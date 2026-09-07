import React from 'react';

interface LogoProps {
  size?: number;
  className?: string;
  showText?: boolean;
}

export function Logo({ size = 28, className = '', showText = true }: LogoProps) {
  return (
    <div className={`flex items-center gap-2.5 select-none ${className}`}>
      <div 
        style={{ width: size, height: size }} 
        className="relative flex items-center justify-center shrink-0 rounded-xl bg-gradient-to-br from-[#1e281d] to-[#2d3a2b] shadow-sm ring-1 ring-black/10 overflow-hidden"
      >
        <svg 
          viewBox="0 0 64 64" 
          fill="none" 
          className="w-full h-full p-1"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <linearGradient id="logoSparkGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#a3e635" />
              <stop offset="50%" stopColor="#4ade80" />
              <stop offset="100%" stopColor="#2dd4bf" />
            </linearGradient>
            <linearGradient id="logoSheetGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#8fa88c" stopOpacity="0.5" />
            </linearGradient>
          </defs>

          {/* Context Doc Silhouette */}
          <path 
            d="M18 20C18 17.7909 19.7909 16 22 16H36L46 26V44C46 46.2091 44.2091 48 42 48H22C19.7909 48 18 46.2091 18 44V20Z" 
            fill="#243122" 
            stroke="url(#logoSheetGrad)" 
            strokeWidth="2.5" 
            strokeLinejoin="round" 
          />

          <path 
            d="M36 16V24C36 25.1046 36.8954 26 38 26H46" 
            stroke="url(#logoSheetGrad)" 
            strokeWidth="2.5" 
            strokeLinejoin="round" 
          />

          {/* Intelligence Spark */}
          <g transform="translate(32, 34)">
            <circle cx="0" cy="0" r="10" fill="#4ade80" fillOpacity="0.2" />
            <path 
              d="M0 -9C0.6 -4 4 -0.6 9 0C4 0.6 0.6 4 0 9C-0.6 4 -4 0.6 -9 0C-4 -0.6 -0.6 -4 0 -9Z" 
              fill="url(#logoSparkGrad)" 
            />
            <circle cx="0" cy="0" r="2.5" fill="#ffffff" />
          </g>
        </svg>
      </div>
      
      {showText && (
        <div className="flex items-baseline gap-1">
          <span className="font-bold tracking-tight text-[#2d372c] text-lg">Context</span>
          <span className="font-semibold text-emerald-600 text-lg">IQ</span>
        </div>
      )}
    </div>
  );
}
