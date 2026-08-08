'use client';

interface Session {
    id: number;
    title: string;
    created_at: string;
}

interface ChatSidebarProps {
    sessions: Session[];
    activeSessionId: number | null;
    onSelectSession: (id: number) => void;
    onNewChat: () => void;
    onDeleteSession?: (id: number) => void;
    workspaceName: string;
    isCreatingSession: boolean;
}

export function ChatSidebar({
    sessions,
    activeSessionId,
    onSelectSession,
    onNewChat,
    onDeleteSession,
    workspaceName,
    isCreatingSession,
}: ChatSidebarProps) {
    return (
        <aside className="w-64 bg-white border-r border-[#e8efe6] flex flex-col shrink-0">
            {/* Workspace name header */}
            <div className="px-4 py-4 border-b border-[#e8efe6]">
                <p className="text-xs font-medium text-[#7a8c78] uppercase tracking-wider mb-1">Workspace</p>
                <h2 className="text-sm font-semibold text-[#2d372c] truncate">{workspaceName}</h2>
            </div>

            {/* New Chat button */}
            <div className="p-3">
                <button
                    id="new-chat-btn"
                    onClick={onNewChat}
                    disabled={isCreatingSession}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-[#3d4c3c] hover:bg-[#2d372c] disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
                >
                    {isCreatingSession ? (
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    ) : (
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                        </svg>
                    )}
                    New Chat
                </button>
            </div>

            {/* Session list */}
            <nav className="flex-1 overflow-y-auto px-2 pb-4">
                {sessions.length === 0 ? (
                    <p className="text-xs text-[#a0aea0] text-center mt-4 px-4">
                        No chats yet. Start a new conversation!
                    </p>
                ) : (
                    <ul className="space-y-0.5">
                        {sessions.map((session) => (
                            <li key={session.id} className="relative group">
                                <button
                                    onClick={() => onSelectSession(session.id)}
                                    className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors ${
                                        activeSessionId === session.id
                                            ? 'bg-[#f0f4ef] text-[#2d372c]'
                                            : 'text-[#5a6e58] hover:bg-[#f7f9f6] hover:text-[#2d372c]'
                                    }`}
                                >
                                    <div className="flex items-start gap-2 pr-6">
                                        <svg className="w-3.5 h-3.5 mt-0.5 shrink-0 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                                        </svg>
                                        <div className="min-w-0 flex-1">
                                            <p className="text-xs font-medium truncate">{session.title}</p>
                                            <p className="text-xs text-[#a0aea0] mt-0.5">
                                                {new Date(session.created_at).toLocaleDateString('en-US', {
                                                    month: 'short', day: 'numeric'
                                                })}
                                            </p>
                                        </div>
                                    </div>
                                </button>
                                {onDeleteSession && (
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onDeleteSession(session.id);
                                        }}
                                        className={`absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-[#a0aea0] hover:text-red-500 hover:bg-red-50 rounded-md transition-all ${
                                            activeSessionId === session.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                                        }`}
                                        title="Delete chat"
                                    >
                                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                        </svg>
                                    </button>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
            </nav>
        </aside>
    );
}
