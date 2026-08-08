'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { isAuthenticated } from '@/lib/auth';
import { fetchWithAuth } from '@/lib/api';
import { ChatMessage } from '@/components/ChatMessage';
import { ChatSidebar } from '@/components/ChatSidebar';
import { getToken } from '@/lib/auth';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Workspace {
    id: number;
    name: string;
    description: string;
    status: string;
    created_at: string;
}

interface Session {
    id: number;
    title: string;
    created_at: string;
}

interface Message {
    role: 'user' | 'assistant';
    content: string;
    sources?: number[];
    isStreaming?: boolean;
}

const SUGGESTED_PROMPTS = [
    'Summarize the key topics in this workspace',
    'What are the main concepts covered?',
    'List all the important definitions or terms',
    'What problems does this document solve?',
];

export default function WorkspacePage() {
    const router = useRouter();
    const params = useParams();
    const workspaceId = params.id as string;

    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [loading, setLoading] = useState(true);

    // Session state
    const [sessions, setSessions] = useState<Session[]>([]);
    const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
    const [isCreatingSession, setIsCreatingSession] = useState(false);

    // Message state
    const [messages, setMessages] = useState<Message[]>([]);
    const [loadingHistory, setLoadingHistory] = useState(false);

    // Input state
    const [query, setQuery] = useState('');
    const [isSending, setIsSending] = useState(false);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    // ── Scroll to bottom whenever messages change ──────────────────────────
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // ── Auth guard ─────────────────────────────────────────────────────────
    useEffect(() => {
        if (!isAuthenticated()) {
            router.push('/login');
        }
    }, [router]);

    // ── Load workspace metadata ────────────────────────────────────────────
    useEffect(() => {
        const fetchWorkspace = async () => {
            try {
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

    // ── Load session history ───────────────────────────────────────────────
    const loadSessionHistory = useCallback(async (sessionId: number) => {
        setLoadingHistory(true);
        setMessages([]);
        try {
            const res = await fetchWithAuth(
                `/api/v1/workspaces/${workspaceId}/chat/sessions/${sessionId}`
            );
            if (res.ok) {
                const data = await res.json();
                const parsed: Message[] = data.messages.map((m: any) => ({
                    role: m.role,
                    content: m.content,
                    sources: m.sources || [],
                }));
                setMessages(parsed);
            }
        } catch (err) {
            console.error('Failed to load history', err);
        } finally {
            setLoadingHistory(false);
        }
    }, [workspaceId]);

    const handleSelectSession = useCallback(async (sessionId: number) => {
        setActiveSessionId(sessionId);
        await loadSessionHistory(sessionId);
    }, [loadSessionHistory]);

    // ── Load sessions list ─────────────────────────────────────────────────
    const fetchSessions = useCallback(async (autoSelect: boolean = false) => {
        try {
            const res = await fetchWithAuth(`/api/v1/workspaces/${workspaceId}/chat/sessions`);
            if (res.ok) {
                const data: Session[] = await res.json();
                setSessions(data);
                
                // Auto-select the most recent session if requested and we have sessions
                if (autoSelect && data.length > 0) {
                    handleSelectSession(data[0].id);
                }
            }
        } catch (err) {
            console.error('Failed to fetch sessions', err);
        }
    }, [workspaceId, handleSelectSession]);

    useEffect(() => {
        if (workspace?.status === 'ready') {
            fetchSessions(true); // pass true to auto-select on initial load
        }
    }, [workspace, fetchSessions]);


    // ── Delete session ─────────────────────────────────────────────────────
    const handleDeleteSession = useCallback(async (sessionId: number) => {
        if (!confirm('Are you sure you want to delete this chat session?')) return;
        
        try {
            const res = await fetchWithAuth(
                `/api/v1/workspaces/${workspaceId}/chat/sessions/${sessionId}`,
                { method: 'DELETE' }
            );
            if (res.ok) {
                // Update local state
                setSessions(prev => prev.filter(s => s.id !== sessionId));
                if (activeSessionId === sessionId) {
                    setActiveSessionId(null);
                    setMessages([]);
                }
            }
        } catch (err) {
            console.error('Failed to delete session', err);
        }
    }, [workspaceId, activeSessionId]);

    // ── Create new chat session ────────────────────────────────────────────
    const handleNewChat = useCallback(async () => {
        setIsCreatingSession(true);
        try {
            const res = await fetchWithAuth(
                `/api/v1/workspaces/${workspaceId}/chat/sessions`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: null }),
                }
            );
            if (res.ok) {
                const newSession: Session = await res.json();
                setSessions(prev => [newSession, ...prev]);
                setActiveSessionId(newSession.id);
                setMessages([]);
                inputRef.current?.focus();
            }
        } catch (err) {
            console.error('Failed to create session', err);
        } finally {
            setIsCreatingSession(false);
        }
    }, [workspaceId]);

    // ── Send message with streaming ────────────────────────────────────────
    const handleSend = useCallback(async () => {
        if (!query.trim() || isSending || !activeSessionId) return;

        const userText = query.trim();
        setQuery('');
        setIsSending(true);

        // Optimistically add the user message
        setMessages(prev => [...prev, { role: 'user', content: userText }]);

        // Add a streaming placeholder for the assistant
        setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true, sources: [] }]);

        try {
            const response = await fetchWithAuth(
                `/api/v1/workspaces/${workspaceId}/chat/sessions/${activeSessionId}/messages`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ query: userText }),
                }
            );

            if (!response.ok || !response.body) {
                throw new Error(`Server error ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let assistantText = '';
            let sourcesForMessage: number[] = [];
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                
                let boundary = buffer.indexOf('\n\n');
                while (boundary !== -1) {
                    const eventStr = buffer.slice(0, boundary);
                    buffer = buffer.slice(boundary + 2);
                    
                    const lines = eventStr.split('\n');
                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        const payload = line.slice(6); // strip "data: "

                        if (payload === '[DONE]') {
                            // Finalise the streaming message
                            setMessages(prev => {
                                const updated = [...prev];
                                const lastIdx = updated.length - 1;
                                updated[lastIdx] = {
                                    role: 'assistant',
                                    content: assistantText,
                                    sources: sourcesForMessage,
                                    isStreaming: false,
                                };
                                return updated;
                            });
                        } else if (payload.startsWith('[SOURCES]')) {
                            sourcesForMessage = JSON.parse(payload.slice(9));
                        } else {
                            // It's a text token. Backend now sends it as a JSON string to preserve newlines.
                            let text = payload;
                            try {
                                text = JSON.parse(payload.trim());
                            } catch (e) {
                                // fallback to raw text if not JSON
                                console.error("SSE JSON parse error:", e, payload);
                            }
                            
                            assistantText += text;
                            setMessages(prev => {
                                const updated = [...prev];
                                const lastIdx = updated.length - 1;
                                if (updated[lastIdx]?.isStreaming) {
                                    updated[lastIdx] = {
                                        ...updated[lastIdx],
                                        content: assistantText,
                                    };
                                }
                                return updated;
                            });
                        }
                    }
                    boundary = buffer.indexOf('\n\n');
                }
            }

            // Refresh sessions to pick up any updated title
            await fetchSessions();
        } catch (err) {
            console.error('Streaming error', err);
            setMessages(prev => {
                const updated = [...prev];
                const lastIdx = updated.length - 1;
                if (updated[lastIdx]?.isStreaming) {
                    updated[lastIdx] = {
                        role: 'assistant',
                        content: 'Sorry, something went wrong. Please try again.',
                        isStreaming: false,
                        sources: [],
                    };
                }
                return updated;
            });
        } finally {
            setIsSending(false);
            inputRef.current?.focus();
        }
    }, [query, isSending, activeSessionId, workspaceId, fetchSessions]);

    // ── Handle Enter key in textarea ──────────────────────────────────────
    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    // ── Loading screen ─────────────────────────────────────────────────────
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
        <div className="h-screen flex flex-col bg-[#f7f9f6]">
            {/* Top navigation bar */}
            <header className="bg-white border-b border-[#e8efe6] px-6 py-3 flex justify-between items-center shrink-0 z-10">
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
                    <span className="text-sm font-medium text-[#2d372c]">{workspace.name}</span>
                </div>
                <div className={`px-2.5 py-1 text-xs font-medium rounded-full ${
                    workspace.status === 'ready' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                }`}>
                    {workspace.status}
                </div>
            </header>

            {workspace.status !== 'ready' ? (
                <div className="flex-1 flex items-center justify-center">
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center max-w-sm">
                        <p className="text-amber-700 text-sm font-medium">
                            Chat is available once the workspace finishes processing.
                        </p>
                        <p className="text-amber-600 text-xs mt-1">Status: <strong>{workspace.status}</strong></p>
                    </div>
                </div>
            ) : (
                <div className="flex-1 flex overflow-hidden">
                    {/* Sidebar */}
                    <ChatSidebar
                        sessions={sessions}
                        activeSessionId={activeSessionId}
                        onSelectSession={handleSelectSession}
                        onNewChat={handleNewChat}
                        onDeleteSession={handleDeleteSession}
                        workspaceName={workspace.name}
                        isCreatingSession={isCreatingSession}
                    />

                    {/* Main chat panel */}
                    <main className="flex-1 flex flex-col overflow-hidden">
                        {/* Message thread */}
                        <div className="flex-1 overflow-y-auto px-6 py-6">
                            {!activeSessionId ? (
                                /* Welcome / landing state */
                                <div className="h-full flex flex-col items-center justify-center max-w-lg mx-auto text-center">
                                    <div className="w-14 h-14 bg-[#e8efe6] rounded-2xl flex items-center justify-center mb-4">
                                        <svg className="w-7 h-7 text-[#3d4c3c]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                                        </svg>
                                    </div>
                                    <h3 className="text-lg font-semibold text-[#2d372c] mb-2">
                                        Ask anything about <span className="text-[#3d9e5f]">{workspace.name}</span>
                                    </h3>
                                    <p className="text-sm text-[#7a8c78] mb-6">
                                        Start a new chat or select an existing session to begin a conversation grounded in your documents.
                                    </p>
                                    {/* Suggested prompts */}
                                    <div className="w-full space-y-2">
                                        <p className="text-xs text-[#a0aea0] mb-2">Try asking:</p>
                                        {SUGGESTED_PROMPTS.map((prompt) => (
                                            <button
                                                key={prompt}
                                                onClick={async () => {
                                                    // Create a session then set the query
                                                    await handleNewChat();
                                                    setQuery(prompt);
                                                    inputRef.current?.focus();
                                                }}
                                                className="w-full text-left px-4 py-2.5 bg-white border border-[#e8efe6] rounded-xl text-sm text-[#5a6e58] hover:border-[#b5ccb3] hover:bg-[#f7f9f6] transition-all"
                                            >
                                                {prompt}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            ) : loadingHistory ? (
                                <div className="flex items-center justify-center h-full">
                                    <div className="w-6 h-6 border-2 border-[#3d4c3c] border-t-transparent rounded-full animate-spin" />
                                </div>
                            ) : messages.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-full text-center">
                                    <div className="w-12 h-12 bg-[#f0f4ef] rounded-xl flex items-center justify-center mb-3">
                                        <svg className="w-6 h-6 text-[#8fa88c]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                                        </svg>
                                    </div>
                                    <p className="text-sm text-[#7a8c78] font-medium">New conversation started</p>
                                    <p className="text-xs text-[#a0aea0] mt-1">Ask your first question below</p>
                                </div>
                            ) : (
                                <div className="max-w-3xl mx-auto">
                                    {messages.map((msg, idx) => (
                                        <ChatMessage
                                            key={idx}
                                            role={msg.role}
                                            content={msg.content}
                                            sources={msg.sources}
                                            isStreaming={msg.isStreaming}
                                        />
                                    ))}
                                    <div ref={messagesEndRef} />
                                </div>
                            )}
                        </div>

                        {/* Input bar */}
                        {activeSessionId && (
                            <div className="shrink-0 border-t border-[#e8efe6] bg-white px-6 py-4">
                                <div className="max-w-3xl mx-auto flex gap-3 items-end">
                                    <textarea
                                        ref={inputRef}
                                        id="chat-input"
                                        value={query}
                                        onChange={e => setQuery(e.target.value)}
                                        onKeyDown={handleKeyDown}
                                        placeholder="Ask a question… (Enter to send, Shift+Enter for new line)"
                                        disabled={isSending}
                                        rows={1}
                                        className="flex-1 resize-none px-4 py-3 bg-[#f7f9f6] border border-[#e8efe6] rounded-xl text-sm text-[#2d372c] placeholder-[#b0bead] focus:outline-none focus:ring-2 focus:ring-[#3d4c3c] focus:border-transparent transition-all max-h-32 overflow-y-auto"
                                        style={{ minHeight: '44px' }}
                                    />
                                    <button
                                        id="chat-send-btn"
                                        onClick={handleSend}
                                        disabled={isSending || !query.trim()}
                                        className="w-11 h-11 bg-[#3d4c3c] hover:bg-[#2d372c] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition-colors flex items-center justify-center shrink-0"
                                    >
                                        {isSending ? (
                                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                        ) : (
                                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                                            </svg>
                                        )}
                                    </button>
                                </div>
                                <p className="text-xs text-[#b0bead] text-center mt-2">
                                    Answers are grounded in your workspace documents only.
                                </p>
                            </div>
                        )}
                    </main>
                </div>
            )}
        </div>
    );
}
