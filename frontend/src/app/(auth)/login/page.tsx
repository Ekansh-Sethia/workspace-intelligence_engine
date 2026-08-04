'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { setToken, setRefreshToken } from '@/lib/auth';

export default function LoginPage() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const router = useRouter();

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            // URL encoded form data required by OAuth2PasswordRequestForm
            const formData = new URLSearchParams();
            formData.append('username', email);
            formData.append('password', password);

            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData.toString(),
            });

            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || 'Login failed');
            }

            const data = await res.json();
            setToken(data.access_token);
            setRefreshToken(data.refresh_token);
            router.push('/dashboard');
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="w-full max-w-md bg-white p-8 rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.04)] border border-[#e8efe6]">
            <div className="text-center mb-8">
                <h1 className="text-2xl font-semibold tracking-tight text-[#2d372c]">Welcome Back</h1>
                <p className="text-sm text-[#7a8c78] mt-2">Sign in to your workspace</p>
            </div>
            
            <form onSubmit={handleLogin} className="space-y-5">
                {error && <div className="p-3 text-sm text-red-600 bg-red-50 rounded-lg">{error}</div>}
                
                <div className="space-y-1">
                    <label className="text-sm font-medium text-[#4b5548]">Email address</label>
                    <input 
                        type="email" 
                        required
                        className="w-full px-4 py-2.5 bg-[#fafbfa] border border-[#dce4db] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8fa88c] focus:border-transparent transition-all"
                        placeholder="you@example.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                    />
                </div>

                <div className="space-y-1">
                    <label className="text-sm font-medium text-[#4b5548]">Password</label>
                    <input 
                        type="password" 
                        required
                        className="w-full px-4 py-2.5 bg-[#fafbfa] border border-[#dce4db] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8fa88c] focus:border-transparent transition-all"
                        placeholder="••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                    />
                </div>

                <button 
                    type="submit" 
                    disabled={loading}
                    className="w-full py-2.5 px-4 bg-[#3d4c3c] hover:bg-[#2d372c] text-white font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#3d4c3c] disabled:opacity-70"
                >
                    {loading ? 'Signing in...' : 'Sign in'}
                </button>
            </form>

            <p className="mt-6 text-center text-sm text-[#7a8c78]">
                Don't have an account?{' '}
                <Link href="/signup" className="font-medium text-[#3d4c3c] hover:underline">
                    Create one
                </Link>
            </p>
        </div>
    );
}
