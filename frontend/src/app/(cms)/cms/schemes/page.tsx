'use client';

import React, { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { useLanguage } from '@/context/LanguageContext';
import {
  fetchCmsSchemes,
  createCmsScheme,
  updateCmsScheme,
  executeGovernanceAction,
  fetchAuthMe,
} from '@/lib/api';
import type { CmsSchemeItem, CmsSchemeRevision, AuthUser } from '@/lib/types';

export default function CmsSchemesPage() {
  const { t, language } = useLanguage();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [schemes, setSchemes] = useState<CmsSchemeItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Filter and search states
  const [activeTab, setActiveTab] = useState<'all' | 'published' | 'pending' | 'draft' | 'withdrawn'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterLevel, setFilterLevel] = useState('all');

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [inspectScheme, setInspectScheme] = useState<CmsSchemeItem | null>(null);
  const [editingItem, setEditingItem] = useState<{
    schemeId: string;
    rev: CmsSchemeRevision;
    schemeLevel: string;
    targetBeneficiary: string;
    officialPortalUrl: string;
    lang: string;
  } | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Form states
  const [slug, setSlug] = useState('');
  const [title, setTitle] = useState('');
  const [department, setDepartment] = useState('');
  const [contactDetails, setContactDetails] = useState('');
  const [schemeLevel, setSchemeLevel] = useState('state');
  const [targetBeneficiary, setTargetBeneficiary] = useState('farmers');
  const [shortDescription, setShortDescription] = useState('');
  const [benefitsSummary, setBenefitsSummary] = useState('');
  const [eligibilityCriteria, setEligibilityCriteria] = useState('');
  const [requiredDocuments, setRequiredDocuments] = useState('आधार कार्ड, ७/१२ उतारा, बँक पासबुक');
  const [applicationProcess, setApplicationProcess] = useState('');
  const [officialPortalUrl, setOfficialPortalUrl] = useState('');
  const [languageCode, setLanguageCode] = useState('mr');
  const [publishNow, setPublishNow] = useState(false);
  const [submitting, setSubmitting] = useState(false);

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

  async function loadSchemes() {
    setLoading(true);
    try {
      const res = await fetchCmsSchemes();
      if (res) {
        setSchemes(res.results);
      }
    } catch (err) {
      console.error('Failed to load schemes', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUser();
    loadSchemes();
  }, []);

  function openCreateModal() {
    setSlug('');
    setTitle('');
    setDepartment('');
    setContactDetails('');
    setSchemeLevel('state');
    setTargetBeneficiary('farmers');
    setShortDescription('');
    setBenefitsSummary('');
    setEligibilityCriteria('');
    setRequiredDocuments('आधार कार्ड, ७/१२ उतारा, बँक पासबुक');
    setApplicationProcess('');
    setOfficialPortalUrl('');
    setLanguageCode(language);
    setPublishNow(false);
    setFeedback(null);
    setShowCreateModal(true);
  }

  function openEditModal(scheme: CmsSchemeItem, rev: CmsSchemeRevision, lang: string) {
    setTitle(rev.scheme_name || rev.title || '');
    setDepartment(scheme.department || '');
    setContactDetails(scheme.contact_details || '');
    setSchemeLevel(scheme.scheme_level);
    setTargetBeneficiary(scheme.target_beneficiary);
    setShortDescription(rev.short_summary || '');
    setBenefitsSummary(rev.benefits || '');
    setEligibilityCriteria(rev.eligibility_criteria || '');
    setRequiredDocuments(rev.required_documents || 'आधार कार्ड, ७/१२ उतारा, बँक पासबुक');
    setApplicationProcess(rev.application_process || '');
    setOfficialPortalUrl(scheme.official_portal_url || '');
    setEditingItem({
      schemeId: scheme.id,
      rev,
      schemeLevel: scheme.scheme_level,
      targetBeneficiary: scheme.target_beneficiary,
      officialPortalUrl: scheme.official_portal_url || '',
      lang,
    });
    setFeedback(null);
  }

  async function handleCreateScheme(e: React.FormEvent) {
    e.preventDefault();
    if (!slug.trim() || !title.trim()) {
      setFeedback({ type: 'error', message: 'Slug and title are required.' });
      return;
    }
    if (title.trim().length < 3) {
      setFeedback({ type: 'error', message: 'Title must be at least 3 characters.' });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const payload: any = {
      slug: slug.trim(),
      title: title.trim(),
      scheme_level: schemeLevel,
      target_beneficiary: targetBeneficiary,
      department: department.trim() || undefined,
      contact_details: contactDetails.trim() || undefined,
      short_description: shortDescription.trim(),
      benefits_summary: benefitsSummary.trim(),
      eligibility_criteria: eligibilityCriteria.trim() || 'पात्रतेचे निकष लागू',
      required_documents: requiredDocuments.trim() || 'आवश्यक कागदपत्रे',
      application_process: applicationProcess.trim() || 'अर्ज प्रक्रिया',
      official_portal_url: officialPortalUrl.trim() || undefined,
      language_code: languageCode,
    };
    if (publishNow && isSuperAdmin) {
      payload.publish_now = true;
    }

    const res = await createCmsScheme(payload);
    setSubmitting(false);

    if (res.success) {
      setFeedback({ type: 'success', message: 'Scheme created successfully.' });
      setShowCreateModal(false);
      loadSchemes();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Failed to register scheme.' });
    }
  }

  async function handleUpdateScheme(e: React.FormEvent) {
    e.preventDefault();
    if (!editingItem) return;
    if (!title.trim() || title.trim().length < 3) {
      setFeedback({ type: 'error', message: 'Title must be at least 3 characters.' });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const res = await updateCmsScheme(editingItem.schemeId, {
      title: title.trim(),
      scheme_name: title.trim(),
      scheme_level: schemeLevel,
      target_beneficiary: targetBeneficiary,
      department: department.trim() || undefined,
      contact_details: contactDetails.trim() || undefined,
      short_summary: shortDescription.trim(),
      benefits: benefitsSummary.trim(),
      eligibility_criteria: eligibilityCriteria.trim(),
      required_documents: requiredDocuments.trim(),
      application_process: applicationProcess.trim(),
      official_portal_url: officialPortalUrl.trim() || undefined,
      language_code: editingItem.lang,
    });

    setSubmitting(false);

    if (res.success) {
      setFeedback({ type: 'success', message: 'Scheme draft updated successfully.' });
      setEditingItem(null);
      loadSchemes();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Update failed.' });
    }
  }

  async function handleSubmitForReview(translationId: string, revisionId: string) {
    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'scheme',
      action: 'submit',
      target_id: translationId,
      revision_id: revisionId,
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.governance.successApprove });
      loadSchemes();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Submission failed.' });
    }
  }

  async function handlePublish(translationId: string, revisionId: string) {
    const justification = window.prompt(t.governance.justificationLabel);
    if (!justification || justification.trim().length < 10) {
      alert('Publication justification must be at least 10 characters.');
      return;
    }

    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'scheme',
      action: 'publish',
      target_id: translationId,
      revision_id: revisionId,
      justification: justification.trim(),
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.governance.successPublish });
      loadSchemes();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Publication failed.' });
    }
  }

  async function handleWithdraw(translationId: string) {
    const justification = window.prompt(t.cmsNotices.withdrawPrompt);
    if (!justification || justification.trim().length < 10) {
      alert('Withdrawal requires a justification of at least 10 characters.');
      return;
    }

    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'scheme',
      action: 'withdraw',
      target_id: translationId,
      justification: justification.trim(),
    });

    if (res.success) {
      setFeedback({ type: 'success', message: 'Scheme successfully withdrawn.' });
      loadSchemes();
      if (inspectScheme && inspectScheme.id === translationId) {
        setInspectScheme(null);
      }
    } else {
      setFeedback({ type: 'error', message: res.error || 'Withdrawal failed.' });
    }
  }

  // Filter schemes by active tab, scheme level, and search query
  const filteredSchemes = schemes.filter((s) => {
    // Level filter
    if (filterLevel !== 'all' && s.scheme_level !== filterLevel) {
      return false;
    }

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      const matchSlug = s.slug.toLowerCase().includes(q);
      const matchBeneficiary = (s.target_beneficiary_display || s.target_beneficiary || '').toLowerCase().includes(q);
      const matchLevel = (s.scheme_level_display || s.scheme_level || '').toLowerCase().includes(q);
      const matchTrans = s.translations.some((t) =>
        t.revisions.some((r) =>
          (r.scheme_name || r.title || '').toLowerCase().includes(q) ||
          (r.short_summary || '').toLowerCase().includes(q)
        )
      );
      if (!matchSlug && !matchBeneficiary && !matchLevel && !matchTrans) {
        return false;
      }
    }

    // Tab filter
    if (activeTab === 'all') return true;

    return s.translations.some((t) => {
      const isPublished = t.status === 'published';
      const isWithdrawn = t.status === 'withdrawn';
      const isPending =
        t.status === 'pending_approval' ||
        t.status === 'submitted' ||
        t.revisions.some((r) => r.editorial_status === 'submitted');
      const isDraft =
        t.status === 'draft' ||
        t.revisions.every((r) => r.editorial_status === 'draft');

      if (activeTab === 'published') return isPublished;
      if (activeTab === 'withdrawn') return isWithdrawn;
      if (activeTab === 'pending') return isPending && !isPublished;
      if (activeTab === 'draft') return isDraft && !isPublished && !isWithdrawn && !isPending;
      return true;
    });
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white p-5 rounded-lg border shadow-sm">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span aria-hidden="true">🌾</span>
            <span>{t.cmsSchemes.pageTitle}</span>
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            {t.cmsSchemes.pageSubtitle}
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold self-start sm:self-auto transition-colors shadow-sm inline-flex items-center gap-1.5"
        >
          <span aria-hidden="true">+</span>
          <span>{t.cmsSchemes.createScheme}</span>
        </button>
      </div>

      {/* Feedback Alert */}
      {feedback && (
        <Alert
          severity={feedback.type === 'success' ? 'info' : 'danger'}
          title={feedback.type === 'success' ? 'Success' : 'Error'}
        >
          <p>{feedback.message}</p>
        </Alert>
      )}

      {/* Management Toolbar: Tabs, Search, and Level Filter */}
      <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-3">
        {/* Navigation Tabs */}
        <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-200 pb-2.5">
          <button
            type="button"
            onClick={() => setActiveTab('all')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              activeTab === 'all'
                ? 'bg-[#1e3a8a] text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            सर्व योजना (All)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('published')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
              activeTab === 'published'
                ? 'bg-emerald-700 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <span aria-hidden="true">✓</span>
            <span>प्रसिद्ध (Published)</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('pending')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
              activeTab === 'pending'
                ? 'bg-amber-600 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <span aria-hidden="true">⏳</span>
            <span>मंजुरी प्रलंबित (Pending Review)</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('draft')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              activeTab === 'draft'
                ? 'bg-slate-800 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            मसुदा (Drafts)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('withdrawn')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              activeTab === 'withdrawn'
                ? 'bg-rose-700 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            मागे घेतलेले (Withdrawn)
          </button>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 pt-1">
          <div className="flex-1 relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="योजनेचे नाव, Slug किंवा लाभार्थी शोधा (Search schemes)..."
              className="w-full bg-slate-50 border border-slate-300 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
            />
            <span className="absolute left-2.5 top-2 text-slate-400 text-xs" aria-hidden="true">
              🔍
            </span>
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="filter-scheme-level" className="text-xs text-slate-600 whitespace-nowrap font-medium">
              स्तर:
            </label>
            <select
              id="filter-scheme-level"
              value={filterLevel}
              onChange={(e) => setFilterLevel(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-600"
            >
              <option value="all">सर्व स्तर (All Levels)</option>
              <option value="central">केंद्र शासन (Central)</option>
              <option value="state">राज्य शासन (State)</option>
              <option value="district">जिल्हा परिषद (District)</option>
              <option value="panchayat">ग्रामपंचायत (Panchayat)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Schemes List */}
      <div className="space-y-4">
        {loading ? (
          <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-slate-500 text-xs shadow-sm">
            {t.common.loading}
          </div>
        ) : filteredSchemes.length === 0 ? (
          <div className="p-10 text-center bg-white rounded-lg border border-slate-200 text-slate-600 text-xs shadow-sm">
            {t.cmsSchemes.emptyList}
          </div>
        ) : (
          filteredSchemes.map((s) => (
            <div key={s.id} className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 shadow-sm hover:border-slate-300 transition-all">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs px-2 py-0.5 bg-blue-50 text-blue-800 border border-blue-200 rounded font-bold">
                    /{s.slug}
                  </span>
                  <span className="px-2 py-0.5 bg-slate-100 text-slate-700 border border-slate-200 rounded text-[10px] uppercase font-mono">
                    {s.scheme_level_display || s.scheme_level}
                  </span>
                  <span className="px-2 py-0.5 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded text-[10px] font-semibold">
                    {s.target_beneficiary_display || s.target_beneficiary}
                  </span>
                  {s.official_portal_url && (
                    <a
                      href={s.official_portal_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-700 hover:underline"
                    >
                      {t.cmsSchemes.officialPortalUrl} &rarr;
                    </a>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setInspectScheme(s)}
                    className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-300 rounded text-xs font-semibold inline-flex items-center gap-1 transition-colors"
                  >
                    <span>🔍</span>
                    <span>तपशील पहा (View Details)</span>
                  </button>
                  {s.translations.some((tr) => tr.status === 'published') && (
                    <a
                      href={`/schemes/${s.slug}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-[#1e3a8a] border border-blue-200 rounded text-xs font-semibold inline-flex items-center gap-1 transition-colors"
                    >
                      <span>सार्वजनिक पहा &rarr;</span>
                    </a>
                  )}
                </div>
              </div>

              {(s.department || s.contact_details) && (
                <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600 bg-slate-50/80 p-2.5 rounded-lg border border-slate-200">
                  {s.department && (
                    <span className="inline-flex items-center gap-1">
                      <span className="font-semibold text-slate-700">विभाग:</span>
                      <span>{s.department}</span>
                    </span>
                  )}
                  {s.contact_details && (
                    <span className="inline-flex items-center gap-1">
                      <span className="font-semibold text-slate-700">मार्गदर्शन / संपर्क:</span>
                      <span>{s.contact_details}</span>
                    </span>
                  )}
                </div>
              )}

              {/* Translations & Revisions */}
              <div className="space-y-3 pt-1">
                {s.translations.map((trans) => (
                  <div key={trans.id} className="bg-slate-50 rounded-lg p-3.5 border border-slate-200 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-white text-slate-800 border border-slate-300 font-mono text-[10px] uppercase rounded font-bold">
                          {trans.language_code}
                        </span>
                        <span className="text-xs font-bold text-slate-900">
                          {trans.revisions[0]?.scheme_name || `Scheme (${trans.language_code})`}
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

                      <div className="flex items-center gap-2">
                        {trans.status === 'published' && isSuperAdmin && (
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
                          <div className="space-y-0.5">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-[11px] text-slate-500 font-bold">r{rev.revision_number}</span>
                              <span className="font-medium text-slate-900">{rev.scheme_name}</span>
                              <span className="px-1.5 py-0.2 bg-slate-100 text-slate-700 border border-slate-300 rounded text-[10px]">
                                {rev.editorial_status}
                              </span>
                            </div>
                            {rev.short_summary && (
                              <p className="text-[11px] text-slate-500 line-clamp-1">{rev.short_summary}</p>
                            )}
                          </div>

                          <div className="flex flex-wrap items-center gap-2 text-[11px] shrink-0">
                            <span className="text-slate-500">{t.governance.submittedBy}: {rev.author_name}</span>

                            {/* Draft state: Save Draft / Submit for Review / Super Admin Publish */}
                            {rev.editorial_status === 'draft' && (
                              <>
                                <button
                                  onClick={() => openEditModal(s, rev, trans.language_code)}
                                  className="px-2 py-0.5 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded text-[10px] font-medium inline-flex items-center gap-1 transition-colors"
                                >
                                  <span aria-hidden="true">✏️</span>
                                  <span>{t.cmsSchemes.editScheme}</span>
                                </button>
                                <button
                                  onClick={() => handleSubmitForReview(trans.id, rev.id)}
                                  className="px-2.5 py-0.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                                >
                                  {t.governance.btnSubmitReview}
                                </button>
                                {isSuperAdmin && (
                                  <button
                                    onClick={() => handlePublish(trans.id, rev.id)}
                                    className="px-2.5 py-0.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                                  >
                                    {t.cmsSchemes.publishDirectly}
                                  </button>
                                )}
                              </>
                            )}

                            {/* Submitted state: Awaiting review indicator */}
                            {rev.editorial_status === 'submitted' && (
                              isSuperAdmin ? (
                                <button
                                  onClick={() => handlePublish(trans.id, rev.id)}
                                  className="px-2.5 py-0.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                                >
                                  {t.governance.btnPublish}
                                </button>
                              ) : (
                                <span className="px-2 py-0.5 bg-amber-50 text-amber-800 border border-amber-300 rounded text-[10px] font-semibold">
                                  {t.governance.btnAwaitingReview}
                                </span>
                              )
                            )}

                            {/* Approved state: Ready for publication */}
                            {rev.editorial_status === 'approved' && trans.status !== 'published' && isSuperAdmin && (
                              <button
                                onClick={() => handlePublish(trans.id, rev.id)}
                                className="px-2.5 py-0.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                              >
                                {t.governance.btnPublish}
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Create Scheme Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">🌾</span>
                <span>{t.cmsSchemes.createScheme}</span>
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                aria-label={t.common.close}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateScheme} className="space-y-3 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsSchemes.slug}:
                  </label>
                  <input
                    type="text"
                    required
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="pm-kisan"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsSchemes.schemeTitle}:
                  </label>
                  <input
                    type="text"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. PM Kisan Samman Nidhi"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsSchemes.schemeLevel}:
                  </label>
                  <select
                    value={schemeLevel}
                    onChange={(e) => setSchemeLevel(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  >
                    <option value="central">{t.cmsSchemes.centralLevel}</option>
                    <option value="state">{t.cmsSchemes.stateLevel}</option>
                    <option value="district">{t.cmsSchemes.districtLevel}</option>
                    <option value="panchayat">{t.cmsSchemes.panchayatLevel}</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsSchemes.targetBeneficiary}:
                  </label>
                  <select
                    value={targetBeneficiary}
                    onChange={(e) => setTargetBeneficiary(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  >
                    <option value="farmers">Farmers</option>
                    <option value="women">Women</option>
                    <option value="youth">Youth & Students</option>
                    <option value="senior_citizens">Senior Citizens</option>
                    <option value="bpl_families">BPL Families</option>
                    <option value="all_residents">All Residents</option>
                  </select>
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

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsSchemes.shortSummary}:
                </label>
                <textarea
                  rows={2}
                  value={shortDescription}
                  onChange={(e) => setShortDescription(e.target.value)}
                  placeholder="Objective and summary..."
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsSchemes.benefits}:
                </label>
                <textarea
                  rows={2}
                  value={benefitsSummary}
                  onChange={(e) => setBenefitsSummary(e.target.value)}
                  placeholder="e.g. Rs 6,000 per year..."
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsSchemes.eligibility}:
                  </label>
                  <textarea
                    rows={3}
                    value={eligibilityCriteria}
                    onChange={(e) => setEligibilityCriteria(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsSchemes.requiredDocuments}:
                  </label>
                  <textarea
                    rows={3}
                    value={requiredDocuments}
                    onChange={(e) => setRequiredDocuments(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsSchemes.applicationProcess}:
                </label>
                <textarea
                  rows={2}
                  value={applicationProcess}
                  onChange={(e) => setApplicationProcess(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    संबंधित शासकीय विभाग (Department):
                  </label>
                  <input
                    type="text"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    placeholder="उदा. कृषी विभाग, महाराष्ट्र शासन"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    मार्गदर्शन व संपर्क / हेल्पलाईन (Contact Details):
                  </label>
                  <input
                    type="text"
                    value={contactDetails}
                    onChange={(e) => setContactDetails(e.target.value)}
                    placeholder="उदा. १८००-१८०-१५५१ / पंचायत कृषी अधिकारी"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsSchemes.officialPortalUrl}:
                </label>
                <input
                  type="url"
                  value={officialPortalUrl}
                  onChange={(e) => setOfficialPortalUrl(e.target.value)}
                  placeholder="https://example.gov.in"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              {/* Super Admin Direct Publish Option */}
              {isSuperAdmin && (
                <label className="flex items-center gap-2 cursor-pointer bg-blue-50 border border-blue-200 p-2.5 rounded-lg mt-2">
                  <input
                    type="checkbox"
                    checked={publishNow}
                    onChange={(e) => setPublishNow(e.target.checked)}
                    className="rounded text-[#1e3a8a] focus:ring-blue-600"
                  />
                  <div>
                    <span className="text-[#1e3a8a] font-bold block">{t.cmsSchemes.publishNow}</span>
                    <span className="text-[11px] text-blue-700 block">{t.governance.publishNowHelp}</span>
                  </div>
                </label>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.close}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {submitting ? t.common.loading : (publishNow ? t.cmsSchemes.publishDirectly : t.cmsSchemes.saveDraft)}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Scheme Draft Modal */}
      {editingItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900">
                {t.cmsSchemes.editScheme} (r{editingItem.rev.revision_number})
              </h3>
              <button
                onClick={() => setEditingItem(null)}
                aria-label={t.common.close}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleUpdateScheme} className="space-y-3 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsSchemes.schemeTitle}:
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
                    {t.cmsSchemes.officialPortalUrl}:
                  </label>
                  <input
                    type="url"
                    value={officialPortalUrl}
                    onChange={(e) => setOfficialPortalUrl(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    संबंधित शासकीय विभाग (Department):
                  </label>
                  <input
                    type="text"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    placeholder="उदा. कृषी विभाग, महाराष्ट्र शासन"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    मार्गदर्शन व संपर्क / हेल्पलाईन (Contact Details):
                  </label>
                  <input
                    type="text"
                    value={contactDetails}
                    onChange={(e) => setContactDetails(e.target.value)}
                    placeholder="उदा. १८००-१८०-१५५१ / पंचायत कृषी अधिकारी"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsSchemes.shortSummary}:
                </label>
                <textarea
                  rows={2}
                  value={shortDescription}
                  onChange={(e) => setShortDescription(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsSchemes.benefits}:
                </label>
                <textarea
                  rows={2}
                  value={benefitsSummary}
                  onChange={(e) => setBenefitsSummary(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsSchemes.eligibility}:
                  </label>
                  <textarea
                    rows={3}
                    value={eligibilityCriteria}
                    onChange={(e) => setEligibilityCriteria(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsSchemes.requiredDocuments}:
                  </label>
                  <textarea
                    rows={3}
                    value={requiredDocuments}
                    onChange={(e) => setRequiredDocuments(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsSchemes.applicationProcess}:
                </label>
                <textarea
                  rows={2}
                  value={applicationProcess}
                  onChange={(e) => setApplicationProcess(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setEditingItem(null)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.close}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {submitting ? t.common.loading : t.cmsSchemes.saveDraft}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Scheme Detail Inspection Modal */}
      {inspectScheme && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white border border-slate-200 rounded-xl max-w-3xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span aria-hidden="true">🌾</span>
                  <span>योजना सविस्तर तपशील (Scheme Details)</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5 font-mono">
                  /{inspectScheme.slug}
                </p>
              </div>
              <button
                onClick={() => setInspectScheme(null)}
                aria-label="Close"
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            {/* Core Metadata Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 text-xs bg-slate-50 p-3.5 rounded-lg border border-slate-200">
              <div>
                <span className="text-slate-500 font-medium">योजना स्तर (Level):</span>
                <span className="font-semibold text-blue-900 block mt-0.5">
                  {inspectScheme.scheme_level_display || inspectScheme.scheme_level}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">लक्षित लाभार्थी (Target Beneficiary):</span>
                <span className="font-semibold text-emerald-800 block mt-0.5">
                  {inspectScheme.target_beneficiary_display || inspectScheme.target_beneficiary}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">प्रदर्शन क्रम (Display Order):</span>
                <span className="font-mono text-slate-700 block mt-0.5">
                  {inspectScheme.display_order ?? 0}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">योजना ओळख (ID):</span>
                <span className="font-mono text-slate-600 text-[10px] block mt-0.5 break-all">
                  {inspectScheme.id}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">शासकीय अधिकृत पोर्टल:</span>
                {inspectScheme.official_portal_url ? (
                  <a
                    href={inspectScheme.official_portal_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-700 hover:underline block truncate mt-0.5"
                  >
                    {inspectScheme.official_portal_url} &rarr;
                  </a>
                ) : (
                  <span className="text-slate-400 block mt-0.5">उपलब्ध नाही</span>
                )}
              </div>
              <div>
                <span className="text-slate-500 font-medium">संबंधित विभाग (Department):</span>
                <span className="font-semibold text-slate-800 block mt-0.5">
                  {inspectScheme.department || 'लागू नाही / नमूद नाही'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">मार्गदर्शन व संपर्क (Contact Details):</span>
                <span className="font-semibold text-slate-800 block mt-0.5">
                  {inspectScheme.contact_details || 'स्थानिक ग्रामपंचायत कार्यालय'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">सार्वजनिक पोर्टल स्थिती:</span>
                <div className="mt-0.5">
                  {inspectScheme.translations.some((tr) => tr.status === 'published') ? (
                    <a
                      href={`/schemes/${inspectScheme.slug}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-emerald-700 hover:text-emerald-800 font-semibold underline text-[11px]"
                    >
                      <span>सार्वजनिक पृष्ठावर पहा ↗</span>
                    </a>
                  ) : (
                    <span className="text-slate-500 text-[11px]">अद्याप प्रसिद्ध नाही (Not Disclosed)</span>
                  )}
                </div>
              </div>
            </div>

            {/* Translations & Detailed Revisions */}
            <div className="space-y-4 pt-1">
              <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                उपलब्ध भाषांतरे व मजकूर (Translations & Content Fields)
              </h4>

              {inspectScheme.translations.map((trans) => (
                <div key={trans.id} className="p-4 bg-white rounded-lg border border-slate-200 text-xs space-y-3 shadow-xs">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 bg-blue-100 text-blue-900 font-mono text-[11px] font-bold uppercase rounded">
                        {trans.language_code}
                      </span>
                      <span className="font-bold text-slate-900 text-sm">
                        {trans.revisions[0]?.scheme_name || `Scheme (${trans.language_code})`}
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

                    <div className="flex items-center gap-2">
                      {trans.status === 'published' && isSuperAdmin && (
                        <button
                          onClick={() => handleWithdraw(trans.id)}
                          className="px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 rounded text-[11px] font-semibold transition-colors"
                        >
                          {t.cmsPages.withdraw} (Withdraw)
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Revision details */}
                  {trans.revisions.map((rev) => (
                    <div key={rev.id} className="space-y-2.5 bg-slate-50 p-3.5 rounded-lg border border-slate-200">
                      <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-blue-800">
                            आवृत्ती r{rev.revision_number}
                          </span>
                          <span className="px-1.5 py-0.5 bg-slate-200 text-slate-700 font-mono text-[10px] rounded uppercase">
                            {rev.editorial_status}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500">
                          {t.governance.submittedBy}: <strong>{rev.author_name}</strong>
                        </div>
                      </div>

                      {/* Content Fields */}
                      <div className="space-y-2">
                        {rev.short_summary && (
                          <div>
                            <span className="text-slate-500 font-bold block text-[11px]">
                              {t.cmsSchemes.shortSummary}:
                            </span>
                            <p className="text-slate-800 bg-white p-2 rounded border border-slate-200 whitespace-pre-line mt-0.5">
                              {rev.short_summary}
                            </p>
                          </div>
                        )}

                        {rev.benefits && (
                          <div>
                            <span className="text-slate-500 font-bold block text-[11px]">
                              {t.cmsSchemes.benefits}:
                            </span>
                            <p className="text-slate-800 bg-white p-2 rounded border border-slate-200 whitespace-pre-line mt-0.5">
                              {rev.benefits}
                            </p>
                          </div>
                        )}

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <div>
                            <span className="text-slate-500 font-bold block text-[11px]">
                              {t.cmsSchemes.eligibility}:
                            </span>
                            <div className="text-slate-800 bg-white p-2 rounded border border-slate-200 whitespace-pre-line mt-0.5">
                              {rev.eligibility_criteria || 'पात्रतेचे निकष लागू'}
                            </div>
                          </div>

                          <div>
                            <span className="text-slate-500 font-bold block text-[11px]">
                              {t.cmsSchemes.requiredDocuments}:
                            </span>
                            <div className="text-slate-800 bg-white p-2 rounded border border-slate-200 whitespace-pre-line mt-0.5">
                              {rev.required_documents || 'आधार कार्ड, ७/१२ उतारा, बँक पासबुक'}
                            </div>
                          </div>
                        </div>

                        {rev.application_process && (
                          <div>
                            <span className="text-slate-500 font-bold block text-[11px]">
                              {t.cmsSchemes.applicationProcess}:
                            </span>
                            <p className="text-slate-800 bg-white p-2 rounded border border-slate-200 whitespace-pre-line mt-0.5">
                              {rev.application_process}
                            </p>
                          </div>
                        )}
                      </div>

                      {/* Action buttons inside revision */}
                      <div className="flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-slate-200">
                        {rev.editorial_status === 'draft' && (
                          <>
                            <button
                              onClick={() => {
                                setInspectScheme(null);
                                openEditModal(inspectScheme, rev, trans.language_code);
                              }}
                              className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded text-[11px] font-medium inline-flex items-center gap-1 transition-colors"
                            >
                              <span>✏️</span>
                              <span>{t.cmsSchemes.editScheme}</span>
                            </button>
                            <button
                              onClick={() => handleSubmitForReview(trans.id, rev.id)}
                              className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[11px] font-semibold shadow-sm transition-colors"
                            >
                              {t.governance.btnSubmitReview}
                            </button>
                            {isSuperAdmin && (
                              <button
                                onClick={() => handlePublish(trans.id, rev.id)}
                                className="px-3 py-1 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[11px] font-semibold shadow-sm transition-colors"
                              >
                                {t.cmsSchemes.publishDirectly}
                              </button>
                            )}
                          </>
                        )}

                        {rev.editorial_status === 'submitted' && (
                          isSuperAdmin ? (
                            <button
                              onClick={() => handlePublish(trans.id, rev.id)}
                              className="px-3 py-1 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[11px] font-semibold shadow-sm transition-colors"
                            >
                              {t.governance.btnPublish}
                            </button>
                          ) : (
                            <span className="px-2.5 py-1 bg-amber-50 text-amber-800 border border-amber-300 rounded text-[11px] font-semibold">
                              {t.governance.btnAwaitingReview}
                            </span>
                          )
                        )}

                        {rev.editorial_status === 'approved' && trans.status !== 'published' && isSuperAdmin && (
                          <button
                            onClick={() => handlePublish(trans.id, rev.id)}
                            className="px-3 py-1 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[11px] font-semibold shadow-sm transition-colors"
                          >
                            {t.governance.btnPublish}
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>

            <div className="flex justify-end pt-3 border-t border-slate-200">
              <button
                type="button"
                onClick={() => setInspectScheme(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold"
              >
                {t.common.close}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
