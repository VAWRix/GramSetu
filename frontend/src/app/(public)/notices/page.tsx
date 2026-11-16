'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/context/LanguageContext';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PlaceholderNotice } from '@/components/ui/PlaceholderNotice';
import { Alert } from '@/components/ui/Alert';
import { fetchPublicNotices, fetchNoticeDetail } from '@/lib/api';
import { PublicNoticeItem } from '@/lib/types';

function getNoticeDescription(notice: PublicNoticeItem, lang: string): string {
  const desc = (notice.description || notice.summary || '').trim();
  if (desc) return desc;
  if (lang === 'mr') return 'तपशील पाहण्यासाठी सूचना उघडा';
  if (lang === 'hi') return 'विवरण देखने के लिए सूचना खोलें';
  return 'Open notice to view full details';
}

function getViewNoticeLabel(lang: string): string {
  if (lang === 'mr') return 'संपूर्ण सूचना पहा';
  if (lang === 'hi') return 'पूरी सूचना देखें';
  return 'View Notice';
}

function getCloseLabel(lang: string): string {
  if (lang === 'mr') return 'बंद करा';
  if (lang === 'hi') return 'बंद करें';
  return 'Close';
}

function formatDeadlineDisplay(deadlineIso: string, lang: string): { label: string; text: string; isPassed: boolean; statusText: string } {
  const d = new Date(deadlineIso);
  const isPassed = d.getTime() < Date.now();
  const formatted = d.toLocaleString(lang === 'en' ? 'en-IN' : 'mr-IN', {
    timeZone: 'Asia/Kolkata',
    dateStyle: 'medium',
    timeStyle: 'short',
  });

  let label = 'अंतिम मुदत / वेळ';
  let statusText = isPassed ? 'मुदत संपली' : 'मुदत सुरू';

  if (lang === 'hi') {
    label = 'अंतिम तिथि व समय';
    statusText = isPassed ? 'समय सीमा समाप्त' : 'समय सीमा सक्रिय';
  } else if (lang === 'en') {
    label = 'Deadline';
    statusText = isPassed ? 'Deadline Passed' : 'Active Deadline';
  }

  return { label, text: formatted, isPassed, statusText };
}

