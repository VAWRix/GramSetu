'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/context/LanguageContext';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PlaceholderNotice } from '@/components/ui/PlaceholderNotice';
import { Alert } from '@/components/ui/Alert';
import { fetchPublicDocuments, getApiBaseUrl } from '@/lib/api';
import { PublicDocumentItem } from '@/lib/types';

export default function DocumentsPage() {
  const { t, language } = useLanguage();
  const [documents, setDocuments] = useState<PublicDocumentItem[]>([]);
  const [category, setCategory] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let isMounted = true;

    fetchPublicDocuments(language, category).then((data) => {
      if (isMounted) {
        if (data && Array.isArray(data.results)) {
          setDocuments(data.results);
        } else {
          setDocuments([]);
        }
        setLoading(false);
      }
    }).catch(() => {
      if (isMounted) {
        setDocuments([]);
        setLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [language, category]);

  const categories = [
    { value: '', label: t.documents.catAll },
    { value: 'resolution', label: language === 'mr' ? 'ठराव व इतिवृत्त' : language === 'hi' ? 'प्रस्ताव एवं कार्यवृत्त' : 'Resolutions & Minutes' },
    { value: 'tender', label: language === 'mr' ? 'निविदा' : language === 'hi' ? 'निविदाएं' : 'Tenders' },
    { value: 'budget', label: language === 'mr' ? 'अंदाजपत्रक व लेखा' : language === 'hi' ? 'बजट एवं ऑडिट' : 'Budget & Audit' },
    { value: 'citizen_charter', label: language === 'mr' ? 'नागरिक सनद' : language === 'hi' ? 'नागरिक अधिकार पत्र' : 'Citizen Charter' },
    { value: 'statutory_report', label: language === 'mr' ? 'प्रशासकीय अहवाल' : language === 'hi' ? 'प्रशासनिक रिपोर्ट' : 'Statutory Reports' },
  ];

  const formatFileSize = (bytes: number): string => {
    if (!bytes || bytes === 0) return '0 KB';
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    return `${(kb / 1024).toFixed(2)} MB`;
  };

  return (
    <div className="space-y-6">
      <header className="border-b border-[var(--border-muted)] pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            {t.documents.title}
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t.documents.subtitle}
          </p>
        </div>
        <Link
          href="/search?type=document"
          className="inline-flex items-center text-xs text-[var(--brand-navy)] hover:underline font-semibold"
        >
          🔍 {t.documents.searchLink} &rarr;
        </Link>
      </header>

      <Alert severity="info" title={t.documents.policyTitle}>
        <p>
          {t.documents.policyDesc}
        </p>
      </Alert>

      {/* Category Filter Pills */}
      <div className="flex flex-wrap gap-1.5 bg-[var(--bg-surface)] p-2.5 rounded-lg border border-[var(--border-muted)] text-xs">
        {categories.map((cat) => (
          <button
            key={cat.value}
            type="button"
            onClick={() => {
              setCategory(cat.value);
              setLoading(true);
            }}
            className={`px-3 py-1 rounded transition-colors ${
              category === cat.value
                ? 'bg-[var(--brand-navy)] text-white font-semibold shadow-xs'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="py-12 text-center text-xs text-[var(--text-muted)]">
          {t.common.loading}
        </div>
      ) : documents.length > 0 ? (
        <div className="space-y-4">
          <div className="text-xs text-[var(--text-muted)] px-1">
            {t.documents.totalDocuments} <strong>{documents.length}</strong>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {documents.map((doc) => (
              <Card
                key={doc.id}
                title={doc.title}
                subtitle={`${doc.category_display} • ${t.common.referenceNo}: ${doc.reference_number || `[${t.common.notAvailable}]`}`}
                badge={
                  <div className="flex items-center gap-1.5">
                    {doc.is_fallback && (
                      <span className="px-1.5 py-0.5 text-[10px] bg-slate-100 text-slate-600 rounded border border-slate-200">
                        {language === 'hi' ? 'मूल मराठी' : 'Marathi Record'}
                      </span>
                    )}
                    <Badge variant="primary">{t.documents.versionLabel} v{doc.version_number}</Badge>
                  </div>
                }
                footer={
                  <div className="flex items-center justify-between pt-2">
                    <span className="text-[11px] text-[var(--text-muted)]">
                      {formatFileSize(doc.file_size_bytes)}
                    </span>
                    <a
                      href={`${getApiBaseUrl()}${doc.download_url}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold bg-[var(--brand-navy)] text-white hover:bg-[var(--brand-navy-dark)] transition-colors focus-visible:outline-2"
                    >
                      <span>⬇️</span>
                      <span>{t.documents.downloadButton}</span>
                    </a>
                  </div>
                }
              >
                <div className="space-y-2 text-xs text-[var(--text-secondary)]">
                  {doc.issuing_department && (
                    <p><strong>{t.documents.issuingDept}</strong> {doc.issuing_department}</p>
                  )}
                  {doc.issue_date && (
                    <p><strong>{t.documents.issueDate}</strong> {doc.issue_date}</p>
                  )}
                  {doc.description && (
                    <p className="line-clamp-2 leading-relaxed">{doc.description}</p>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      ) : (
        <PlaceholderNotice
          title={t.documents.emptyTitle}
          description={t.documents.emptyDesc}
        />
      )}
    </div>
  );
}
