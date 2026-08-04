export function setToken(token: string) {
    if (typeof window !== 'undefined') {
        localStorage.setItem('wie_token', token);
    }
}

export function getToken() {
    if (typeof window !== 'undefined') {
        return localStorage.getItem('wie_token');
    }
    return null;
}

export function setRefreshToken(token: string) {
    if (typeof window !== 'undefined') {
        localStorage.setItem('wie_refresh_token', token);
    }
}

export function getRefreshToken() {
    if (typeof window !== 'undefined') {
        return localStorage.getItem('wie_refresh_token');
    }
    return null;
}

export function removeToken() {
    if (typeof window !== 'undefined') {
        localStorage.removeItem('wie_token');
        localStorage.removeItem('wie_refresh_token');
    }
}

export function isAuthenticated() {
    return !!getToken() || !!getRefreshToken();
}
