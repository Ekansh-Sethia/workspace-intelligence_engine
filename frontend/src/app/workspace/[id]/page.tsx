'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { isAuthenticated } from '@/lib/auth';
import { fetchWithAuth } from '@/lib/api';

interface SearchResult {
    score: number;
    text: string;
    file_id: number;
    chunk_id: number;
    chunk_index: number;
    page_number: number | null;
}

interface Workspace {
    id: number;
    name: string;
    description: string;
    status: string;
    created_at: string;
}

export default function WorkspacePage() {
    const router = useRouter();
    const params = useParams();
    const workspaceId = params.id as string;

    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [loading, setLoading] = useState(true);

    // Search state
    const [query, setQuery] = useState('');
    const [limit, setLimit] = useState(5);
    const [results, setResults] = useState<SearchResult[] | null>(null);
    const [searching, setSearching] = useState(false);
    const [searchError, setSearchError] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (!isAuthenticated()) {
            router.push('/login');
            return;
        }
        const fetchWorkspace = async () => {
            try {
                // Fetch all workspaces and find the current one
                const res = await fetchWithAuth('/api/v1/workspaces');
                if (res.ok) {
                    const data: Workspace[] = await res.json();
                    const ws = data.find(w => String(w.id) === workspaceId);
                    if (ws) {
                        setWorkspace(ws);
                    } else {
                        router.push('/dashboard');
                    }
                }
            } catch {
                router.push('/dashboard');
            } finally {
                setLoading(false);
            }
        };
        fetchWorkspace();
    }, [router, workspaceId]);

    const handleSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!query.trim()) return;

        setSearching(true);
        setSearchError('');
        setResults(null);

        try {
            const res = await fetchWithAuth(`/api/v1/workspaces/${workspaceId}/search`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query.trim(), limit }),
            });

            if (res.ok) {
                const data: SearchResult[] = await res.json();
                setResults(data);
            } else {
                const err = await res.json();
                setSearchError(err.detail || 'Search failed. Please try again.');
            }
        } catch {
            setSearchError('Network error. Please check your connection.');
        } finally {
            setSearching(false);
        }
    };

    const getScoreColor = (score: number) => {
        if (score >= 0.75) return { bar: '#3d9e5f', label: 'Very Relevant', text: '#166534' };
        if (score >= 0.55) return { bar: '#7ab88a', label: 'Relevant', text: '#14532d' };
        if (score >= 0.35) return { bar: '#b5ccb3', label: 'Somewhat Relevant', text: '#3d4c3c' };
        return { bar: '#d1d5db', label: 'Low Relevance', text: '#6b7280' };
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#f7f9f6]">
                <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 border-2 border-[#3d4c3c] border-t-transparent rounded-full animate-spin" />
                    <span className="text-[#7a8c78] text-sm">Loading workspace...</span>
                </div>
            </div>
        );
    }

    if (!workspace) return null;

    return (
        <div className="min-h-screen bg-[#f7f9f6] text-[#333333]">
            {/* Header */}
            <header className="bg-white border-b border-[#e8efe6] px-8 py-4 flex justify-between items-center sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => router.push('/dashboard')}
                        className="text-[#7a8c78] hover:text-[#2d372c] transition-colors flex items-center gap-1.5 text-sm"
                    >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                        Workspaces
                    </button>
                    <span className="text-[#d1d8d0]">/</span>
                    <h1 className="text-sm font-medium text-[#2d372c]">{workspace.name}</h1>
                </div>
                <div className={`px-2.5 py-1 text-xs font-medium rounded-full ${
                    workspace.status === 'ready' ? 'bg-green-100 text-green-800' :
                    workspace.status === 'processing' ? 'bg-blue-100 text-blue-800' :
                    workspace.status === 'failed' ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-600'
                }`}>
                    {workspace.status}
                </div>
            </header>

            <main className="max-w-4xl mx-auto px-6 py-10">
                {/* Workspace Info */}
                <div className="mb-8">
                    <h2 className="text-2xl font-semibold text-[#2d372c]">{workspace.name}</h2>
                    {workspace.description && (
                        <p className="text-[#7a8c78] mt-1">{workspace.description}</p>
                    )}
                    <p className="text-xs text-[#a0aea0] mt-2">
                        Created {new Date(workspace.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                    </p>
                </div>

                {/* Search Panel */}
                {workspace.status !== 'ready' ? (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
                        <p className="text-amber-700 text-sm font-medium">
                            Search is available once the workspace finishes processing.
                        </p>
                        <p className="text-amber-600 text-xs mt-1">Current status: <strong>{workspace.status}</strong></p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {/* Search Form */}
                        <div className="bg-white rounded-2xl border border-[#e8efe6] shadow-sm p-6">
                            <div className="flex items-center gap-2 mb-4">
                                <div className="w-7 h-7 bg-[#f0f4ef] rounded-lg flex items-center justify-center">
                                    <svg className="w-4 h-4 text-[#3d4c3c]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                    </svg>
                                </div>
                                <h3 className="text-sm font-semibold text-[#2d372c]">Semantic Search</h3>
                                <span className="text-xs bg-[#f0f4ef] text-[#5a6e58] px-2 py-0.5 rounded-full ml-1">Phase 8 Test</span>
                            </div>

                            <form onSubmit={handleSearch} className="space-y-3">
                                <div className="flex gap-3">
                                    <input
                                        ref={inputRef}
                                        id="search-query-input"
                                        type="text"
                                        value={query}
                                        onChange={e => setQuery(e.target.value)}
                                        placeholder="Ask anything about this workspace…"
                                        className="flex-1 px-4 py-2.5 bg-[#f7f9f6] border border-[#e8efe6] rounded-lg text-sm text-[#2d372c] placeholder-[#b0bead] focus:outline-none focus:ring-2 focus:ring-[#3d4c3c] focus:border-transparent transition-all"
                                        disabled={searching}
                                    />
                                    <button
                                        id="search-submit-btn"
                                        type="submit"
                                        disabled={searching || !query.trim()}
                                        className="px-5 py-2.5 bg-[#3d4c3c] hover:bg-[#2d372c] disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2 min-w-[100px] justify-center"
                                    >
                                        {searching ? (
                                            <>
                                                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                                Searching
                                            </>
                                        ) : (
                                            'Search'
                                        )}
                                    </button>
                                </div>

                                {/* Result limit selector */}
                                <div className="flex items-center gap-2 text-xs text-[#7a8c78]">
                                    <span>Return top</span>
                                    {[3, 5, 10, 15].map(n => (
                                        <button
                                            key={n}
                                            type="button"
                                            onClick={() => setLimit(n)}
                                            className={`px-2 py-0.5 rounded-md transition-colors ${
                                                limit === n
                                                    ? 'bg-[#3d4c3c] text-white'
                                                    : 'bg-[#f0f4ef] text-[#5a6e58] hover:bg-[#e8efe6]'
                                            }`}
                                        >
                                            {n}
                                        </button>
                                    ))}
                                    <span>results</span>
                                </div>
                            </form>
                        </div>

                        {/* Error */}
                        {searchError && (
                            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-red-700 text-sm">
                                {searchError}
                            </div>
                        )}

                        {/* Results Panel */}
                        {results !== null && (
                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <p className="text-sm font-medium text-[#2d372c]">
                                        {results.length > 0
                                            ? `${results.length} result${results.length !== 1 ? 's' : ''} for "${query}"`
                                            : `No results found for "${query}"`
                                        }
                                    </p>
                                    <button
                                        onClick={() => { setResults(null); setQuery(''); inputRef.current?.focus(); }}
                                        className="text-xs text-[#7a8c78] hover:text-[#2d372c] transition-colors"
                                    >
                                        Clear
                                    </button>
                                </div>

                                {results.length === 0 ? (
                                    <div className="bg-white rounded-xl border border-[#e8efe6] p-8 text-center">
                                        <p className="text-[#7a8c78] text-sm">Try a different query — the workspace may not contain content about this topic.</p>
                                    </div>
                                ) : (
                                    results.map((result, idx) => {
                                        const scoreInfo = getScoreColor(result.score);
                                        return (
                                            <div
                                                key={`${result.chunk_id}-${idx}`}
                                                className="bg-white rounded-xl border border-[#e8efe6] shadow-sm overflow-hidden"
                                                style={{ borderLeftWidth: '3px', borderLeftColor: scoreInfo.bar }}
                                            >
                                                <div className="px-5 pt-4 pb-3">
                                                    {/* Top bar: rank + score + metadata */}
                                                    <div className="flex items-center justify-between mb-3">
                                                        <div className="flex items-center gap-2">
                                                            <span className="w-5 h-5 bg-[#f0f4ef] text-[#5a6e58] text-xs font-bold rounded flex items-center justify-center">
                                                                {idx + 1}
                                                            </span>
                                                            <span className="text-xs font-medium" style={{ color: scoreInfo.text }}>
                                                                {scoreInfo.label}
                                                            </span>
                                                        </div>
                                                        <div className="flex items-center gap-3">
                                                            {result.page_number !== null && (
                                                                <span className="text-xs text-[#a0aea0]">
                                                                    Page {result.page_number}
                                                                </span>
                                                            )}
                                                            <span className="text-xs text-[#a0aea0]">
                                                                Chunk #{result.chunk_index}
                                                            </span>
                                                            {/* Score pill */}
                                                            <div className="flex items-center gap-1.5">
                                                                <div className="w-16 h-1.5 bg-[#f0f4ef] rounded-full overflow-hidden">
                                                                    <div
                                                                        className="h-full rounded-full transition-all"
                                                                        style={{ width: `${Math.min(result.score * 100, 100)}%`, backgroundColor: scoreInfo.bar }}
                                                                    />
                                                                </div>
                                                                <span className="text-xs font-mono font-semibold text-[#5a6e58]">
                                                                    {(result.score * 100).toFixed(1)}%
                                                                </span>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    {/* Chunk text */}
                                                    <p className="text-sm text-[#3d3d3d] leading-relaxed whitespace-pre-wrap font-mono bg-[#f7f9f6] rounded-lg p-3 max-h-48 overflow-y-auto">
                                                        {result.text}
                                                    </p>
                                                </div>
                                            </div>
                                        );
                                    })
                                )}
                            </div>
                        )}

                        {/* Placeholder when no search yet */}
                        {results === null && !searchError && (
                            <div className="bg-white rounded-xl border border-dashed border-[#d4dfd2] p-10 text-center">
                                <div className="w-12 h-12 bg-[#f0f4ef] rounded-xl flex items-center justify-center mx-auto mb-3">
                                    <svg className="w-6 h-6 text-[#8fa88c]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                                    </svg>
                                </div>
                                <p className="text-sm text-[#7a8c78] font-medium">Ask anything in natural language</p>
                                <p className="text-xs text-[#a0aea0] mt-1">e.g. "How does authentication work?" or "What are the API endpoints?"</p>
                            </div>
                        )}
                    </div>
                )}
            </main>
        </div>
    );
}
