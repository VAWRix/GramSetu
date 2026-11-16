'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useLanguage } from '@/context/LanguageContext';
import { fetchSiteConfig } from '@/lib/api';
import { PanchayatProfile } from '@/lib/types';

export function GovernmentHeader() {
  const { t, language } = useLanguage();
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [profile, setProfile] = useState<PanchayatProfile | null>(null);

  useEffect(() => {
    let isMounted = true;
    fetchSiteConfig(language).then((data) => {
      if (isMounted && data && data.profile) {
        setProfile(data.profile);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [language]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  return (
    <header className="bg-[var(--bg-surface)] border-b border-[var(--border-muted)] py-4 px-4 sm:px-6">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Left: State Emblem, Panchayat Identity, and Codes */}
        <div className="flex items-center gap-4 w-full md:w-auto">
          {/* Emblem representation / placeholder */}
          <Link
            href="/"
            aria-label={`${t.header.panchayatOffice} - ${t.nav.home}`}
            className="shrink-0 flex items-center justify-center w-14 h-14 rounded-full bg-[var(--bg-muted)] border-2 border-[var(--brand-saffron)] text-[var(--brand-navy)] font-bold text-xs text-center p-1 leading-tight hover:opacity-90 focus-visible:outline-2"
          >
            <span className="sr-only">{t.header.stateEmblemAlt}</span>
            <div className="flex flex-col items-center">
              <span className="text-[10px] text-[var(--brand-saffron)]">🏛️</span>
              <span className="text-[9px] uppercase font-bold tracking-tighter">राजमुद्रा</span>
            </div>
          </Link>

          {/* Panchayat Names & Statutory Codes */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-bold text-[var(--text-primary)] tracking-tight">
                {profile?.panchayat_name || t.header.panchayatOffice}
              </h1>
            </div>
            <p className="text-sm font-medium text-[var(--text-secondary)] mt-0.5">
              {profile ? (
                <span>
                  {t.header.talukaTitle} {profile.taluka_name}, {t.header.districtTitle} {profile.district_name}
                </span>
              ) : (
                <span>
                  {t.header.talukaTitle} [तालुका नाव प्रलंबित], {t.header.districtTitle} [जिल्हा नाव प्रलंबित]
                </span>
              )}
            </p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--text-muted)] mt-1">
              <span className="inline-flex items-center gap-1 font-mono bg-[var(--bg-muted)] px-1.5 py-0.5 rounded">
                <span className="font-sans font-medium">{t.header.lgdCodeLabel}:</span>
                <span className={profile?.lgd_code ? "text-emerald-700 dark:text-emerald-400 font-semibold" : "text-amber-700 dark:text-amber-400 font-semibold"}>
                  {profile?.lgd_code || '[Pending]'}
                </span>
              </span>
              <span className="inline-flex items-center gap-1 font-mono bg-[var(--bg-muted)] px-1.5 py-0.5 rounded">
                <span className="font-sans font-medium">{t.header.censusCodeLabel}:</span>
                <span className={profile?.census_code ? "text-emerald-700 dark:text-emerald-400 font-semibold" : "text-amber-700 dark:text-amber-400 font-semibold"}>
                  {profile?.census_code || '[Pending]'}
                </span>
              </span>
            </div>
          </div>
        </div>

        {/* Right: Quick Search Form & Official Seal Placeholder */}
        <div className="flex items-center gap-3 w-full md:w-auto justify-end">
          <form
            onSubmit={handleSearchSubmit}
            role="search"
            aria-label={t.header.searchButton}
            className="flex items-center w-full md:w-64 relative"
          >
            <label htmlFor="header-search-input" className="sr-only">
              {t.header.searchPlaceholder}
            </label>
            <input
              id="header-search-input"
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t.header.searchPlaceholder}
              className="w-full bg-[var(--bg-muted)] border border-[var(--border-primary)] rounded-l-md px-3 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus-visible:outline-2"
            />
            <button
              type="submit"
              className="bg-[var(--brand-navy)] text-white text-xs font-semibold px-3 py-1.5 rounded-r-md hover:bg-[var(--brand-navy-dark)] transition-colors focus-visible:outline-2"
            >
              {t.header.searchButton}
            </button>
          </form>

          {/* Official Seal Placeholder / Dynamic Path */}
          <div
            title={t.header.sealPlaceholder}
            aria-label={t.header.sealPlaceholder}
            className="hidden lg:flex flex-col items-center justify-center w-12 h-12 rounded-full border border-dashed border-[var(--border-primary)] bg-[var(--bg-muted)] text-[9px] text-[var(--text-muted)] text-center p-1 shrink-0"
          >
            <span>📜</span>
            <span className="text-[8px] leading-tight">
              {profile?.official_seal_asset_path ? 'मुद्रित' : 'शिक्का'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
