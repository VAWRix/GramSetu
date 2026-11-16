'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/context/LanguageContext';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PlaceholderNotice } from '@/components/ui/PlaceholderNotice';
import { Alert } from '@/components/ui/Alert';
import { fetchPublicSchemes } from '@/lib/api';
import { PublicSchemeItem } from '@/lib/types';

export default function SchemesPage() {
  const { t, language } = useLanguage();
  const [level, setLevel] = useState<string>('');
  const [schemes, setSchemes] = useState<PublicSchemeItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    fetchPublicSchemes(language, level).then((data) => {
      if (isMounted) {
        if (data && Array.isArray(data.results)) {
          setSchemes(data.results as PublicSchemeItem[]);
        } else {
          setSchemes([]);
        }
        setLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [language, level]);

  return (
    <div className="space-y-6">
      <header className="border-b border-[var(--border-muted)] pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            {t.schemes.title}
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t.schemes.subtitle}
          </p>
        </div>

        {/* Scheme level filter */}
        <div className="inline-flex rounded-md border border-[var(--border-primary)] p-0.5 bg-[var(--bg-muted)] text-xs">
          <button
            type="button"
            onClick={() => setLevel('')}
            className={`px-2.5 py-1 rounded font-medium transition-colors ${
              level === ''
                ? 'bg-[var(--brand-navy)] text-white shadow-xs'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {t.schemes.filterAll}
          </button>
          <button
            type="button"
            onClick={() => setLevel('state')}
            className={`px-2.5 py-1 rounded font-medium transition-colors ${
              level === 'state'
                ? 'bg-[var(--brand-navy)] text-white shadow-xs'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {t.schemes.filterState}
          </button>
          <button
            type="button"
            onClick={() => setLevel('central')}
            className={`px-2.5 py-1 rounded font-medium transition-colors ${
              level === 'central'
                ? 'bg-[var(--brand-navy)] text-white shadow-xs'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {t.schemes.filterCentral}
          </button>
        </div>
      </header>

      <Alert severity="info" title={t.schemes.policyTitle}>
        <p>
          {t.schemes.policyDesc}
        </p>
      </Alert>

      {loading ? (
        <div className="py-12 text-center text-xs text-[var(--text-muted)]">
          {t.common.loading}
        </div>
      ) : schemes.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {schemes.map((scheme) => (
            <Card
              key={scheme.id}
              title={
                <Link href={`/schemes/${scheme.slug}`} className="hover:underline text-[var(--brand-navy)]">
                  {scheme.title || scheme.scheme_name}
                </Link>
              }
              subtitle={`${scheme.scheme_level_display} • ${scheme.beneficiary_category_display || scheme.target_beneficiary_display || ''}`}
              badge={
                <div className="flex items-center gap-1.5">
                  {scheme.is_fallback && (
                    <span className="px-1.5 py-0.5 text-[10px] bg-slate-100 text-slate-600 rounded border border-slate-200">
                      {language === 'hi' ? 'मूल मराठी' : 'Marathi Record'}
                    </span>
                  )}
                  <Badge variant="primary">{scheme.scheme_level_display}</Badge>
                </div>
              }
              footer={
                <div className="flex items-center justify-between w-full pt-1">
                  <Link
                    href={`/schemes/${scheme.slug}`}
                    className="text-[var(--brand-navy)] font-semibold hover:underline inline-flex items-center gap-1 text-xs"
                  >
                    <span>{language === 'mr' ? 'तपशील पहा' : language === 'hi' ? 'विवरण देखें' : 'View Details'}</span>
                    <span aria-hidden="true">&rarr;</span>
                  </Link>
                  {scheme.official_guidelines_url ? (
                    <a
                      href={scheme.official_guidelines_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-slate-500 hover:text-slate-800 underline"
                    >
                      {t.schemes.guidelinesLink} &nearr;
                    </a>
                  ) : null}
                </div>
              }
            >
              <Link href={`/schemes/${scheme.slug}`} className="block hover:opacity-90">
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed line-clamp-3">
                  {scheme.short_description || scheme.short_summary}
                </p>
              </Link>
            </Card>
          ))}
        </div>
      ) : (
        <PlaceholderNotice
          title={t.schemes.emptyTitle}
          description={t.schemes.emptyDesc}
        />
      )}
    </div>
  );
}
