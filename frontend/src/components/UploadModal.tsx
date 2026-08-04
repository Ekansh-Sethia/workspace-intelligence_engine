'use client';

import { useState, useRef } from 'react';
import { fetchWithAuth } from '@/lib/api';

export function UploadModal({ isOpen, onClose, onSuccess }: { isOpen: boolean, onClose: () => void, onSuccess: () => void }) {
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [file, setFile] = useState<File | null>(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    
    const fileInputRef = useRef<HTMLInputElement>(null);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!file) {
            setError("Please select a ZIP file");
            return;
        }

        setLoading(true);
        setError('');

        const formData = new FormData();
        formData.append('name', name);
        formData.append('description', description);
        formData.append('file', file);

        try {
            const res = await fetchWithAuth('/api/v1/workspaces', {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || 'Upload failed');
            }

            setName('');
            setDescription('');
            setFile(null);
            onSuccess();
            onClose();
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl w-full max-w-lg p-6 shadow-xl border border-[#e8efe6]">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-xl font-semibold text-[#2d372c]">Create Workspace</h2>
                    <button onClick={onClose} className="text-[#a0aea0] hover:text-[#2d372c] transition-colors">
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="space-y-5">
                    {error && <div className="p-3 text-sm text-red-600 bg-red-50 rounded-lg">{error}</div>}
                    
                    <div className="space-y-1">
                        <label className="text-sm font-medium text-[#4b5548]">Workspace Name</label>
                        <input 
                            type="text" 
                            required
                            className="w-full px-4 py-2 bg-[#fafbfa] border border-[#dce4db] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8fa88c] transition-all"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                        />
                    </div>

                    <div className="space-y-1">
                        <label className="text-sm font-medium text-[#4b5548]">Description (optional)</label>
                        <textarea 
                            rows={2}
                            className="w-full px-4 py-2 bg-[#fafbfa] border border-[#dce4db] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8fa88c] transition-all"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                        />
                    </div>

                    <div className="space-y-1">
                        <label className="text-sm font-medium text-[#4b5548]">Codebase Archive (.zip)</label>
                        <div 
                            className="border-2 border-dashed border-[#dce4db] rounded-xl p-8 text-center hover:bg-[#fafbfa] transition-colors cursor-pointer"
                            onClick={() => fileInputRef.current?.click()}
                        >
                            <input 
                                type="file" 
                                accept=".zip"
                                className="hidden" 
                                ref={fileInputRef}
                                onChange={(e) => setFile(e.target.files?.[0] || null)}
                            />
                            {file ? (
                                <div className="text-sm font-medium text-[#2d372c]">
                                    {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
                                </div>
                            ) : (
                                <div>
                                    <p className="text-sm font-medium text-[#3d4c3c]">Click to browse</p>
                                    <p className="text-xs text-[#7a8c78] mt-1">Maximum file size: 50MB</p>
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="pt-4 flex justify-end space-x-3">
                        <button 
                            type="button" 
                            onClick={onClose}
                            className="px-4 py-2.5 text-sm font-medium text-[#4b5548] hover:bg-[#f0f4ef] rounded-lg transition-colors"
                        >
                            Cancel
                        </button>
                        <button 
                            type="submit" 
                            disabled={loading || !file}
                            className="px-6 py-2.5 bg-[#3d4c3c] hover:bg-[#2d372c] text-white text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#3d4c3c] disabled:opacity-50"
                        >
                            {loading ? 'Uploading...' : 'Create Workspace'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
