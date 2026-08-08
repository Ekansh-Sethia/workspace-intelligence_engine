'use client';

import { useEffect, useRef } from 'react';

interface Source {
    chunk_id: number;
    score?: number;
    text?: string;
    file_id?: number;
    chunk_index?: number;
    page_number?: number | null;
}

interface ChatMessageProps {
    role: 'user' | 'assistant';
    content: string;
    sources?: number[];       // chunk_ids (from DB)
    isStreaming?: boolean;     // true while the assistant is still typing
}

export function ChatMessage({ role, content, sources, isStreaming }: ChatMessageProps) {
    const isUser = role === 'user';

    return (
        <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'} mb-4 items-start`}>
            {/* Avatar */}
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                isUser ? 'bg-[#3d4c3c] text-white' : 'bg-[#e8efe6] text-[#3d4c3c]'
            }`}>
                {isUser ? 'Y' : 'AI'}
            </div>

            {/* Bubble */}
            <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                isUser
                    ? 'bg-[#3d4c3c] text-white rounded-tr-sm'
                    : 'bg-white border border-[#e8efe6] text-[#2d372c] rounded-tl-sm shadow-sm'
            }`}>
                {/* Content */}
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>

                {/* Streaming cursor */}
                {isStreaming && (
                    <span className="inline-block w-2 h-4 bg-[#7a8c78] rounded-sm animate-pulse ml-1 align-middle" />
                )}

                {/* Source citations for assistant messages */}
                {!isUser && sources && sources.length > 0 && !isStreaming && (
                    <details className="mt-3 pt-2 border-t border-[#f0f4ef]">
                        <summary className="text-xs text-[#7a8c78] cursor-pointer hover:text-[#3d4c3c] transition-colors select-none">
                            📄 {sources.length} source chunk{sources.length !== 1 ? 's' : ''} used
                        </summary>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                            {sources.map((chunkId) => (
                                <span
                                    key={chunkId}
                                    className="text-xs bg-[#f0f4ef] text-[#5a6e58] px-2 py-0.5 rounded-full font-mono"
                                >
                                    chunk #{chunkId}
                                </span>
                            ))}
                        </div>
                    </details>
                )}
            </div>
        </div>
    );
}
