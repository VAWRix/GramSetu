'use client';

import React, { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { useLanguage } from '@/context/LanguageContext';
import {
  fetchCmsPages,
  createCmsPage,
  updateCmsPageRevision,
  branchCmsPageRevision,
  executeGovernanceAction,
  fetchAuthMe,
  fetchVillageResearchData,
} from '@/lib/api';
import type { CmsPageItem, CmsPageTranslation, CmsPageRevision, AuthUser, VillageKnowledgeSection, VillageKnowledgeReference } from '@/lib/types';

function SafeMarkdownRenderer({ content }: { content: string }) {
  if (!content || !content.trim()) {
    return <p className="text-slate-400 italic">कोणताही मजकूर उपलब्ध नाही (No markdown content available).</p>;
  }

  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let inList: 'ul' | 'ol' | null = null;
  let listItems: string[] = [];

  function flushList() {
    if (inList === 'ul' && listItems.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="list-disc list-inside space-y-1 my-2 pl-2 text-slate-800">
          {listItems.map((li, idx) => (
            <li key={idx}>{renderInline(li)}</li>
          ))}
        </ul>
      );
    } else if (inList === 'ol' && listItems.length > 0) {
      elements.push(
        <ol key={`ol-${elements.length}`} className="list-decimal list-inside space-y-1 my-2 pl-2 text-slate-800">
          {listItems.map((li, idx) => (
            <li key={idx}>{renderInline(li)}</li>
          ))}
        </ol>
      );
    }
    inList = null;
    listItems = [];
  }

  function renderInline(text: string): React.ReactNode {
    const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    while ((match = linkRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(renderTextDecorations(text.substring(lastIndex, match.index)));
      }
      const label = match[1];
      const href = match[2];
      const isExternal = href.startsWith('http://') || href.startsWith('https://');
      parts.push(
        <a
          key={`link-${match.index}`}
          href={href}
          target={isExternal ? '_blank' : undefined}
          rel={isExternal ? 'noopener noreferrer' : undefined}
          className="text-[#1e3a8a] underline hover:text-blue-900 font-medium"
        >
          {label}
        </a>
      );
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < text.length) {
      parts.push(renderTextDecorations(text.substring(lastIndex)));
    }
    return parts.length > 0 ? parts : renderTextDecorations(text);
  }

  function renderTextDecorations(text: string): React.ReactNode {
    const boldParts = text.split(/(\*\*[^*]+\*\*)/g);
    return boldParts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-bold text-slate-900">{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  }

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    if (!line) {
      flushList();
      continue;
    }

    if (line.startsWith('# ')) {
      flushList();
      elements.push(
        <h1 key={i} className="text-xl sm:text-2xl font-bold text-slate-900 mt-4 mb-2 border-b border-slate-200 pb-1">
          {renderInline(line.substring(2))}
        </h1>
      );
    } else if (line.startsWith('## ')) {
      flushList();
      elements.push(
        <h2 key={i} className="text-lg sm:text-xl font-bold text-slate-900 mt-3 mb-1.5 border-b border-slate-100 pb-0.5">
          {renderInline(line.substring(3))}
        </h2>
      );
    } else if (line.startsWith('### ')) {
      flushList();
      elements.push(
        <h3 key={i} className="text-sm sm:text-base font-bold text-slate-800 mt-2.5 mb-1">
          {renderInline(line.substring(4))}
        </h3>
      );
    } else if (line.startsWith('> ')) {
      flushList();
      elements.push(
        <blockquote key={i} className="border-l-4 border-blue-700 bg-blue-50/50 pl-3 py-1.5 my-2 text-xs italic text-slate-700 rounded-r">
          {renderInline(line.substring(2))}
        </blockquote>
      );
    } else if (/^[-*]\s+/.test(line)) {
      if (inList !== 'ul') flushList();
      inList = 'ul';
      listItems.push(line.replace(/^[-*]\s+/, ''));
    } else if (/^\d+\.\s+/.test(line)) {
      if (inList !== 'ol') flushList();
      inList = 'ol';
      listItems.push(line.replace(/^\d+\.\s+/, ''));
    } else {
      flushList();
      elements.push(
        <p key={i} className="my-1.5 text-xs sm:text-sm text-slate-700 leading-relaxed">
          {renderInline(line)}
        </p>
      );
    }
  }
  flushList();

  return <div className="space-y-1">{elements}</div>;
}

