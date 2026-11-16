'use client';

import React from 'react';
import Link from 'next/link';
import { useLanguage } from '@/context/LanguageContext';
import { useAuth } from '@/context/AuthContext';
import { Badge } from '../ui/Badge';

export function CmsHeader() {
  const { t, language, setLanguage } = useLanguage();
  const { user, isAuthenticated, logout } = useAuth();

  return (
    <header className="bg-[#1e3a8a] text-white border-b-4 border-amber-500 px-4 py-3 shadow-md">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Left: Branding & Administrative Title */}
        <div className="flex items-center gap-3">
          <Link href="/cms" className="flex items-center gap-2.5 hover:opacity-90 focus-visible:outline-white">
            <span className="text-2xl drop-shadow-sm">🏛️</span>
            <div>
              <span className="font-bold text-sm sm:text-base tracking-tight block text-white drop-shadow-sm">
                {t.cms.portalTitle}
              </span>
              <span className="text-[11px] text-blue-100 font-medium block -mt-0.5">
                GramSetu Administrative Backoffice
              </span>
            </div>
          </Link>
          <span className="hidden sm:inline-flex px-2 py-0.5 bg-amber-400 text-slate-950 font-bold rounded text-[10px] uppercase tracking-wider">
            CMS Portal
          </span>
          {isAuthenticated && (
            <span className="hidden lg:inline-flex items-center gap-1 text-[11px] text-white font-semibold bg-emerald-700 border border-emerald-500 px-2 py-0.5 rounded-full shadow-sm">
              <span>🛡️</span> MFA Verified
            </span>
          )}
        </div>

        {/* Right: User / Role indicator, Public link, Logout */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {isAuthenticated && user && (
            <>
              <div className="hidden sm:flex flex-col text-right">
                <span className="font-bold text-white">
                  {user.full_name || user.email}
                </span>
                <span className="text-[10px] text-blue-200">{user.email}</span>
              </div>

              <div className="flex items-center gap-1.5 bg-blue-950/80 px-2.5 py-1 rounded-md text-white border border-blue-400 shrink-0 shadow-inner">
                <span className="text-blue-200 hidden md:inline font-medium">{t.cms.roleIndicator}:</span>
                <span className={`font-bold font-mono text-[11px] sm:text-xs ${user.is_super_admin ? 'text-amber-300' : 'text-emerald-300'}`}>
                  {user.role_display.toUpperCase()}
                </span>
              </div>
            </>
          )}

          {/* Language Selector */}
          <div className="flex items-center">
            <label htmlFor="cms-lang-select" className="sr-only">
              {t.accessibility.language}
            </label>
            <select
              id="cms-lang-select"
              value={language}
              onChange={(e) => setLanguage(e.target.value as any)}
              className="bg-white text-slate-900 border border-slate-300 rounded px-2.5 py-1 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-amber-400 cursor-pointer shadow-sm"
            >
              <option value="mr">मराठी</option>
              <option value="hi">हिंदी</option>
              <option value="en">English</option>
            </select>
          </div>

          <Link
            href="/"
            className="text-amber-300 hover:text-white font-semibold underline focus-visible:outline-white shrink-0 text-[11px] sm:text-xs transition-colors"
          >
            &larr; {t.cms.backToPublic}
          </Link>

          {isAuthenticated && (
            <button
              type="button"
              onClick={() => logout()}
              className="shrink-0 px-3 py-1 rounded bg-red-700 hover:bg-red-800 text-white font-semibold shadow-sm focus-visible:outline-white transition-colors"
            >
              {t.cms.logout}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