export default function NoticesPage() {
  const { t, language } = useLanguage();
  const [notices, setNotices] = useState<PublicNoticeItem[]>([]);
  const [noticeType, setNoticeType] = useState<string>('');
  const [urgency, setUrgency] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);

  // Detail Modal State
  const [detailNotice, setDetailNotice] = useState<PublicNoticeItem | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);

  async function handleOpenNotice(item: PublicNoticeItem) {
    setDetailNotice(item);
    setLoadingDetail(true);
    try {
      const full = await fetchNoticeDetail(item.id, language);
      if (full) {
        setDetailNotice(full);
      }
    } catch {
      // Keep basic item info if detail fetch fails
    } finally {
      setLoadingDetail(false);
    }
  }

  function handleCloseNotice() {
    setDetailNotice(null);
    setLoadingDetail(false);
  }

  // Keyboard accessibility: Close on Escape key
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && detailNotice) {
        handleCloseNotice();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [detailNotice]);

  useEffect(() => {
    let isMounted = true;

    fetchPublicNotices(language, noticeType, urgency, page).then((data) => {
      if (isMounted) {
        if (data && Array.isArray(data.results)) {
          setNotices(data.results);
          setTotalPages(data.total_pages || 1);
          setTotalCount(data.count || 0);
        } else {
          setNotices([]);
          setTotalPages(1);
          setTotalCount(0);
        }
        setLoading(false);
      }
    }).catch(() => {
      if (isMounted) {
        setNotices([]);
        setLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [language, noticeType, urgency, page]);

  return (
    <div className="space-y-6">
      <header className="border-b border-[var(--border-muted)] pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            {t.notices.title}
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t.notices.subtitle}
          </p>
        </div>
        <Link
          href="/search?type=notice"
          className="inline-flex items-center text-xs text-[var(--brand-navy)] hover:underline font-semibold"
        >
          🔍 {t.notices.searchLink} &rarr;
        </Link>
      </header>

      <Alert severity="info" title={t.notices.policyTitle}>
        <p>
          {t.notices.policyDesc}
        </p>
      </Alert>

      {/* Filter Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[var(--bg-surface)] p-3 rounded-lg border border-[var(--border-muted)] text-xs">
        {/* Type Filter */}
        <div className="flex flex-wrap items-center gap-1">
          <span className="font-semibold text-[var(--text-secondary)] mr-1">{t.notices.typeFilterLabel}</span>
          <button
            type="button"
            onClick={() => { setNoticeType(''); setPage(1); setLoading(true); }}
            className={`px-2.5 py-1 rounded transition-colors ${
              noticeType === ''
                ? 'bg-[var(--brand-navy)] text-white font-semibold'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {t.notices.filterAll}
          </button>
          <button
            type="button"
            onClick={() => { setNoticeType('statutory'); setPage(1); setLoading(true); }}
            className={`px-2.5 py-1 rounded transition-colors ${
              noticeType === 'statutory'
                ? 'bg-[var(--brand-navy)] text-white font-semibold'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {language === 'mr' ? 'वैधानिक' : language === 'hi' ? 'वैधानिक' : 'Statutory'}
          </button>
          <button
            type="button"
            onClick={() => { setNoticeType('gram_sabha'); setPage(1); setLoading(true); }}
            className={`px-2.5 py-1 rounded transition-colors ${
              noticeType === 'gram_sabha'
                ? 'bg-[var(--brand-navy)] text-white font-semibold'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {language === 'mr' ? 'ग्रामसभा' : language === 'hi' ? 'ग्राम सभा' : 'Gram Sabha'}
          </button>
          <button
            type="button"
            onClick={() => { setNoticeType('tender'); setPage(1); setLoading(true); }}
            className={`px-2.5 py-1 rounded transition-colors ${
              noticeType === 'tender'
                ? 'bg-[var(--brand-navy)] text-white font-semibold'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {t.notices.filterTender}
          </button>
          <button
            type="button"
            onClick={() => { setNoticeType('emergency_alert'); setPage(1); setLoading(true); }}
            className={`px-2.5 py-1 rounded transition-colors ${
              noticeType === 'emergency_alert'
                ? 'bg-[var(--brand-navy)] text-white font-semibold'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {language === 'mr' ? 'आपत्कालीन' : language === 'hi' ? 'आपातकालीन' : 'Emergency'}
          </button>
          <button
            type="button"
            onClick={() => { setNoticeType('general'); setPage(1); setLoading(true); }}
            className={`px-2.5 py-1 rounded transition-colors ${
              noticeType === 'general'
                ? 'bg-[var(--brand-navy)] text-white font-semibold'
                : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]'
            }`}
          >
            {language === 'mr' ? 'सर्वसाधारण' : language === 'hi' ? 'सामान्य' : 'General'}
          </button>
        </div>

        {/* Urgency Filter */}
        <div className="flex flex-wrap items-center gap-1">
          <span className="font-semibold text-[var(--text-secondary)] mr-1">{t.notices.urgencyFilterLabel}</span>
          <button
            type="button"
            onClick={() => { setUrgency(''); setPage(1); setLoading(true); }}
            className={`px-2 py-0.5 rounded text-[11px] transition-colors ${
              urgency === '' ? 'bg-slate-700 text-white font-semibold' : 'bg-[var(--bg-muted)] text-[var(--text-secondary)]'
            }`}
          >
            {t.notices.filterAll}
          </button>
          <button
            type="button"
            onClick={() => { setUrgency('standard'); setPage(1); setLoading(true); }}
            className={`px-2 py-0.5 rounded text-[11px] transition-colors ${
              urgency === 'standard' ? 'bg-blue-700 text-white font-semibold' : 'bg-[var(--bg-muted)] text-blue-800'
            }`}
          >
            {language === 'mr' ? 'सर्वसाधारण' : language === 'hi' ? 'सामान्य' : 'Standard'}
          </button>
          <button
            type="button"
            onClick={() => { setUrgency('urgent'); setPage(1); setLoading(true); }}
            className={`px-2 py-0.5 rounded text-[11px] transition-colors ${
              urgency === 'urgent' ? 'bg-amber-600 text-white font-semibold' : 'bg-[var(--bg-muted)] text-amber-700'
            }`}
          >
            {t.notices.filterUrgent}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="py-12 text-center text-xs text-[var(--text-muted)]">
          {t.common.loading}
        </div>
      ) : notices.length > 0 ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)] px-1">
            <span>{t.notices.totalNotices} <strong>{totalCount}</strong></span>
            <span>{t.notices.pageLabel} {page} {t.notices.outOf} {totalPages}</span>
          </div>

          <div className="space-y-4">
            {notices.map((notice) => (
              <Card
                key={notice.id}
                title={notice.title}
                subtitle={`${t.common.referenceNo}: ${notice.reference_number || `[${t.common.notAvailable}]`} • ${t.common.date}: ${notice.issue_date || notice.effective_from || t.common.notAvailable}`}
                badge={
                  <div className="flex items-center gap-1.5">
                    {notice.is_fallback && (
                      <span className="px-1.5 py-0.5 text-[10px] bg-slate-100 text-slate-600 rounded border border-slate-200">
                        {language === 'hi' ? 'मूल मराठी' : 'Marathi Record'}
                      </span>
                    )}
                    {notice.urgency === 'emergency' ? (
                      <Badge variant="danger">{t.notices.filterEmergency}</Badge>
                    ) : notice.urgency === 'urgent' ? (
                      <Badge variant="warning">{t.notices.filterUrgent}</Badge>
                    ) : null}
                    <Badge variant="primary">{notice.notice_type_display}</Badge>
                  </div>
                }
                footer={
                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[11px] text-[var(--text-muted)]">
                      {notice.issue_date ? `📅 ${t.common.date}: ${notice.issue_date}` : ''}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleOpenNotice(notice)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold bg-[var(--brand-navy)] text-white hover:bg-[var(--brand-navy-dark)] transition-colors focus-visible:outline-2"
                      aria-label={`${getViewNoticeLabel(language)}: ${notice.title}`}
                    >
                      <span>📋</span>
                      <span>{getViewNoticeLabel(language)}</span>
                    </button>
                  </div>
                }
              >
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed line-clamp-3">
                  {getNoticeDescription(notice, language)}
                </p>

                {notice.deadline && (() => {
                  const dl = formatDeadlineDisplay(notice.deadline, language);
                  return (
                    <div
                      className={`mt-2.5 p-2 rounded-md border flex flex-wrap items-center justify-between gap-1.5 text-xs ${
                        dl.isPassed
                          ? 'bg-rose-50/80 border-rose-200 text-rose-900'
                          : 'bg-amber-50/80 border-amber-200 text-amber-900'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 font-medium">
                        <span aria-hidden="true">⏰</span>
                        <span>
                          {dl.label}: <strong className="font-semibold">{dl.text}</strong>
                        </span>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                          dl.isPassed ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {dl.statusText}
                      </span>
                    </div>
                  );
                })()}
              </Card>
            ))}
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-4">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => { setPage(page - 1); setLoading(true); }}
                className="px-3 py-1.5 rounded text-xs border border-[var(--border-primary)] bg-[var(--bg-surface)] disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[var(--bg-muted)]"
              >
                &larr; {t.notices.prevPage}
              </button>
              <span className="text-xs px-2 text-[var(--text-secondary)]">
                {page} / {totalPages}
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => { setPage(page + 1); setLoading(true); }}
                className="px-3 py-1.5 rounded text-xs border border-[var(--border-primary)] bg-[var(--bg-surface)] disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[var(--bg-muted)]"
              >
                {t.notices.nextPage} &rarr;
              </button>
            </div>
          )}
        </div>
      ) : (
        <PlaceholderNotice
          title={t.notices.emptyTitle}
          description={t.notices.emptyDesc}
        />
      )}

      {/* Full Notice Detail Modal */}
      {detailNotice && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
          onClick={handleCloseNotice}
          role="presentation"
        >
          <div
            className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="public-notice-modal-title"
          >
            <div className="flex items-start justify-between border-b border-slate-200 pb-3 gap-3">
              <div>
                <h2 id="public-notice-modal-title" className="text-base sm:text-lg font-bold text-slate-900 leading-snug">
                  {detailNotice.title}
                </h2>
                <p className="text-xs text-slate-500 mt-1">
                  {t.common.referenceNo}: {detailNotice.reference_number || `[${t.common.notAvailable}]`}
                </p>
              </div>
              <button
                type="button"
                onClick={handleCloseNotice}
                aria-label={getCloseLabel(language)}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Badges & Meta */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="primary">{detailNotice.notice_type_display}</Badge>
              {detailNotice.urgency === 'emergency' ? (
                <Badge variant="danger">{t.notices.filterEmergency}</Badge>
              ) : detailNotice.urgency === 'urgent' ? (
                <Badge variant="warning">{t.notices.filterUrgent}</Badge>
              ) : (
                <Badge variant="neutral">{detailNotice.urgency_display}</Badge>
              )}
              {detailNotice.is_fallback && (
                <span className="px-2 py-0.5 text-[11px] bg-slate-100 text-slate-600 rounded border border-slate-200">
                  {language === 'hi' ? 'मूल मराठी' : 'Marathi Record'}
                </span>
              )}
            </div>

            {/* Dates row */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 bg-slate-50 p-3 rounded-lg border border-slate-100 text-xs">
              {detailNotice.issue_date && (
                <div>
                  <span className="text-slate-500 block text-[11px]">{t.common.date}:</span>
                  <span className="font-semibold text-slate-800">{detailNotice.issue_date}</span>
                </div>
              )}
              {detailNotice.effective_from && (
                <div>
                  <span className="text-slate-500 block text-[11px]">लागू दिनांक (Effective):</span>
                  <span className="font-semibold text-slate-800">{detailNotice.effective_from.slice(0, 10)}</span>
                </div>
              )}
              {detailNotice.expires_at && (
                <div>
                  <span className="text-slate-500 block text-[11px]">मुदत समाप्ती (Expires):</span>
                  <span className="font-semibold text-slate-800">{detailNotice.expires_at.slice(0, 10)}</span>
                </div>
              )}
              {detailNotice.deadline && (() => {
                const dl = formatDeadlineDisplay(detailNotice.deadline, language);
                return (
                  <div className="col-span-2 sm:col-span-3 bg-amber-50/80 p-2.5 rounded-lg border border-amber-200 mt-1">
                    <div className="flex items-center justify-between">
                      <span className="text-amber-950 block text-[11px] font-bold">⏰ {dl.label}:</span>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          dl.isPassed ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {dl.statusText}
                      </span>
                    </div>
                    <span className="font-semibold text-slate-900 block mt-0.5 text-xs">{dl.text}</span>
                  </div>
                );
              })()}
            </div>

            {/* Body Markdown Content */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-slate-700 block">
                {language === 'mr' ? 'सूचना सविस्तर माहिती:' : language === 'hi' ? 'सूचना विस्तृत विवरण:' : 'Full Notice Content:'}
              </span>
              {loadingDetail ? (
                <div className="py-8 text-center text-xs text-slate-400">
                  {t.common.loading}
                </div>
              ) : (
                <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 text-xs sm:text-sm text-slate-800 leading-relaxed whitespace-pre-wrap max-h-72 overflow-y-auto">
                  {detailNotice.body_markdown || detailNotice.summary || getNoticeDescription(detailNotice, language)}
                </div>
              )}
            </div>

            {/* Attachments if any */}
            {detailNotice.attachments && detailNotice.attachments.length > 0 && (
              <div className="space-y-1.5 pt-2 border-t border-slate-200">
                <span className="text-xs font-bold text-slate-700 block">
                  {language === 'mr' ? 'जोडलेली कागदपत्रे (Attachments):' : language === 'hi' ? 'संलग्न दस्तावेज़:' : 'Attachments:'}
                </span>
                <ul className="space-y-1 text-xs">
                  {detailNotice.attachments.map((att, idx) => (
                    <li key={idx} className="flex items-center gap-2 p-2 bg-slate-50 rounded border border-slate-200">
                      <span>📎</span>
                      <span className="font-medium text-slate-800">{att.title || att.filename}</span>
                      {att.file_size > 0 && (
                        <span className="text-[11px] text-slate-500">
                          ({(att.file_size / 1024).toFixed(1)} KB)
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Modal Footer */}
            <div className="pt-3 border-t border-slate-200 flex justify-end">
              <button
                type="button"
                onClick={handleCloseNotice}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold transition-colors"
              >
                {getCloseLabel(language)}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
