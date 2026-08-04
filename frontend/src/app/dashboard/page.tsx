'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { isAuthenticated, removeToken } from '@/lib/auth';
import { fetchWithAuth } from '@/lib/api';
import { WorkspaceCard } from '@/components/WorkspaceCard';
import { UploadModal } from '@/components/UploadModal';

export default function DashboardPage() {
    const router = useRouter();
    const [loading, setLoading] = useState(true);
    const [workspaces, setWorkspaces] = useState<any[]>([]);
    const [isModalOpen, setIsModalOpen] = useState(false);

    const fetchWorkspaces = useCallback(async () => {
        try {
            const res = await fetchWithAuth('/api/v1/workspaces');
            if (res.ok) {
                const data = await res.json();
                setWorkspaces(data);
            }
        } catch (err) {
            console.error("Failed to fetch workspaces", err);
        }
    }, []);

    useEffect(() => {
        if (!isAuthenticated()) {
            router.push('/login');
        } else {
            setLoading(false);
            fetchWorkspaces();
        }
    }, [router, fetchWorkspaces]);

    // Polling logic
    useEffect(() => {
        const hasProcessing = workspaces.some(ws => ws.status === 'processing' || ws.status === 'pending');
        let interval: NodeJS.Timeout;

        if (hasProcessing) {
            interval = setInterval(() => {
                fetchWorkspaces();
            }, 3000);
        }

        return () => {
            if (interval) clearInterval(interval);
        };
    }, [workspaces, fetchWorkspaces]);

    const handleLogout = () => {
        removeToken();
        router.push('/login');
    };

    const handleDelete = async (id: number) => {
        if (!confirm('Are you sure you want to delete this workspace? This cannot be undone.')) return;

        try {
            const res = await fetchWithAuth(`/api/v1/workspaces/${id}`, {
                method: 'DELETE'
            });
            if (res.ok) {
                fetchWorkspaces();
            } else {
                alert("Failed to delete workspace");
            }
        } catch (err) {
            console.error("Failed to delete workspace", err);
        }
    };

    if (loading) {
        return <div className="min-h-screen flex items-center justify-center bg-[#f7f9f6]">Loading...</div>;
    }

    return (
        <div className="min-h-screen bg-[#f7f9f6] text-[#333333]">
            <header className="bg-white border-b border-[#e8efe6] px-8 py-4 flex justify-between items-center sticky top-0 z-10">
                <h1 className="text-xl font-semibold text-[#2d372c]">Workspace Intelligence Engine</h1>
                <button
                    onClick={handleLogout}
                    className="px-4 py-2 text-sm font-medium text-[#7a8c78] hover:text-[#2d372c] transition-colors"
                >
                    Log out
                </button>
            </header>

            <main className="max-w-7xl mx-auto px-8 py-12">
                <div className="flex justify-between items-center mb-8">
                    <div>
                        <h2 className="text-2xl font-semibold tracking-tight text-[#2d372c]">Your Workspaces</h2>
                        <p className="text-[#7a8c78] mt-1">Manage and query your documentation contexts.</p>
                    </div>
                    <button
                        onClick={() => setIsModalOpen(true)}
                        className="px-5 py-2.5 bg-[#3d4c3c] hover:bg-[#2d372c] text-white text-sm font-medium rounded-lg transition-colors shadow-sm"
                    >
                        + New Workspace
                    </button>
                </div>

                {workspaces.length === 0 ? (
                    <div className="bg-white rounded-2xl p-12 border border-[#e8efe6] shadow-sm text-center">
                        <div className="w-16 h-16 bg-[#f0f4ef] text-[#8fa88c] rounded-full flex items-center justify-center mx-auto mb-4">
                            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                            </svg>
                        </div>
                        <h3 className="text-lg font-medium text-[#2d372c] mb-2">No workspaces yet</h3>
                        <p className="text-[#7a8c78] max-w-sm mx-auto mb-6">
                            Create your first workspace by uploading a ZIP archive containing your documentation.
                        </p>
                        <button
                            onClick={() => setIsModalOpen(true)}
                            className="px-5 py-2.5 bg-white border-2 border-[#3d4c3c] text-[#3d4c3c] hover:bg-[#f0f4ef] text-sm font-medium rounded-lg transition-colors"
                        >
                            Create Workspace
                        </button>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {workspaces.map(ws => (
                            <WorkspaceCard
                                key={ws.id}
                                workspace={ws}
                                onDelete={handleDelete}
                            />
                        ))}
                    </div>
                )}
            </main>

            <UploadModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                onSuccess={() => fetchWorkspaces()}
            />
        </div>
    );
}
