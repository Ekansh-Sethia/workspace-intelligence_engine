'use client';

import { useEffect } from 'react';

interface ConfirmModalProps {
    isOpen: boolean;
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    isDestructive?: boolean;
    isLoading?: boolean;
    onConfirm: () => void;
    onClose: () => void;
}

export function ConfirmModal({
    isOpen,
    title,
    message,
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    isDestructive = true,
    isLoading = false,
    onConfirm,
    onClose,
}: ConfirmModalProps) {
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && isOpen && !isLoading) {
                onClose();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isOpen, isLoading, onClose]);

    if (!isOpen) return null;

    return (
        <div 
            className="fixed inset-0 bg-black/45 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-in fade-in duration-150"
            onClick={(e) => {
                if (e.target === e.currentTarget && !isLoading) onClose();
            }}
        >
            <div 
                role="dialog"
                aria-modal="true"
                className="bg-white rounded-2xl w-full max-w-md p-6 shadow-2xl border border-[#e8efe6] animate-in zoom-in-95 duration-150"
            >
                <div className="flex items-start gap-4">
                    {isDestructive && (
                        <div className="w-11 h-11 rounded-xl bg-red-50 border border-red-100 flex items-center justify-center shrink-0 text-red-600 mt-0.5">
                            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                        </div>
                    )}
                    <div className="flex-1 min-w-0">
                        <h3 className="text-lg font-semibold text-[#2d372c]">{title}</h3>
                        <p className="text-sm text-[#667764] mt-1.5 leading-relaxed">{message}</p>
                    </div>
                </div>

                <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-[#f0f4ef]">
                    <button
                        type="button"
                        onClick={onClose}
                        disabled={isLoading}
                        className="px-4 py-2 text-sm font-medium text-[#4b5548] hover:text-[#2d372c] hover:bg-[#f2f6f1] rounded-xl transition-colors border border-[#dce4db] disabled:opacity-50"
                    >
                        {cancelText}
                    </button>
                    <button
                        type="button"
                        onClick={onConfirm}
                        disabled={isLoading}
                        className={`px-4 py-2 text-sm font-medium rounded-xl transition-all disabled:opacity-50 flex items-center gap-2 ${
                            isDestructive
                                ? 'bg-red-600 hover:bg-red-700 active:bg-red-800 text-white shadow-sm shadow-red-200'
                                : 'bg-[#3d4c3c] hover:bg-[#2d372c] text-white shadow-sm'
                        }`}
                    >
                        {isLoading && (
                            <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        )}
                        {confirmText}
                    </button>
                </div>
            </div>
        </div>
    );
}
