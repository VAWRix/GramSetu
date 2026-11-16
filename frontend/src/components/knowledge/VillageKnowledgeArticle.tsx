'use client';

import React, { useState, useMemo } from 'react';
import { PublicPageItem, VillageKnowledgeSection, VillageKnowledgeReference, PanchayatProfile } from '@/lib/types';
import { SafeMarkdownRenderer } from '@/components/ui/SafeMarkdownRenderer';
import { Badge } from '@/components/ui/Badge';
import { useLanguage } from '@/context/LanguageContext';

interface VillageKnowledgeArticleProps {
  page: PublicPageItem;
  profile?: PanchayatProfile | null;
  language: string;
}

export function VillageKnowledgeArticle({ page, profile, language }: VillageKnowledgeArticleProps) {
  const { t } = useLanguage();
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSection, setActiveSection] = useState<string>('');
  const [sealLoadError, setSealLoadError] = useState(false);

  // Fallback detection: if page is returned via fallback or page's language doesn't match requested language
  const isFallbackLanguage = Boolean(page.is_fallback || (page.language_code && page.language_code !== language));

  const sections: VillageKnowledgeSection[] = useMemo(() => {
    if (page.sections_data && page.sections_data.length > 0) {
      return page.sections_data;
    }
    // Fallback: build a section from body_markdown if no structured sections exist
    return [
      {
        key: 'overview',
        title_mr: '१. सर्वसाधारण माहिती व आढावा (General Overview)',
        title_hi: '1. सामान्य विवरण एवं अवलोकन (General Overview)',
        title_en: '1. General Overview',
        order: 1,
        body_markdown: page.body_markdown || page.summary || '',
        data_year: '2024',
        verification_status: 'verified',
        references: [1],
      },
    ];
  }, [page.sections_data, page.body_markdown, page.summary]);

  const references: VillageKnowledgeReference[] = useMemo(() => {
    if (page.references_data && page.references_data.length > 0) {
      return page.references_data;
    }
    return [
      {
        id: 1,
        ref_number: 1,
        source_title: language === 'en'
          ? 'Local Government Directory (LGD)'
          : language === 'hi'
          ? 'स्थानीय निकाय निर्देशिका (LGD)'
          : 'स्थानिक स्वराज्य संस्था निर्देशिका (LGD)',
        source_url: 'https://lgdirectory.gov.in/',
        organization: language === 'en'
          ? 'Ministry of Panchayati Raj, Government of India'
          : language === 'hi'
          ? 'पंचायती राज मंत्रालय, भारत सरकार'
          : 'पंचायती राज मंत्रालय, भारत सरकार',
        retrieval_date: '2026-11-15',
        data_year: '2024',
        verification_status: 'verified',
      },
    ];
  }, [page.references_data, language]);

  // Helper to get localized title for a section
  const getSectionTitle = (s: VillageKnowledgeSection): string => {
    if (language === 'en') {
      return s.title_en || s.title || s.title_mr || '';
    }
    if (language === 'hi') {
      return s.title_hi || s.title_mr || s.title_en || s.title || '';
    }
    return s.title_mr || s.title || s.title_en || '';
  };

  // Helper to get localized body markdown for a section
  const getSectionBody = (s: VillageKnowledgeSection): string => {
    if (language === 'en' && s.body_markdown_en) {
      return s.body_markdown_en;
    }
    if (language === 'hi' && s.body_markdown_hi) {
      return s.body_markdown_hi;
    }
    if (language === 'mr' && s.body_markdown_mr) {
      return s.body_markdown_mr;
    }
    return s.body_markdown || '';
  };

  // Filter sections by search query
  const filteredSections = useMemo(() => {
    if (!searchQuery.trim()) return sections;
    const q = searchQuery.toLowerCase();
    return sections.filter((s) => {
      const title = getSectionTitle(s).toLowerCase();
      const body = getSectionBody(s).toLowerCase();
      return title.includes(q) || body.includes(q);
    });
  }, [sections, searchQuery, language]);

  const scrollToSection = (key: string) => {
    setActiveSection(key);
    const element = document.getElementById(key === 'references' ? 'article-references' : `section-${key}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const handlePrint = () => {
    if (typeof window !== 'undefined') {
      window.print();
    }
  };

  return (
    <article id="knowledge-article" className="space-y-6 text-[var(--text-primary)]">
      {/* Fallback Notice if requested language is unavailable */}
      {isFallbackLanguage && (
        <div
          role="status"
          aria-live="polite"
          className="p-4 bg-amber-50 border border-amber-300 text-amber-950 rounded-xl shadow-xs flex items-start gap-3"
        >
          <span className="text-xl shrink-0" aria-hidden="true">⚠️</span>
          <div className="space-y-1 text-xs">
            <p className="font-bold">
              {t.about.fallbackNotice}
            </p>
            <p className="text-amber-800 text-[11px]">
              {language === 'en'
                ? 'Official English translation is being finalized by administrative authority. The verified Marathi version is provided as statutory reference.'
                : language === 'hi'
                ? 'इस लेख का आधिकारिक हिंदी अनुवाद प्रशासनिक स्तर पर तैयार किया जा रहा है। आधिकारिक संदर्भ हेतु मराठी मूल सामग्री उपलब्ध कराई गई है।'
                : 'निवडलेल्या भाषेतील अधिकृत भाषांतर प्रक्रिया सुरू आहे.'}
            </p>
          </div>
        </div>
      )}

      {/* Official Light Theme Article Header Card */}
      <div className="bg-[var(--bg-surface)] border border-[var(--border-muted)] border-l-4 border-l-[var(--brand-navy)] rounded-xl p-5 sm:p-7 shadow-xs print:border-b-2 print:border-black print:p-0 print:shadow-none">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-blue-50 text-[var(--brand-navy)] border border-blue-200 uppercase tracking-wider">
                {t.about.encyclopediaBadge}
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[var(--bg-muted)] text-[var(--text-secondary)] border border-[var(--border-muted)] print:hidden">
                LGD: {profile?.lgd_code || '549493'}
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[var(--bg-muted)] text-[var(--text-secondary)] border border-[var(--border-muted)] print:hidden">
                Census: {profile?.census_code || '549493'}
              </span>
              {isFallbackLanguage && (
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-900 border border-amber-300">
                  {t.about.fallbackBadge}
                </span>
              )}
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold text-[var(--text-primary)] tracking-tight">
              {page.title}
            </h1>

            <p className="text-xs sm:text-sm text-[var(--text-secondary)] max-w-3xl leading-relaxed">
              {page.summary || (language === 'en'
                ? 'Statutory Local Government Information Portal according to Maharashtra Government standards.'
                : language === 'hi'
                ? 'महाराष्ट्र शासन के नियमों के अनुसार प्रमाणित स्थानीय निकाय अभिलेख।'
                : 'महाराष्ट्र शासनाच्या नियमांनुसार प्रमाणित स्थानिक स्वराज्य नोंद.')}
            </p>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-center shrink-0 print:hidden">
            <button
              type="button"
              onClick={handlePrint}
              aria-label={t.about.printArticle}
              title={t.about.printArticle}
              className="p-2 bg-[var(--bg-muted)] hover:bg-slate-200 text-[var(--text-primary)] rounded-lg text-xs font-semibold border border-[var(--border-muted)] transition-colors inline-flex items-center gap-1.5 shadow-xs"
            >
              <span aria-hidden="true">🖨️</span>
              <span className="hidden sm:inline">{t.about.printArticle}</span>
            </button>
          </div>
        </div>

        {/* Administrative Metadata Sub-bar */}
        <div className="mt-4 pt-3.5 border-t border-[var(--border-muted)] flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--text-secondary)]">
          <div className="flex flex-wrap items-center gap-2">
            <span aria-hidden="true">🏛️</span>
            <span>{t.about.localAdmin}: <strong>{profile?.panchayat_name || (language === 'en' ? 'Narayangaon Gram Panchayat' : language === 'hi' ? 'नारायणगांव ग्राम पंचायत' : 'नारायणगाव ग्रामपंचायत')}</strong></span>
            <span>•</span>
            <span>{t.about.taluka}: <strong>{profile?.taluka_name || (language === 'en' ? 'Paithan' : 'पैठण')}</strong></span>
            <span>•</span>
            <span>{t.about.district}: <strong>{profile?.district_name || (language === 'en' ? 'Chhatrapati Sambhajinagar' : language === 'hi' ? 'छत्रपति संभाजीनगर' : 'छत्रपती संभाजीनगर')}</strong></span>
          </div>
          <div>
            {t.about.lastUpdated}: <strong>{page.updated_at ? page.updated_at.split('T')[0] : '2026-11-15'}</strong>
          </div>
        </div>
      </div>

      {/* Main Grid: Three-Column Layout (Left TOC / Center Article / Right Governance Information) */}
      <div className="grid grid-cols-1 md:grid-cols-12 lg:grid-cols-12 gap-6 items-start">
        {/* 1. Left Column: Interactive Table of Contents (Sticky on Desktop) */}
        <aside className="col-span-1 md:col-span-4 lg:col-span-3 space-y-4 print:hidden">
          <div id="article-toc" className="bg-[var(--bg-surface)] border border-[var(--border-muted)] rounded-xl p-4 lg:sticky lg:top-4 shadow-xs space-y-3">
            <div className="flex items-center justify-between border-b border-[var(--border-muted)] pb-2.5">
              <h2 className="text-xs font-bold text-[var(--text-primary)] flex items-center gap-1.5 uppercase tracking-wider">
                <span aria-hidden="true">📑</span>
                <span>{t.about.contentsTitle}</span>
              </h2>
              <span className="text-[10px] text-[var(--text-muted)] font-mono">
                {filteredSections.length} {t.about.sectionsCount}
              </span>
            </div>

            {/* In-article search input */}
            <div className="relative">
              <input
                id="section-filter"
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t.about.searchPlaceholder}
                className="w-full text-xs bg-[var(--bg-surface)] border border-[var(--border-primary)] rounded-lg px-2.5 py-1.5 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  aria-label={t.about.clearSearch}
                  className="absolute right-2 top-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] text-xs"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Clickable Section Links */}
            <nav id="article-toc-nav" className="max-h-[60vh] overflow-y-auto space-y-1 pr-1 text-xs" aria-label="Table of Contents">
              {filteredSections.map((sec) => {
                const title = getSectionTitle(sec);
                const isActive = activeSection === sec.key;
                return (
                  <button
                    key={sec.key}
                    type="button"
                    onClick={() => scrollToSection(sec.key)}
                    className={`w-full text-left px-2.5 py-1.5 rounded-md transition-colors block truncate text-[11px] ${
                      isActive
                        ? 'bg-blue-50 text-[var(--brand-navy)] font-bold border-l-2 border-[var(--brand-navy)]'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]'
                    }`}
                    title={title}
                  >
                    {sec.order ? `${sec.order}. ` : ''}{title}
                  </button>
                );
              })}

              <button
                type="button"
                onClick={() => scrollToSection('references')}
                className="w-full text-left px-2.5 py-1.5 rounded-md text-[11px] text-[var(--text-muted)] hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] font-medium block border-t border-[var(--border-muted)] mt-2 pt-2"
              >
                {t.about.referencesTitle}
              </button>
            </nav>
          </div>
        </aside>

        {/* 2. Center Column: Main Article Content */}
        <div className="col-span-1 md:col-span-8 lg:col-span-6 space-y-6 min-w-0">
          {/* Article Lead / Introduction Section */}
          <div className="bg-[var(--bg-surface)] border border-[var(--border-muted)] rounded-xl p-5 sm:p-6 shadow-xs space-y-3">
            <h2 className="text-base sm:text-lg font-bold text-[var(--text-primary)] border-b border-[var(--border-muted)] pb-2">
              {t.about.overviewHeading}
            </h2>
            <div className="text-xs sm:text-sm text-[var(--text-secondary)] leading-relaxed space-y-2">
              <SafeMarkdownRenderer content={page.body_markdown || page.summary || ''} />
            </div>
          </div>

          {/* Structured Sections Loop — Content-Driven Sizing without Fixed Heights */}
          <div className="space-y-5">
            {filteredSections.map((sec) => {
              const secTitle = getSectionTitle(sec);
              const secBody = getSectionBody(sec);

              return (
                <section
                  key={sec.key}
                  id={`section-${sec.key}`}
                  className="bg-[var(--bg-surface)] border border-[var(--border-muted)] rounded-xl p-5 sm:p-6 shadow-xs scroll-mt-6 transition-all hover:border-[var(--border-primary)] space-y-3.5"
                >
                  {/* Section Header */}
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-muted)] pb-2.5">
                    <h2 className="text-base sm:text-lg font-bold text-[var(--text-primary)] flex items-center gap-2">
                      <span className="text-[var(--brand-navy)]" aria-hidden="true">§</span>
                      <span>{secTitle}</span>
                    </h2>

                    <div className="flex items-center gap-1.5 shrink-0">
                      {sec.data_year && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-[var(--bg-muted)] text-[var(--text-secondary)] border border-[var(--border-muted)]">
                          {t.about.year}: {sec.data_year}
                        </span>
                      )}
                      {sec.verification_status === 'verified' ? (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-emerald-50 text-emerald-900 border border-emerald-300">
                          {t.about.verifiedBadge}
                        </span>
                      ) : (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-amber-50 text-amber-900 border border-amber-300">
                          {t.about.pendingBadge}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Section Body */}
                  <div className="text-xs sm:text-sm text-[var(--text-secondary)] leading-relaxed space-y-2.5">
                    <SafeMarkdownRenderer content={secBody} />
                  </div>

                  {/* Section Footnote References */}
                  {sec.references && sec.references.length > 0 && (
                    <div className="pt-2 text-[11px] text-[var(--text-muted)] flex items-center gap-1.5">
                      <span>{t.about.references}:</span>
                      {sec.references.map((refId) => (
                        <button
                          key={refId}
                          type="button"
                          onClick={() => scrollToSection('references')}
                          className="font-bold text-[var(--brand-navy)] hover:underline px-1.5 py-0.5 bg-blue-50 rounded border border-blue-200 text-xs"
                          title={`Go to reference [${refId}]`}
                        >
                          [{refId}]
                        </button>
                      ))}
                    </div>
                  )}
                </section>
              );
            })}
          </div>

          {/* References & Official Sources Section */}
          <section
            id="article-references"
            data-testid="article-references"
            className="bg-[var(--bg-surface)] border border-[var(--border-muted)] rounded-xl p-5 sm:p-6 shadow-xs scroll-mt-6 space-y-4"
          >
            <div className="border-b border-[var(--border-muted)] pb-2.5">
              <h2 className="text-base sm:text-lg font-bold text-[var(--text-primary)] flex items-center gap-2">
                <span aria-hidden="true">📚</span>
                <span>{t.about.referencesTitle}</span>
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                {t.about.referencesSubtitle}
              </p>
            </div>

            <ol className="list-none space-y-3 text-xs">
              {references.map((ref) => (
                <li
                  key={ref.id}
                  className="p-3.5 bg-[var(--bg-muted)] rounded-lg border border-[var(--border-muted)] flex flex-col sm:flex-row sm:items-center justify-between gap-2.5"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-[var(--brand-navy)] font-mono text-xs">
                        [{ref.ref_number || ref.id}]
                      </span>
                      <span className="font-semibold text-[var(--text-primary)]">
                        {ref.source_title}
                      </span>
                    </div>
                    <p className="text-[11px] text-[var(--text-muted)]">
                      {t.about.publishedBy}: <strong>{ref.organization}</strong> • {t.about.retrievalDate}: {ref.retrieval_date} {ref.data_year ? `• ${t.about.statisticalYear}: ${ref.data_year}` : ''}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 self-start sm:self-center shrink-0">
                    <Badge variant={ref.verification_status === 'verified' ? 'success' : 'warning'}>
                      {ref.verification_status === 'verified'
                        ? (language === 'en' ? 'Verified' : language === 'hi' ? 'सत्यापित' : 'पडताळणीकृत')
                        : (language === 'en' ? 'Pending' : language === 'hi' ? 'लंबित' : 'प्रलंबित')}
                    </Badge>
                    {ref.source_url && (
                      <a
                        href={ref.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-2.5 py-1 bg-white hover:bg-slate-100 text-[var(--brand-navy)] rounded text-[11px] font-semibold inline-flex items-center gap-1 border border-[var(--border-primary)] transition-colors shadow-xs"
                      >
                        <span>{t.about.viewSource}</span>
                        <span aria-hidden="true">↗</span>
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </section>

          {/* Quick Citizen Navigation Card */}
          <div className="bg-[var(--bg-surface)] border border-[var(--border-muted)] p-5 rounded-xl text-xs space-y-3 shadow-xs print:hidden">
            <h3 className="font-bold text-[var(--text-primary)] flex items-center gap-2">
              <span aria-hidden="true">🔗</span>
              <span>{t.about.relatedPortals}</span>
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-center font-semibold">
              <a href="/notices" className="p-2.5 bg-[var(--bg-muted)] hover:bg-blue-50 hover:text-[var(--brand-navy)] hover:border-blue-300 rounded-lg border border-[var(--border-muted)] transition-all shadow-xs">
                📢 {language === 'en' ? 'Notices' : language === 'hi' ? 'सूचनाएं' : 'सूचना व जाहीरनामे'}
              </a>
              <a href="/documents" className="p-2.5 bg-[var(--bg-muted)] hover:bg-blue-50 hover:text-[var(--brand-navy)] hover:border-blue-300 rounded-lg border border-[var(--border-muted)] transition-all shadow-xs">
                📄 {language === 'en' ? 'Orders & Circulars' : language === 'hi' ? 'शासनादेश' : 'शासकीय आदेश व ठराव'}
              </a>
              <a href="/schemes" className="p-2.5 bg-[var(--bg-muted)] hover:bg-blue-50 hover:text-[var(--brand-navy)] hover:border-blue-300 rounded-lg border border-[var(--border-muted)] transition-all shadow-xs">
                🎯 {language === 'en' ? 'Welfare Schemes' : language === 'hi' ? 'कल्याणकारी योजनाएं' : 'कल्याणकारी योजना'}
              </a>
              <a href="/gallery" className="p-2.5 bg-[var(--bg-muted)] hover:bg-blue-50 hover:text-[var(--brand-navy)] hover:border-blue-300 rounded-lg border border-[var(--border-muted)] transition-all shadow-xs">
                🖼️ {language === 'en' ? 'Photo Gallery' : language === 'hi' ? 'चित्र दीर्घा' : 'छायाचित्र दालन'}
              </a>
            </div>
          </div>
        </div>

        {/* 3. Right Column: Local Governance Information Card */}
        <aside
          aria-label={t.about.infoboxBadge}
          className="col-span-1 md:col-span-12 lg:col-span-3 space-y-4"
        >
          <div className="bg-[var(--bg-surface)] border border-[var(--border-muted)] rounded-xl p-4 shadow-xs text-xs space-y-3 lg:sticky lg:top-4">
            <div className="text-center pb-2.5 border-b border-[var(--border-muted)]">
              <span className="text-[10px] font-bold text-[var(--brand-navy)] uppercase tracking-widest block">
                {t.about.infoboxBadge}
              </span>
              <h3 className="text-base font-extrabold text-[var(--text-primary)] mt-0.5">
                {language === 'en' ? 'Narayangaon' : language === 'hi' ? 'नारायणगांव' : 'नारायणगाव'}
              </h3>
              <p className="text-[11px] text-[var(--text-muted)]">
                {language === 'en'
                  ? 'Gram Panchayat, Paithan, Chhatrapati Sambhajinagar'
                  : language === 'hi'
                  ? 'ग्राम पंचायत, पैठण, छत्रपति संभाजीनगर'
                  : 'ग्रामपंचायत, पैठण, छत्रपती संभाजीनगर'}
              </p>
            </div>

            {/* Infobox Visual Seal/Illustration with Accessible Alt Text */}
            <div className="bg-[var(--bg-muted)] rounded-lg flex flex-col items-center justify-center p-4 text-center border border-[var(--border-muted)] space-y-1.5">
              {profile?.official_seal_asset_path && !sealLoadError ? (
                <img
                  src={profile.official_seal_asset_path}
                  alt={language === 'en' ? 'Official Emblem of Government of Maharashtra' : 'महाराष्ट्र शासन अधिकृत राजमुद्रा'}
                  className="w-16 h-16 object-contain"
                  onError={() => setSealLoadError(true)}
                />
              ) : (
                <div
                  className="w-14 h-14 rounded-full border-2 border-[var(--brand-navy)] flex items-center justify-center bg-white text-2xl shadow-xs"
                  aria-label={t.about.infoboxSealText}
                  title={t.about.infoboxSealText}
                >
                  <span aria-hidden="true">🏛️</span>
                </div>
              )}
              <span className="text-[10px] font-bold text-[var(--text-secondary)] leading-tight">
                {t.about.infoboxSealText}
              </span>
              <span className="text-[9px] text-[var(--text-muted)] font-mono">
                LGD Code: {profile?.lgd_code || '549493'}
              </span>
            </div>

            {/* Fact Table */}
            <table className="w-full text-[11px] border-collapse">
              <tbody className="divide-y divide-[var(--border-muted)]">
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] w-2/5 break-words">
                    {t.about.countryState}:
                  </th>
                  <td className="py-2 text-[var(--text-primary)] font-medium break-words">
                    {t.about.countryStateVal}
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] break-words">
                    {t.about.district}:
                  </th>
                  <td className="py-2 text-[var(--text-primary)] font-medium break-words">
                    {profile?.district_name || (language === 'en' ? 'Chhatrapati Sambhajinagar' : language === 'hi' ? 'छत्रपति संभाजीनगर' : 'छत्रपती संभाजीनगर')}
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] break-words">
                    {t.about.taluka}:
                  </th>
                  <td className="py-2 text-[var(--text-primary)] font-medium break-words">
                    {profile?.taluka_name || (language === 'en' ? 'Paithan (10 km)' : 'पैठण (१० किमी)')}
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] break-words">
                    {t.about.lgdCode}:
                  </th>
                  <td className="py-2 text-[var(--brand-navy)] font-mono font-bold break-words">
                    {profile?.lgd_code || '549493'}
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] break-words">
                    {t.about.censusCode}:
                  </th>
                  <td className="py-2 text-[var(--text-primary)] font-mono break-words">
                    {profile?.census_code || '549493'}
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] break-words">
                    {t.about.totalArea}:
                  </th>
                  <td className="py-2 text-[var(--text-primary)] font-medium break-words">
                    {t.about.totalAreaVal}
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] break-words">
                    {t.about.pincode}:
                  </th>
                  <td className="py-2 text-[var(--text-primary)] font-mono break-words">
                    431148
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] break-words">
                    {t.about.riverBasin}:
                  </th>
                  <td className="py-2 text-[var(--text-primary)] font-medium break-words">
                    {t.about.riverBasinVal}
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] break-words">
                    {t.about.administration}:
                  </th>
                  <td className="py-2 text-[var(--text-primary)] font-medium break-words">
                    {t.about.administrationVal}
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold text-[var(--text-muted)] break-words">
                    {t.about.officeContact}:
                  </th>
                  <td className="py-2 text-[var(--text-primary)] font-mono text-[10px] break-words">
                    {profile?.contact_phone || '02431-223022'}
                  </td>
                </tr>
              </tbody>
            </table>

            <div className="pt-2 border-t border-[var(--border-muted)] text-[10px] text-[var(--text-muted)] text-center leading-normal">
              {t.about.infoSource}
            </div>
          </div>
        </aside>
      </div>
    </article>
  );
}