export default function CmsContentPage() {
  const { t, language } = useLanguage();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [pages, setPages] = useState<CmsPageItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [inspectingRev, setInspectingRev] = useState<{
    page: CmsPageItem;
    trans: CmsPageTranslation;
    rev: CmsPageRevision;
  } | null>(null);
  const [branchingPage, setBranchingPage] = useState<{
    page: CmsPageItem;
    trans: CmsPageTranslation;
    latestRev?: CmsPageRevision;
  } | null>(null);
  const [editingRev, setEditingRev] = useState<{
    rev: CmsPageRevision;
    pageSlug: string;
    lang: string;
  } | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Form states
  const [slug, setSlug] = useState('');
  const [title, setTitle] = useState('');
  const [summary, setSummary] = useState('');
  const [bodyMarkdown, setBodyMarkdown] = useState('');
  const [sectionsData, setSectionsData] = useState<VillageKnowledgeSection[]>([]);
  const [referencesData, setReferencesData] = useState<VillageKnowledgeReference[]>([]);
  const [languageCode, setLanguageCode] = useState('mr');
  const [publishNow, setPublishNow] = useState(false);
  const [justification, setJustification] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [loadingResearch, setLoadingResearch] = useState(false);

  const isSuperAdmin = currentUser?.role === 'super_admin';

  async function loadUser() {
    try {
      const me = await fetchAuthMe();
      if (me?.user) {
        setCurrentUser(me.user);
      }
    } catch (err) {
      console.error('Failed to load user profile', err);
    }
  }

  async function loadPages() {
    setLoading(true);
    try {
      const res = await fetchCmsPages();
      if (res) {
        setPages(res.results);
      }
    } catch (err) {
      console.error('Failed to load CMS pages', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUser();
    loadPages();
  }, []);

  async function handleImportResearch(customLang?: string) {
    const langToFetch = (typeof customLang === 'string' && customLang)
      ? customLang
      : (branchingPage ? branchingPage.trans.language_code : languageCode) || 'mr';
    setLoadingResearch(true);
    try {
      const res = await fetchVillageResearchData(langToFetch);
      if (res.success && res.research) {
        const data = res.research;
        setTitle(
          langToFetch === 'en'
            ? `${data.village_name_en} Village Knowledge Portal`
            : langToFetch === 'hi'
            ? `${data.village_name_hi} ग्राम ज्ञानकोश (Knowledge Portal)`
            : `${data.village_name_mr} ग्राम माहिती ज्ञानकोश (Knowledge Portal)`
        );
        setSummary(data.summary || '');
        setBodyMarkdown(data.summary || '');
        if (data.sections && Array.isArray(data.sections)) {
          setSectionsData(data.sections);
        }
        if (data.references && Array.isArray(data.references)) {
          setReferencesData(data.references);
        }
        setFeedback({
          type: 'success',
          message: `शासकीय संशोधन माहिती यशस्वीरीत्या आयात केली (${langToFetch.toUpperCase()}: ${data.sections?.length || 0} अधिकृत विभाग व ${data.references?.length || 0} संदर्भ).`,
        });
      } else {
        setFeedback({ type: 'error', message: res.error || 'Failed to import research facts.' });
      }
    } catch (err) {
      setFeedback({ type: 'error', message: 'Error retrieving research data.' });
    } finally {
      setLoadingResearch(false);
    }
  }

  function openNewTranslationModal(page: CmsPageItem, langCode: string) {
    setTitle('');
    setSummary('');
    setBodyMarkdown('');
    setSectionsData([]);
    setReferencesData([]);
    setPublishNow(false);
    setJustification('');
    setBranchingPage({
      page,
      trans: {
        id: '',
        language_code: langCode,
        localized_slug: `${page.slug}-${langCode}`,
        status: 'draft',
        current_approved_revision_id: null,
        revisions: [],
      },
      latestRev: undefined,
    });
    setFeedback(null);
    handleImportResearch(langCode);
  }

  function openCreateModal() {
    setSlug('');
    setTitle('');
    setSummary('');
    setBodyMarkdown('');
    setSectionsData([]);
    setReferencesData([]);
    setLanguageCode(language);
    setPublishNow(false);
    setJustification('');
    setFeedback(null);
    setShowCreateModal(true);
  }

  function openEditModal(page: CmsPageItem, rev: CmsPageRevision, lang: string) {
    setTitle(rev.title);
    setSummary(rev.summary || '');
    setBodyMarkdown(rev.body_markdown || '');
    setSectionsData(rev.sections_data || []);
    setReferencesData(rev.references_data || []);
    setEditingRev({ rev, pageSlug: page.slug, lang });
    setFeedback(null);
  }

  function openBranchModal(page: CmsPageItem, trans: CmsPageTranslation) {
    const latest = trans.revisions[0];
    setTitle(latest?.title || '');
    setSummary(latest?.summary || '');
    setBodyMarkdown(latest?.body_markdown || '');
    setSectionsData(latest?.sections_data || []);
    setReferencesData(latest?.references_data || []);
    setPublishNow(false);
    setJustification('');
    setBranchingPage({ page, trans, latestRev: latest });
    setFeedback(null);
  }

  async function handleBranchPage(e: React.FormEvent) {
    e.preventDefault();
    if (!branchingPage) return;
    if (!title.trim()) {
      setFeedback({ type: 'error', message: 'Page title is required.' });
      return;
    }

    if (publishNow && isSuperAdmin && (!justification || justification.trim().length < 10)) {
      setFeedback({
        type: 'error',
        message: 'प्रकाशन औचित्य किमान १० अक्षरे असणे आवश्यक आहे (Justification min 10 chars).',
      });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const res = await branchCmsPageRevision(branchingPage.page.id, {
      title: title.trim(),
      summary: summary.trim(),
      body_markdown: bodyMarkdown.trim(),
      sections_data: sectionsData,
      references_data: referencesData,
      language_code: branchingPage.trans.language_code,
      publish_now: publishNow && isSuperAdmin ? true : undefined,
      justification: publishNow && isSuperAdmin ? justification.trim() : undefined,
    });

    setSubmitting(false);

    if (res.success) {
      setFeedback({
        type: 'success',
        message: publishNow
          ? 'नवीन आवृत्ती तयार करून थेट प्रकाशित केली (New revision branched and published directly).'
          : 'नवीन मसुदा आवृत्ती तयार केली (New revision branched for review).',
      });
      setBranchingPage(null);
      loadPages();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Failed to branch new revision.' });
    }
  }

  async function handleCreatePage(e: React.FormEvent) {
    e.preventDefault();
    if (!slug.trim() || !title.trim()) {
      setFeedback({ type: 'error', message: t.cmsPages.pageTitleLabel });
      return;
    }

    if (publishNow && isSuperAdmin && (!justification || justification.trim().length < 10)) {
      setFeedback({ type: 'error', message: t.governance.justificationMinLength });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const res = await createCmsPage({
      slug: slug.trim(),
      title: title.trim(),
      summary: summary.trim(),
      body_markdown: bodyMarkdown.trim(),
      sections_data: sectionsData,
      references_data: referencesData,
      language_code: languageCode,
      publish_now: publishNow && isSuperAdmin ? true : undefined,
      justification: publishNow && isSuperAdmin ? justification.trim() : undefined,
    });

    setSubmitting(false);

    if (res.success) {
      setFeedback({
        type: 'success',
        message: publishNow
          ? `${t.cmsPages.newPage} - ${t.governance.statusPublished}`
          : t.cmsPages.newPage,
      });
      setShowCreateModal(false);
      loadPages();
    } else {
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  async function handleUpdatePageRevision(e: React.FormEvent) {
    e.preventDefault();
    if (!editingRev) return;
    if (!title.trim()) {
      setFeedback({ type: 'error', message: t.cmsPages.pageTitleLabel });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const res = await updateCmsPageRevision(editingRev.rev.id, {
      title: title.trim(),
      summary: summary.trim(),
      body_markdown: bodyMarkdown.trim(),
      sections_data: sectionsData,
      references_data: referencesData,
    });

    setSubmitting(false);

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsPages.editDraft });
      setEditingRev(null);
      loadPages();
    } else {
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  async function handleSubmitForReview(translationId: string, revisionId: string) {
    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'page',
      action: 'submit',
      target_id: translationId,
      revision_id: revisionId,
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsPages.submitForApproval });
      loadPages();
    } else {
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  async function handlePublish(translationId: string, revisionId: string) {
    const promptMsg = t.governance.justificationMinLength;
    const just = window.prompt(promptMsg);
    if (!just || just.trim().length < 10) {
      alert(t.governance.justificationMinLength);
      return;
    }

    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'page',
      action: 'publish',
      target_id: translationId,
      revision_id: revisionId,
      justification: just.trim(),
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsPages.publish });
      loadPages();
    } else {
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  async function handleWithdraw(translationId: string) {
    const promptMsg = t.governance.justificationMinLength;
    const just = window.prompt(promptMsg);
    if (!just || just.trim().length < 10) {
      alert(t.governance.justificationMinLength);
      return;
    }

    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'page',
      action: 'withdraw',
      target_id: translationId,
      justification: just.trim(),
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsPages.withdraw });
      loadPages();
    } else {
      setFeedback({ type: 'error', message: res.error || t.governance.actionFailed });
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white p-5 rounded-lg border shadow-sm">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span aria-hidden="true">📄</span>
            <span>{t.cmsPages.pageTitle}</span>
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            {t.cmsPages.pageSubtitle}
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold self-start sm:self-auto transition-colors shadow-sm inline-flex items-center gap-1.5"
        >
          <span aria-hidden="true">+</span>
          <span>{t.cmsPages.newPage}</span>
        </button>
      </div>

      {/* Feedback Alert */}
      {feedback && (
        <Alert
          severity={feedback.type === 'success' ? 'info' : 'danger'}
          title={feedback.type === 'success' ? t.common.save : t.governance.actionFailed}
        >
          <p>{feedback.message}</p>
        </Alert>
      )}

      {/* Pages List */}
      <div className="space-y-4">
        {loading ? (
          <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-slate-500 text-xs shadow-sm">
            {t.common.loading}
          </div>
        ) : pages.length === 0 ? (
          <div className="p-10 text-center bg-white rounded-lg border border-slate-200 text-slate-600 text-xs shadow-sm">
            {t.cmsPages.emptyList}
          </div>
        ) : (
          pages.map((p) => (
            <div key={p.id} className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 shadow-sm hover:border-slate-300 transition-all">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs px-2 py-0.5 bg-blue-50 text-blue-800 border border-blue-200 rounded font-bold">
                    /{p.slug}
                  </span>
                  <span className="text-xs text-slate-500">
                    {t.cmsPages.displayOrder}: {p.display_order}
                  </span>
                </div>
              </div>

              {/* Translations & Revisions */}
              <div className="space-y-3 pt-1">
                {p.translations.map((trans) => (
                  <div key={trans.id} className="bg-slate-50 rounded-lg p-3.5 border border-slate-200 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-white text-slate-800 border border-slate-300 font-mono text-[10px] uppercase rounded font-bold">
                          {trans.language_code}
                        </span>
                        <span className="text-xs font-bold text-slate-900">
                          {trans.revisions[0]?.title || `Page (${trans.language_code})`}
                        </span>
                        <Badge
                          variant={
                            trans.status === 'published'
                              ? 'success'
                              : trans.status === 'withdrawn'
                              ? 'neutral'
                              : 'warning'
                          }
                        >
                          {trans.status}
                        </Badge>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {/* View Details Button */}
                        <button
                          type="button"
                          onClick={() => setInspectingRev({ page: p, trans, rev: trans.revisions[0] })}
                          className="px-2.5 py-1 bg-white hover:bg-slate-100 text-slate-800 border border-slate-300 rounded text-[11px] font-semibold transition-colors inline-flex items-center gap-1 shadow-xs"
                          title="View full markdown content, headings, lists and links"
                        >
                          <span aria-hidden="true">🔍</span>
                          <span>तपशील पहा (View Details)</span>
                        </button>

                        {/* Edit / Branch New Revision Button */}
                        <button
                          type="button"
                          onClick={() => openBranchModal(p, trans)}
                          className="px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-[#1e3a8a] border border-blue-200 rounded text-[11px] font-semibold transition-colors inline-flex items-center gap-1 shadow-xs"
                          title="Branch a new revision for editing without mutating published records"
                        >
                          <span aria-hidden="true">✏️</span>
                          <span>नवीन आवृत्ती संपादित करा (Edit)</span>
                        </button>

                        {trans.status === 'published' && (
                          <button
                            onClick={() => handleWithdraw(trans.id)}
                            className="px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 rounded text-[11px] font-medium transition-colors"
                          >
                            {t.cmsPages.withdraw}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Revisions list */}
                    <div className="space-y-1.5 pt-1">
                      {trans.revisions.map((rev) => (
                        <div
                          key={rev.id}
                          className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2.5 bg-white rounded-md border border-slate-200 text-xs text-slate-700"
                        >
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[11px] text-slate-500 font-bold">r{rev.revision_number}</span>
                            <span className="font-medium text-slate-900">{rev.title}</span>
                            <span className="px-1.5 py-0.2 bg-slate-100 text-slate-700 border border-slate-300 rounded text-[10px]">
                              {rev.editorial_status}
                            </span>
                          </div>

                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <span className="text-slate-500">{rev.author_name}</span>

                            <button
                              type="button"
                              onClick={() => setInspectingRev({ page: p, trans, rev })}
                              className="px-2 py-0.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 rounded text-[10px] font-medium inline-flex items-center gap-1 transition-colors"
                              title="Inspect full markdown and metadata for this revision"
                            >
                              <span>🔍</span>
                              <span>पहा (View)</span>
                            </button>

                            {rev.editorial_status === 'draft' && (
                              <>
                                <button
                                  onClick={() => openEditModal(p, rev, trans.language_code)}
                                  className="px-2 py-0.5 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded text-[10px] font-medium inline-flex items-center gap-1 transition-colors"
                                >
                                  <span aria-hidden="true">✏️</span>
                                  <span>{t.cmsPages.editDraft}</span>
                                </button>
                                <button
                                  onClick={() => handleSubmitForReview(trans.id, rev.id)}
                                  className="px-2.5 py-0.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                                >
                                  {t.cmsPages.submitForApproval}
                                </button>
                                {isSuperAdmin && (
                                  <button
                                    onClick={() => handlePublish(trans.id, rev.id)}
                                    className="px-2.5 py-0.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                                  >
                                    {t.cmsPages.publishDirectly}
                                  </button>
                                )}
                              </>
                            )}

                            {rev.editorial_status === 'approved' && trans.status !== 'published' && (
                              <button
                                onClick={() => handlePublish(trans.id, rev.id)}
                                className="px-2.5 py-0.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                              >
                                {t.cmsPages.publish}
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}

                {/* Missing Translations Indicator & Add Button */}
                {(() => {
                  const supportedLangs = ['mr', 'hi', 'en'];
                  const missing = supportedLangs.filter(l => !p.translations.some(t => t.language_code === l));
                  if (missing.length === 0) return null;
                  return (
                    <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-200 text-xs">
                      <span className="text-slate-500 text-[11px] font-medium">भाषांतर स्थिती / Missing Translations:</span>
                      {missing.map((ml) => (
                        <button
                          key={ml}
                          type="button"
                          onClick={() => openNewTranslationModal(p, ml)}
                          className="px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-900 border border-amber-300 rounded text-[11px] font-semibold inline-flex items-center gap-1 transition-colors shadow-xs"
                          title={`Add ${ml.toUpperCase()} translation for /${p.slug}`}
                        >
                          <span aria-hidden="true">+</span>
                          <span>{ml.toUpperCase()} भाषांतर जोडा (Add {ml.toUpperCase()})</span>
                        </button>
                      ))}
                    </div>
                  );
                })()}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Create Page Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">📄</span>
                <span>{t.cmsPages.newPage}</span>
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreatePage} className="space-y-3 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsPages.slugLabel}:
                  </label>
                  <input
                    type="text"
                    required
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="history"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    Language:
                  </label>
                  <select
                    value={languageCode}
                    onChange={(e) => setLanguageCode(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  >
                    <option value="mr">मराठी (mr)</option>
                    <option value="hi">हिंदी (hi)</option>
                    <option value="en">English (en)</option>
                  </select>
                </div>
              </div>

              {/* Research Assistant Import Button */}
              <div className="p-3 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <span className="text-xs font-bold text-blue-900 block flex items-center gap-1.5">
                    <span>⚡</span>
                    <span>शासकीय संशोधन सहाय्यक (Statutory Research Assistant)</span>
                  </span>
                  <p className="text-[11px] text-blue-700">
                    जनगणना २०११, एलजीडी (LGD 549493) व ग्रामविकास विभागाची अधिकृत माहिती थेट आयात करा.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleImportResearch()}
                  disabled={loadingResearch}
                  className="px-3 py-1.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-xs font-semibold whitespace-nowrap shadow-xs transition-colors disabled:opacity-50"
                >
                  {loadingResearch ? 'आयात करत आहे...' : 'माहिती आयात करा (Import Facts)'}
                </button>
              </div>

              {sectionsData.length > 0 && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-emerald-900 flex items-center gap-1">
                      <span>✓</span>
                      <span>ज्ञानकोश विभाग सक्रिय ({sectionsData.length} विभाग समाविष्ट)</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => setSectionsData([])}
                      className="text-emerald-700 hover:text-red-700 text-[11px] underline"
                    >
                      विभाग साफ करा (Clear)
                    </button>
                  </div>
                  <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                    {sectionsData.map((sec, idx) => (
                      <div key={sec.key || idx} className="p-1.5 bg-white rounded border border-emerald-200 text-[11px] text-emerald-950 flex items-center justify-between">
                        <span className="truncate">{sec.title_mr || sec.title_en}</span>
                        <span className="font-mono text-[10px] text-emerald-700 uppercase">{sec.data_year}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsPages.pageTitleLabel}:
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Village History & Culture"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsPages.summaryLabel}:
                </label>
                <textarea
                  rows={2}
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsPages.bodyLabel}:
                </label>
                <textarea
                  rows={4}
                  value={bodyMarkdown}
                  onChange={(e) => setBodyMarkdown(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white font-mono"
                />
              </div>

              {isSuperAdmin && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer font-semibold text-amber-900">
                    <input
                      type="checkbox"
                      checked={publishNow}
                      onChange={(e) => setPublishNow(e.target.checked)}
                      className="rounded border-amber-400 text-blue-600 focus:ring-blue-500"
                    />
                    <span>{t.cmsPages.publishNow}</span>
                  </label>
                  {publishNow && (
                    <input
                      type="text"
                      required
                      placeholder={t.governance.justificationMinLength}
                      value={justification}
                      onChange={(e) => setJustification(e.target.value)}
                      className="w-full bg-white border border-amber-300 rounded px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
                    />
                  )}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.cancel}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {submitting ? t.common.loading : t.common.save}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Page Revision Modal */}
      {editingRev && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">✏️</span>
                <span>{t.cmsPages.editDraft} (/{editingRev.pageSlug} - r{editingRev.rev.revision_number})</span>
              </h3>
              <button
                onClick={() => setEditingRev(null)}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleUpdatePageRevision} className="space-y-3 text-xs">
              {/* Research Assistant Import Button */}
              <div className="p-3 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <span className="text-xs font-bold text-blue-900 block flex items-center gap-1.5">
                    <span>⚡</span>
                    <span>शासकीय संशोधन सहाय्यक (Statutory Research Assistant)</span>
                  </span>
                  <p className="text-[11px] text-blue-700">
                    जनगणना २०११, एलजीडी (LGD 549493) व ग्रामविकास विभागाची अधिकृत माहिती थेट आयात करा.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleImportResearch()}
                  disabled={loadingResearch}
                  className="px-3 py-1.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-xs font-semibold whitespace-nowrap shadow-xs transition-colors disabled:opacity-50"
                >
                  {loadingResearch ? 'आयात करत आहे...' : 'माहिती आयात करा (Import Facts)'}
                </button>
              </div>

              {sectionsData.length > 0 && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-emerald-900 flex items-center gap-1">
                      <span>✓</span>
                      <span>ज्ञानकोश विभाग सक्रिय ({sectionsData.length} विभाग समाविष्ट)</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => setSectionsData([])}
                      className="text-emerald-700 hover:text-red-700 text-[11px] underline"
                    >
                      विभाग साफ करा (Clear)
                    </button>
                  </div>
                  <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                    {sectionsData.map((sec, idx) => (
                      <div key={sec.key || idx} className="p-1.5 bg-white rounded border border-emerald-200 text-[11px] text-emerald-950 flex items-center justify-between">
                        <span className="truncate">{sec.title_mr || sec.title_en}</span>
                        <span className="font-mono text-[10px] text-emerald-700 uppercase">{sec.data_year}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsPages.pageTitleLabel}:
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsPages.summaryLabel}:
                </label>
                <textarea
                  rows={2}
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsPages.bodyLabel}:
                </label>
                <textarea
                  rows={4}
                  value={bodyMarkdown}
                  onChange={(e) => setBodyMarkdown(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white font-mono"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setEditingRev(null)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.cancel}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {submitting ? t.common.loading : t.common.save}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* View Page Details Modal (Full Markdown, Headings, Lists, Links, Metadata) */}
      {inspectingRev && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white border border-slate-200 rounded-xl max-w-3xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[92vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-slate-200 pb-3 gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-xs px-2 py-0.5 bg-blue-50 text-blue-800 border border-blue-200 rounded font-bold">
                    /{inspectingRev.page.slug}
                  </span>
                  <span className="px-2 py-0.5 bg-white text-slate-800 border border-slate-300 font-mono text-[10px] uppercase rounded font-bold">
                    {inspectingRev.trans.language_code}
                  </span>
                  <span className="font-mono text-xs text-blue-700 font-bold">
                    r{inspectingRev.rev.revision_number}
                  </span>
                  <Badge
                    variant={
                      inspectingRev.trans.status === 'published'
                        ? 'success'
                        : inspectingRev.trans.status === 'withdrawn'
                        ? 'neutral'
                        : 'warning'
                    }
                  >
                    {inspectingRev.trans.status}
                  </Badge>
                </div>
                <h2 className="text-lg sm:text-xl font-bold text-slate-900 leading-snug">
                  {inspectingRev.rev.title}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setInspectingRev(null)}
                aria-label="Close"
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            {/* Metadata Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs">
              <div>
                <span className="text-slate-500 block text-[10px]">संपादक / लेखक:</span>
                <span className="font-semibold text-slate-800">{inspectingRev.rev.author_name}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">मसुदा स्थिती:</span>
                <span className="font-semibold text-slate-800">{inspectingRev.rev.editorial_status}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">नोंदणी दिनांक:</span>
                <span className="font-semibold text-slate-800">
                  {new Date(inspectingRev.rev.created_at).toLocaleString('en-IN', {
                    timeZone: 'Asia/Kolkata',
                    dateStyle: 'short',
                    timeStyle: 'short',
                  })}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">हॅश (SHA-256):</span>
                <span className="font-mono text-[10px] text-slate-600 truncate block" title={inspectingRev.rev.content_hash}>
                  {inspectingRev.rev.content_hash ? inspectingRev.rev.content_hash.slice(0, 12) + '...' : 'अप्रकाशित'}
                </span>
              </div>
            </div>

            {/* Summary */}
            {inspectingRev.rev.summary && (
              <div className="bg-blue-50/70 p-3.5 rounded-lg border border-blue-200 text-xs text-slate-800">
                <strong className="block text-[11px] font-bold text-[#1e3a8a] uppercase tracking-wider mb-1">
                  संक्षिप्त सारांश (Summary):
                </strong>
                <p className="leading-relaxed">{inspectingRev.rev.summary}</p>
              </div>
            )}

            {/* Rendered Full Markdown Body */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-slate-800 uppercase tracking-wider block">
                संपूर्ण मजकूर (Full Formatted Content):
              </span>
              <div className="bg-white p-5 rounded-lg border border-slate-200 text-xs sm:text-sm text-slate-900 leading-relaxed max-h-80 overflow-y-auto">
                <SafeMarkdownRenderer content={inspectingRev.rev.body_markdown || ''} />
              </div>
            </div>

            {/* Structured Sections Preview */}
            {inspectingRev.rev.sections_data && inspectingRev.rev.sections_data.length > 0 && (
              <div className="space-y-2">
                <span className="text-xs font-bold text-slate-800 uppercase tracking-wider block flex items-center justify-between">
                  <span>ज्ञानकोश विभाग रचना (Structured Encyclopedia Sections: {inspectingRev.rev.sections_data.length})</span>
                  <span className="text-[10px] text-blue-700 font-semibold">अधिकृत ज्ञान नोंद</span>
                </span>
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 space-y-1.5 max-h-48 overflow-y-auto">
                  {inspectingRev.rev.sections_data.map((sec, idx) => (
                    <div key={sec.key || idx} className="p-2 bg-white rounded border border-slate-200 text-xs flex items-center justify-between gap-2">
                      <span className="font-semibold text-slate-900 truncate">{sec.title_mr || sec.title_en}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className="font-mono text-[10px] text-slate-500">{sec.data_year}</span>
                        <Badge variant={sec.verification_status === 'verified' ? 'success' : 'warning'}>
                          {sec.verification_status === 'verified' ? 'पडताळणीकृत' : 'प्रलंबित'}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Revisions History Drawer / Footer */}
            <div className="pt-3 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div className="text-slate-500 flex items-center gap-1.5 font-mono text-[11px]">
                <span>एकूण आवृत्त्या: {inspectingRev.trans.revisions.length}</span>
                <span>•</span>
                <span>सध्याची: r{inspectingRev.rev.revision_number}</span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const current = inspectingRev;
                    setInspectingRev(null);
                    openBranchModal(current.page, current.trans);
                  }}
                  className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-[#1e3a8a] border border-blue-200 rounded-lg text-xs font-semibold transition-colors inline-flex items-center gap-1"
                >
                  <span>✏️</span>
                  <span>नवीन आवृत्ती संपादित करा (Edit New Revision)</span>
                </button>
                <button
                  type="button"
                  onClick={() => setInspectingRev(null)}
                  className="px-4 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold"
                >
                  {t.common.close}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit / Branch New Page Revision Modal */}
      {branchingPage && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span>✏️</span>
                  <span>पृष्ठ संपादन — नवीन आवृत्ती (Edit Page & Branch Next Revision)</span>
                </h3>
                <p className="text-[11px] text-slate-500 font-mono mt-0.5">
                  /{branchingPage.page.slug} [{branchingPage.trans.language_code.toUpperCase()}]
                </p>
              </div>
              <button
                onClick={() => setBranchingPage(null)}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-900">
              <p>
                <strong>अपरिवर्तनीय शासन (Immutable Governance):</strong> अस्तित्वात असलेल्या प्रसिद्ध पानामध्ये फेरबदल करताना नवी आवृत्ती (Next Revision) तयार केली जाते. ऑपरेटरने केलेले बदल पुनरावलोकनासाठी सादर होईपर्यंत सार्वजनिक संकेतस्थळावर मागील मंजूर आवृत्तीच सक्रिय राहील.
              </p>
            </div>

            <form onSubmit={handleBranchPage} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsPages.pageTitleLabel} *:
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="पृष्ठाचे शीर्षक..."
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsPages.summaryLabel}:
                </label>
                <textarea
                  rows={2}
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder="पृष्ठाचा संक्षिप्त सारांश..."
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsPages.bodyLabel} (Markdown) *:
                </label>
                <textarea
                  rows={8}
                  required
                  value={bodyMarkdown}
                  onChange={(e) => setBodyMarkdown(e.target.value)}
                  placeholder="# मुख्य शीर्षक&#10;&#10;येथे मजकूर लिहा...&#10;&#10;- मुद्यावली १&#10;- मुद्यावली २"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white font-mono leading-relaxed"
                />
                <span className="text-[10px] text-slate-500 block mt-0.5">
                  Markdown स्वरूप समर्थित आहे: # (शीर्षक), **ठळक**, - (मुद्यावली), 1. (क्रमांक), &gt; (उद्धरण), [नाव](URL).
                </span>
              </div>

              {/* Super Admin Direct Publish Option */}
              {isSuperAdmin && (
                <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-lg space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={publishNow}
                      onChange={(e) => setPublishNow(e.target.checked)}
                      className="rounded text-emerald-700 focus:ring-emerald-600"
                    />
                    <div>
                      <span className="text-emerald-900 font-bold block">
                        थेट प्रकाशित करा (Publish Directly without Review)
                      </span>
                      <span className="text-[11px] text-emerald-700 block">
                        मुख्य प्रशासक अधिकार: ही नवीन आवृत्ती थेट सार्वजनिक संकेतस्थळावर अद्यतनित होईल.
                      </span>
                    </div>
                  </label>

                  {publishNow && (
                    <div>
                      <label className="block text-slate-700 font-semibold mb-1">
                        प्रकाशन औचित्य / कारण (Justification - min 10 chars) *:
                      </label>
                      <input
                        type="text"
                        required
                        value={justification}
                        onChange={(e) => setJustification(e.target.value)}
                        placeholder="उदा. माहितीचे वार्षिक अद्यतन व नवीन तपशील समाविष्ट"
                        className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-600"
                      />
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setBranchingPage(null)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.cancel}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {submitting
                    ? t.common.loading
                    : publishNow
                    ? 'जतन करून थेट प्रकाशित करा'
                    : 'नवीन आवृत्ती जतन करा (Save Revision)'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
