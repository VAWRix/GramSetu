'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useLanguage } from '@/context/LanguageContext';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PlaceholderNotice } from '@/components/ui/PlaceholderNotice';
import { fetchSearchResults } from '@/lib/api';
import { SearchResultItem } from '@/lib/types';

function SearchContent() {
  const { t, language } = useLanguage();
  const searchParams = useSearchParams();
  const router = useRouter();

  const currentQ = searchParams.get('q') || '';
  const [query, setQuery] = useState(currentQ);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(Boolean(currentQ));
  const [hasSearched, setHasSearched] = useState(Boolean(currentQ));

  useEffect(() => {
    if (currentQ) {
      let isMounted = true;
      fetchSearchResults(currentQ, language).then((data) => {
        if (isMounted) {
          if (data && Array.isArray(data.results)) {
            setResults(data.results as SearchResultItem[]);
            setCount(data.count || 0);
          } else {
            setResults([]);
            setCount(0);
          }
          setLoading(false);
          setHasSearched(true);
        }
      });

      return () => {
        isMounted = false;
      };
    }
  }, [currentQ, language]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      setLoading(true);
      router.push(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  const getContentTypeDisplay = (type: string) => {
    switch (type) {
      case 'notice':
        return t.search.typeNotice;
      case 'document':
        return t.search.typeDocument;
      case 'event':
        return t.search.typeEvent;
      case 'scheme':
        return t.search.typeScheme;
      case 'page':
        return t.search.typePage;
      default:
        return type;
    }
  };

  return (
    <div className="space-y-6">
      <header className="border-b border-[var(--border-muted)] pb-4">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          {t.search.title}
        </h1>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          {t.search.subtitle}
        </p>
      </header>

      {/* Search Input Box */}
      <form onSubmit={handleSearchSubmit} className="flex gap-2 max-w-2xl">
        <label htmlFor="search-page-input" className="sr-only">
          {t.search.inputPlaceholder}
        </label>
        <input
          id="search-page-input"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t.search.inputPlaceholder}
          className="flex-1 bg-[var(--bg-surface)] border border-[var(--border-primary)] rounded-md px-4 py-2.5 text-sm text-[var(--text-primary)] focus-visible:outline-2"
        />
        <button
          type="submit"
          className="bg-[var(--brand-navy)] text-white text-sm font-semibold px-6 py-2.5 rounded-md hover:bg-[var(--brand-navy-dark)] transition-colors focus-visible:outline-2"
        >
          {t.header.searchButton}
        </button>
      </form>

      {/* Search Output */}
      {loading ? (
        <div className="py-12 text-center text-xs text-[var(--text-muted)]">
          {t.search.searchingText}
        </div>
      ) : hasSearched ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)] border-b border-[var(--border-muted)] pb-2">
            <span>&ldquo;{query}&rdquo; — {t.search.resultsFound} <strong>{count}</strong></span>
            <span>{t.search.languageLabel} <strong>{language.toUpperCase()}</strong></span>
          </div>

          {results.length > 0 ? (
            <div className="space-y-3">
              {results.map((item, idx) => (
                <Card
                  key={idx}
                  title={item.title}
                  badge={<Badge variant="primary">{getContentTypeDisplay(item.content_type)}</Badge>}
                  footer={
                    <span className="text-[11px] text-[var(--text-muted)]">
                      {t.common.publishedDate}: {item.published_date || t.common.notAvailable}
                    </span>
                  }
                >
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed mb-2">
                    {item.summary}
                  </p>
                  {item.url && (
                    <a
                      href={item.url}
                      className="text-xs font-semibold text-[var(--brand-navy)] hover:underline inline-flex items-center gap-1"
                    >
                      {t.common.details} &rarr;
                    </a>
                  )}
                </Card>
              ))}
            </div>
          ) : (
            <PlaceholderNotice
              title={t.search.noResultsTitle}
              description={t.search.noResultsDesc}
            />
          )}
        </div>
      ) : (
        <PlaceholderNotice
          title={t.search.title}
          description={t.search.subtitle}
        />
      )}
    </div>
  );
}

export default function SearchPage() {
  const { t } = useLanguage();
  return (
    <Suspense fallback={<div className="py-12 text-center text-xs">{t.common.loading}</div>}>
      <SearchContent />
    </Suspense>
  );
}
