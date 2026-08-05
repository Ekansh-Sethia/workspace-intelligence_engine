'use client';

import { useRouter } from 'next/navigation';

export function WorkspaceCard({ workspace, onDelete }: { workspace: any, onDelete: (id: number) => void }) {
    const router = useRouter();

    const handleCardClick = (e: React.MouseEvent) => {
        // Don't navigate if clicking the Delete button
        if ((e.target as HTMLElement).closest('[data-no-nav]')) return;
        if (workspace.status === 'ready') {
            router.push(`/workspace/${workspace.id}`);
        }
    };

    return (
        <div
            onClick={handleCardClick}
            className={`bg-white rounded-xl p-6 border border-[#e8efe6] shadow-sm transition-all ${
                workspace.status === 'ready'
                    ? 'hover:shadow-md hover:border-[#c5d4c3] cursor-pointer'
                    : 'cursor-default'
            }`}
        >
            <div className="flex justify-between items-start mb-4">
                <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-medium text-[#2d372c] truncate">{workspace.name}</h3>
                    <p className="text-sm text-[#7a8c78] mt-1 line-clamp-2">{workspace.description || "No description provided"}</p>
                </div>
                <div className={`flex items-center space-x-1.5 px-2.5 py-1 text-xs font-medium rounded-full ml-3 shrink-0 ${
                    workspace.status === 'ready' ? 'bg-green-100 text-green-800' :
                    workspace.status === 'processing' ? 'bg-blue-100 text-blue-800' :
                    workspace.status === 'failed' ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-800'
                }`}>
                    {workspace.status === 'processing' && (
                        <svg className="animate-spin -ml-1 mr-1 h-3 w-3 text-blue-800" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    )}
                    <span>{workspace.status}</span>
                </div>
            </div>

            <div className="flex justify-between items-center mt-6 pt-4 border-t border-[#f0f4ef]">
                <span className="text-xs text-[#a0aea0]">
                    Created {new Date(workspace.created_at).toLocaleDateString()}
                </span>
                <div className="flex items-center gap-3">
                    {workspace.status === 'ready' && (
                        <span className="text-xs text-[#5a8c60] font-medium flex items-center gap-1">
                            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                            Search
                        </span>
                    )}
                    <button
                        data-no-nav="true"
                        onClick={() => onDelete(workspace.id)}
                        className="text-xs font-medium text-red-500 hover:text-red-700 transition-colors"
                    >
                        Delete
                    </button>
                </div>
            </div>
        </div>
    );
}
