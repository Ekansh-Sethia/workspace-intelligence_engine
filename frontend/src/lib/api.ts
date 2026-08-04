import { getToken, getRefreshToken, setToken, setRefreshToken, removeToken } from './auth';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * A wrapper around native fetch that automatically injects the access token
 * and handles 401 Unauthorized errors by attempting to refresh the token.
 */
export async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
    const token = getToken();
    
    // Setup headers
    const headers = new Headers(options.headers || {});
    if (token) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    
    // First attempt
    let response = await fetch(`${BASE_URL}${url}`, {
        ...options,
        headers
    });
    
    // If 401, try to refresh the token
    if (response.status === 401) {
        const refreshToken = getRefreshToken();
        
        if (refreshToken) {
            try {
                // Call the refresh endpoint
                const refreshResponse = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ refresh_token: refreshToken })
                });
                
                if (refreshResponse.ok) {
                    const data = await refreshResponse.json();
                    
                    // Save new tokens
                    setToken(data.access_token);
                    setRefreshToken(data.refresh_token);
                    
                    // Retry original request with new access token
                    headers.set('Authorization', `Bearer ${data.access_token}`);
                    response = await fetch(`${BASE_URL}${url}`, {
                        ...options,
                        headers
                    });
                } else {
                    // Refresh token is expired or invalid
                    removeToken();
                    if (typeof window !== 'undefined') {
                        window.location.href = '/login';
                    }
                }
            } catch (err) {
                console.error("Failed to refresh token", err);
                removeToken();
                if (typeof window !== 'undefined') {
                    window.location.href = '/login';
                }
            }
        } else {
            // No refresh token available
            removeToken();
            if (typeof window !== 'undefined') {
                window.location.href = '/login';
            }
        }
    }
    
    return response;
}
