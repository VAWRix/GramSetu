'use client';

import React, { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { useLanguage } from '@/context/LanguageContext';
import {
  fetchCmsNotices,
  createCmsNotice,
  updateCmsNotice,
  executeGovernanceAction,
  fetchAuthMe,
} from '@/lib/api';
import type { CmsNoticeItem, CmsNoticeRevision, AuthUser } from '@/lib/types';

export default function CmsNoticesPage() {
  const { t, language } = useLanguage();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [notices, setNotices] = useState<CmsNoticeItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Tabs and filter states
  const [activeTab, setActiveTab] = useState<'all' | 'draft' | 'pending' | 'published' | 'withdrawn'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState('all');

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [inspectNotice, setInspectNotice] = useState<CmsNoticeItem | null>(null);
  const [withdrawModal, setWithdrawModal] = useState<{ transId: string; noticeTitle: string } | null>(null);
  const [withdrawReason, setWithdrawReason] = useState('');
  const [withdrawLoading, setWithdrawLoading] = useState(false);
  const [editingItem, setEditingItem] = useState<{
    noticeId: string;
    rev: CmsNoticeRevision;
    noticeType: string;
    urgency: string;
    refNo: string;
    lang: string;
  } | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Form states
  const [title, setTitle] = useState('');
  const [noticeType, setNoticeType] = useState('statutory');
  const [urgency, setUrgency] = useState('standard');
  const [refNo, setRefNo] = useState('');
  const [summary, setSummary] = useState('');
  const [bodyMarkdown, setBodyMarkdown] = useState('');
  const [isEmergency, setIsEmergency] = useState(false);
  const [publishNow, setPublishNow] = useState(false);
  const [deadline, setDeadline] = useState('');
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

  async function loadNotices() {
    setLoading(true);
    try {
      const res = await fetchCmsNotices();
      if (res) {
        setNotices(res.results);
      }
    } catch (err) {
      console.error('Failed to load notices', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUser();
    loadNotices();
  }, []);

  function openCreateModal() {
    setTitle('');
    setNoticeType('statutory');
    setUrgency('standard');
    setRefNo('');
    setSummary('');
    setBodyMarkdown('');
    setDeadline('');
    setIsEmergency(false);
    setPublishNow(false);
    setFeedback(null);
    setShowCreateModal(true);
  }

  function openEditModal(notice: CmsNoticeItem, rev: CmsNoticeRevision, lang: string) {
    setTitle(rev.title);
    setNoticeType(notice.notice_type);
    setUrgency(notice.urgency);
    setRefNo(notice.reference_number || '');
    setSummary(rev.summary || '');
    setBodyMarkdown(rev.body_markdown || '');
    setDeadline(notice.deadline ? notice.deadline.slice(0, 16) : '');
    setEditingItem({
      noticeId: notice.id,
      rev,
      noticeType: notice.notice_type,
      urgency: notice.urgency,
      refNo: notice.reference_number || '',
      lang,
    });
    setFeedback(null);
  }

  async function handleCreateNotice(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      setFeedback({ type: 'error', message: 'Notice title is required.' });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const payload: any = {
      title: title.trim(),
      notice_type: noticeType,
      urgency,
      reference_number: refNo.trim(),
      summary: summary.trim(),
      body_markdown: bodyMarkdown.trim(),
      is_emergency: isEmergency,
      language_code: language,
    };
    if (deadline) {
      payload.deadline = new Date(deadline).toISOString();
    }
    if (publishNow && isSuperAdmin) {
      payload.publish_now = true;
    }

    const res = await createCmsNotice(payload);
    setSubmitting(false);

    if (res.success) {
      setFeedback({ type: 'success', message: 'Notice created successfully.' });
      setShowCreateModal(false);
      loadNotices();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Failed to create notice.' });
    }
  }

  async function handleUpdateNotice(e: React.FormEvent) {
    e.preventDefault();
    if (!editingItem) return;
    if (!title.trim()) {
      setFeedback({ type: 'error', message: 'Notice title is required.' });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const res = await updateCmsNotice(editingItem.noticeId, {
      title: title.trim(),
      notice_type: noticeType,
      urgency,
      reference_number: refNo.trim(),
      description: bodyMarkdown.trim(),
      summary: summary.trim(),
      language_code: editingItem.lang,
      deadline: deadline ? new Date(deadline).toISOString() : null,
    });

    setSubmitting(false);

    if (res.success) {
      setFeedback({ type: 'success', message: 'Notice draft updated successfully.' });
      setEditingItem(null);
      loadNotices();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Failed to update notice.' });
    }
  }

  async function handleSubmitNotice(translationId: string, revisionId: string) {
    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'notice',
      action: 'submit',
      target_id: translationId,
      revision_id: revisionId,
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.governance.successApprove });
      loadNotices();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Submission failed.' });
    }
  }

  async function handlePublishNotice(translationId: string, revisionId: string) {
    const justification = window.prompt(t.governance.justificationLabel) || 'Approved and published by Super Administrator';
    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'notice',
      action: 'publish',
      target_id: translationId,
      revision_id: revisionId,
      justification,
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.governance.successPublish });
      loadNotices();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Publication failed.' });
    }
  }

  async function handleUrgentPublish(noticeId: string, translationId: string, revisionId: string) {
    const authId = window.prompt('Enter your valid Operator Urgent Authorization UUID (तातडीचे प्राधिकरण आयडी):');
    if (!authId || !authId.trim()) {
      alert('Valid Urgent Authorization UUID is required for emergency bypass.');
      return;
    }

    const justification = window.prompt('Enter statutory emergency justification (किमान १५ अक्षरे):');
    if (!justification || justification.trim().length < 15) {
      alert('Emergency publication justification must be at least 15 characters.');
      return;
    }

    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'notice',
      action: 'urgent_publish',
      target_id: translationId,
      revision_id: revisionId,
      urgent_authorization_id: authId.trim(),
      justification: justification.trim(),
    });

    if (res.success) {
      setFeedback({ type: 'success', message: 'Urgent notice published under statutory protocol.' });
      loadNotices();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Urgent publication failed.' });
    }
  }

  async function handleConfirmWithdrawNotice() {
    if (!withdrawModal) return;
    if (withdrawReason.trim().length < 10) {
      alert('Withdrawal requires a justification of at least 10 characters.');
      return;
    }

    setWithdrawLoading(true);
    setFeedback(null);

    const res = await executeGovernanceAction({
      entity_type: 'notice',
      action: 'withdraw',
      target_id: withdrawModal.transId,
      justification: withdrawReason.trim(),
    });

    setWithdrawLoading(false);
    setWithdrawModal(null);
    setWithdrawReason('');

    if (res.success) {
      setFeedback({ type: 'success', message: 'Notice successfully withdrawn from public portal.' });
      loadNotices();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Withdrawal failed.' });
    }
  }

  // Filter notices by tab, category, and search query
  const filteredNotices = notices.filter((n) => {
    // Type match
    if (selectedType !== 'all' && n.notice_type !== selectedType) {
      return false;
    }

    // Search query match
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      const matchRef = n.reference_number?.toLowerCase().includes(q);
      const matchTitle = n.translations.some((t) =>
        t.title?.toLowerCase().includes(q) || t.summary?.toLowerCase().includes(q)
      );
      if (!matchRef && !matchTitle) return false;
    }

    // Tab match
    if (activeTab === 'all') return true;

    return n.translations.some((t) => {
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
            <span aria-hidden="true">📢</span>
            <span>{t.cmsNotices.pageTitle}</span>
          </h1>
          <p className="text-xs text-slate-600 mt-1">{t.cmsNotices.pageSubtitle}</p>
        </div>
        <button
          onClick={openCreateModal}
          className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold self-start sm:self-auto transition-colors shadow-sm inline-flex items-center gap-1.5"
        >
          <span aria-hidden="true">+</span>
          <span>{t.cmsNotices.newNotice}</span>
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

      <Alert severity="warning" title={t.cmsNotices.urgentProtocolTitle}>
        <p>{t.cmsNotices.urgentProtocolDesc}</p>
      </Alert>

      {/* Management Toolbar: Tabs, Search, and Category Filtering */}
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
            सर्व सूचना (All)
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
            <span>प्रसिद्ध सूचना (Published)</span>
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
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
              activeTab === 'withdrawn'
                ? 'bg-rose-700 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <span aria-hidden="true">🚫</span>
            <span>मागे घेतलेल्या (Withdrawn)</span>
          </button>
        </div>

        {/* Search & Category Filter Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
          <div className="flex-1 max-w-md">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="शीर्षक किंवा संदर्भ क्रमांकाने शोधा (Search title or ref no)..."
              className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
            />
          </div>

          <div className="flex items-center gap-2 text-xs">
            <label className="text-slate-500 font-medium whitespace-nowrap">प्रकार (Type):</label>
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
            >
              <option value="all">सर्व प्रकार (All Types)</option>
              <option value="statutory">वैधानिक सूचना (Statutory)</option>
              <option value="tender">निविदा सूचना (Tender)</option>
              <option value="gram_sabha">ग्रामसभा सूचना (Gram Sabha)</option>
              <option value="emergency_alert">आपत्कालीन सूचना (Emergency Alert)</option>
              <option value="general">सामान्य सूचना (General)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Notices List */}
      <div className="space-y-4">
        {loading ? (
          <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-slate-500 text-xs shadow-sm">
            {t.common.loading}
          </div>
        ) : filteredNotices.length === 0 ? (
          <div className="p-10 text-center bg-white rounded-lg border border-slate-200 text-slate-600 text-xs shadow-sm">
            {searchQuery || selectedType !== 'all' || activeTab !== 'all'
              ? 'निवडलेल्या निकषांनुसार कोणतीही सूचना आढळली नाही. (No matching notices found).'
              : t.cmsNotices.emptyList}
          </div>
        ) : (
          filteredNotices.map((n) => (
            <div
              key={n.id}
              className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 shadow-sm hover:border-slate-300 transition-all"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2 py-0.5 bg-blue-50 text-blue-800 border border-blue-200 rounded text-[10px] font-bold uppercase font-mono">
                    {n.notice_type_display || n.notice_type}
                  </span>
                  <span className="px-2 py-0.5 bg-slate-100 text-slate-700 border border-slate-200 rounded text-[10px] uppercase font-mono">
                    {n.urgency_display || n.urgency}
                  </span>
                  {n.is_emergency && (
                    <Badge variant="danger">{t.cmsNotices.emergencyNotice}</Badge>
                  )}
                  {n.reference_number && (
                    <span className="text-xs text-slate-500 font-mono">
                      {t.cmsNotices.referenceNumber}: {n.reference_number}
                    </span>
                  )}
                  {n.deadline && (
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase font-mono border flex items-center gap-1 ${
                        new Date(n.deadline) < new Date()
                          ? 'bg-rose-50 text-rose-800 border-rose-300'
                          : 'bg-amber-50 text-amber-800 border-amber-300'
                      }`}
                    >
                      <span>⏰</span>
                      <span>
                        {new Date(n.deadline) < new Date() ? 'मुदत संपली (Passed): ' : 'मुदत (Deadline): '}
                        {new Date(n.deadline).toLocaleString('en-IN', {
                          timeZone: 'Asia/Kolkata',
                          dateStyle: 'short',
                          timeStyle: 'short',
                        })}
                      </span>
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setInspectNotice(n)}
                    className="px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-800 border border-blue-200 rounded text-xs font-semibold transition-colors inline-flex items-center gap-1"
                  >
                    <span aria-hidden="true">🔍</span>
                    <span>तपशील पहा (View Details)</span>
                  </button>
                </div>
              </div>

              {/* Translations & Revisions */}
              <div className="space-y-3 pt-1">
                {n.translations.map((trans) => (
                  <div key={trans.id} className="bg-slate-50 rounded-lg p-3.5 border border-slate-200 space-y-2.5">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-white text-slate-800 border border-slate-300 font-mono text-[10px] uppercase rounded font-bold">
                          {trans.language_code}
                        </span>
                        <span className="text-xs font-bold text-slate-900">
                          {trans.language_code === 'mr'
                            ? 'मराठी आवृत्ती (Marathi)'
                            : trans.language_code === 'hi'
                            ? 'हिंदी संस्करण (Hindi)'
                            : 'English Version'}
                        </span>
                        <Badge
                          variant={
                            trans.status === 'published'
                              ? 'success'
                              : trans.status === 'withdrawn'
                              ? 'danger'
                              : 'warning'
                          }
                        >
                          {trans.status === 'published'
                            ? 'प्रसिद्ध / Published'
                            : trans.status === 'withdrawn'
                            ? 'मागे घेतलेली / Withdrawn'
                            : trans.status}
                        </Badge>
                      </div>

                      <div className="flex items-center gap-2">
                        {trans.status === 'published' && isSuperAdmin && (
                          <button
                            onClick={() =>
                              setWithdrawModal({
                                transId: trans.id,
                                noticeTitle: trans.title || 'सूचना',
                              })
                            }
                            className="px-2.5 py-1 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-300 rounded text-xs font-semibold transition-colors inline-flex items-center gap-1 shadow-sm"
                          >
                            <span aria-hidden="true">🚫</span>
                            <span>{t.cmsNotices.withdraw}</span>
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
                              <span className="font-mono text-[11px] text-slate-500 font-bold">
                                r{rev.revision_number}
                              </span>
                              <span className="font-medium text-slate-900">{rev.title}</span>
                              <span className="px-1.5 py-0.2 bg-slate-100 text-slate-700 border border-slate-300 rounded text-[10px]">
                                {rev.editorial_status}
                              </span>
                            </div>
                            {rev.summary && (
                              <p className="text-[11px] text-slate-600 line-clamp-1">{rev.summary}</p>
                            )}
                          </div>

                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <span className="text-slate-500">
                              {t.governance.submittedBy}: <strong>{rev.author_name}</strong>
                            </span>

                            {/* Draft state */}
                            {rev.editorial_status === 'draft' && (
                              <>
                                <button
                                  onClick={() => openEditModal(n, rev, trans.language_code)}
                                  className="px-2 py-0.5 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded text-[10px] font-medium inline-flex items-center gap-1 transition-colors"
                                >
                                  <span aria-hidden="true">✏️</span>
                                  <span>{t.cmsNotices.editDraft}</span>
                                </button>
                                <button
                                  onClick={() => handleSubmitNotice(trans.id, rev.id)}
                                  className="px-2.5 py-0.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                                >
                                  {t.governance.btnSubmitReview}
                                </button>
                                {isSuperAdmin && (
                                  <button
                                    onClick={() => handlePublishNotice(trans.id, rev.id)}
                                    className="px-2.5 py-0.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                                  >
                                    {t.cmsNotices.publishDirectly}
                                  </button>
                                )}
                                <button
                                  onClick={() => handleUrgentPublish(n.id, trans.id, rev.id)}
                                  className="px-2.5 py-0.5 bg-amber-600 hover:bg-amber-700 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                                >
                                  {t.cmsNotices.urgentPublish}
                                </button>
                              </>
                            )}

                            {/* Submitted / Pending review state */}
                            {rev.editorial_status === 'submitted' && (
                              isSuperAdmin ? (
                                <button
                                  onClick={() => handlePublishNotice(trans.id, rev.id)}
                                  className="px-2.5 py-0.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                                >
                                  {t.governance.btnPublish}
                                </button>
                              ) : (
                                <span className="px-2.5 py-0.5 bg-amber-50 text-amber-800 border border-amber-300 rounded text-[10px] font-semibold">
                                  {t.governance.btnAwaitingReview}
                                </span>
                              )
                            )}

                            {/* Approved state */}
                            {rev.editorial_status === 'approved' &&
                              trans.status !== 'published' &&
                              isSuperAdmin && (
                                <button
                                  onClick={() => handlePublishNotice(trans.id, rev.id)}
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

      {/* Complete Notice Details Modal */}
      {inspectNotice && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">📋</span>
                <span>सूचना संपूर्ण माहिती (Complete Notice Record Details)</span>
              </h3>
              <button
                onClick={() => setInspectNotice(null)}
                aria-label="Close"
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-slate-50 p-3.5 rounded-lg border border-slate-200">
              <div>
                <span className="text-slate-500 font-medium">सूचना आयडी (UUID): </span>
                <span className="font-mono text-slate-800 text-[11px] block">{inspectNotice.id}</span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">संदर्भ क्रमांक (Ref No): </span>
                <span className="font-mono font-bold text-slate-900 block">
                  {inspectNotice.reference_number || 'उपलब्ध नाही'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">सूचनेचा प्रकार (Category): </span>
                <span className="font-semibold text-blue-900 block">
                  {inspectNotice.notice_type_display || inspectNotice.notice_type}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">तातडी पातळी (Urgency): </span>
                <span className="font-semibold text-slate-800 block">
                  {inspectNotice.urgency_display || inspectNotice.urgency}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">लागू दिनांक (Effective From): </span>
                <span className="text-slate-800 block">
                  {inspectNotice.effective_from ? new Date(inspectNotice.effective_from).toLocaleString('en-IN') : 'तात्काळ'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">समाप्ती दिनांक (Expires At): </span>
                <span className="text-slate-800 block">
                  {inspectNotice.expires_at ? new Date(inspectNotice.expires_at).toLocaleString('en-IN') : 'निरंक (No Expiry)'}
                </span>
              </div>
              <div className="col-span-1 sm:col-span-2">
                <span className="text-slate-500 font-medium">अंतिम मुदत (Deadline): </span>
                <span
                  className={`block font-semibold ${
                    inspectNotice.deadline && new Date(inspectNotice.deadline) < new Date()
                      ? 'text-rose-700 font-bold'
                      : inspectNotice.deadline
                      ? 'text-amber-700 font-bold'
                      : 'text-slate-600'
                  }`}
                >
                  {inspectNotice.deadline
                    ? `${new Date(inspectNotice.deadline).toLocaleString('en-IN', {
                        timeZone: 'Asia/Kolkata',
                        dateStyle: 'medium',
                        timeStyle: 'short',
                      })} (${new Date(inspectNotice.deadline) < new Date() ? 'मुदत संपली / Passed' : 'मुदत सुरू / Active'})`
                    : 'लागू नाही (No Deadline Set)'}
                </span>
              </div>
            </div>

            {/* Translation & Revision Inspection */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                उपलब्ध भाषांतरे व मसुदे (Translations & Revisions)
              </h4>
              {inspectNotice.translations.map((t) => (
                <div key={t.id} className="p-3 bg-white rounded-lg border border-slate-200 text-xs space-y-2">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900 text-sm">{t.title}</span>
                      <span className="px-1.5 py-0.5 bg-slate-100 border text-slate-700 font-mono text-[10px] uppercase font-bold rounded">
                        {t.language_code}
                      </span>
                    </div>
                    <Badge
                      variant={
                        t.status === 'published'
                          ? 'success'
                          : t.status === 'withdrawn'
                          ? 'danger'
                          : 'warning'
                      }
                    >
                      {t.status}
                    </Badge>
                  </div>

                  {t.summary && (
                    <div className="bg-slate-50 p-2 rounded border border-slate-200 text-slate-700">
                      <strong>सारांश:</strong> {t.summary}
                    </div>
                  )}

                  {t.body_markdown && (
                    <div className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800">
                      <strong>मजकूर (Body):</strong>
                      <pre className="font-sans whitespace-pre-wrap text-xs mt-1 text-slate-700">
                        {t.body_markdown}
                      </pre>
                    </div>
                  )}

                  {/* Revisions list */}
                  <div className="space-y-1 pt-1">
                    <span className="text-[11px] font-bold text-slate-700 block">मसुदा आवृत्त्या (Revisions):</span>
                    {t.revisions.map((r) => (
                      <div
                        key={r.id}
                        className="p-2 bg-slate-50 rounded border border-slate-200 text-[11px] flex justify-between items-center"
                      >
                        <div>
                          <span className="font-mono font-bold text-blue-700">r{r.revision_number}</span>{' '}
                          <span className="font-medium text-slate-900">{r.title}</span>{' '}
                          <span className="text-slate-500">• लेखक: {r.author_name}</span>
                          <div className="text-[10px] font-mono text-slate-400">SHA: {r.content_hash}</div>
                        </div>
                        <span className="px-2 py-0.5 bg-white border rounded text-[10px] font-bold">
                          {r.editorial_status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end pt-3 border-t border-slate-200">
              <button
                type="button"
                onClick={() => setInspectNotice(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold"
              >
                बंद करा (Close)
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Withdrawal Confirmation Dialog for Notices */}
      {withdrawModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-md w-full p-6 space-y-4 shadow-2xl text-slate-900">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-rose-700 flex items-center gap-2">
                <span aria-hidden="true">🚫</span>
                <span>सूचना मागे घेण्याची पुष्टी (Withdraw Notice)</span>
              </h3>
              <button
                onClick={() => setWithdrawModal(null)}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 space-y-1">
              <p>
                <strong>सावधान:</strong> ही सूचना (<strong>{withdrawModal.noticeTitle}</strong>) सार्वजनिक संकेतस्थळावरून तात्काळ मागे घेतली जाईल.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                मागे घेण्याचे वैधानिक कारण (Withdrawal Justification):
              </label>
              <textarea
                rows={3}
                required
                value={withdrawReason}
                onChange={(e) => setWithdrawReason(e.target.value)}
                placeholder="उदा. मुदत संपल्यामुळे अथवा सुधारित सूचना प्रसिद्ध करण्यासाठी ही सूचना मागे घेण्यात येत आहे..."
                className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-rose-600 focus:bg-white"
              />
              <span className="text-[10px] text-slate-500 block mt-0.5">
                किमान १० अक्षरे बंधनकारक (Minimum 10 characters required).
              </span>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-200">
              <button
                type="button"
                onClick={() => setWithdrawModal(null)}
                className="px-3.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
              >
                रद्द करा (Cancel)
              </button>
              <button
                type="button"
                disabled={withdrawLoading || withdrawReason.trim().length < 10}
                onClick={handleConfirmWithdrawNotice}
                className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold shadow-sm disabled:opacity-50"
              >
                {withdrawLoading ? 'प्रक्रिया सुरू आहे...' : 'मागे घ्या (Confirm Withdrawal)'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Notice Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">📢</span>
                <span>{t.cmsNotices.newNotice}</span>
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                aria-label={t.common.close}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateNotice} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsNotices.noticeTitle}:
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="उदा. गाव नमुना ८ अ तपासणी व कर वसुली मोहीम"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsNotices.noticeType}:
                  </label>
                  <select
                    value={noticeType}
                    onChange={(e) => setNoticeType(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  >
                    <option value="statutory">वैधानिक सूचना (Statutory)</option>
                    <option value="tender">निविदा सूचना (Tender)</option>
                    <option value="gram_sabha">ग्रामसभा सूचना (Gram Sabha)</option>
                    <option value="emergency_alert">आपत्कालीन सूचना (Emergency Alert)</option>
                    <option value="general">सामान्य सूचना (General)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsNotices.urgency}:
                  </label>
                  <select
                    value={urgency}
                    onChange={(e) => setUrgency(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  >
                    <option value="standard">सर्वसाधारण (Standard)</option>
                    <option value="urgent">तातडीचे / प्राधान्य (Urgent)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsNotices.referenceNumber}:
                </label>
                <input
                  type="text"
                  value={refNo}
                  onChange={(e) => setRefNo(e.target.value)}
                  placeholder="उदा. GP/ADM/2026/042"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  अंतिम मुदत व वेळ (Deadline - Optional):
                </label>
                <input
                  type="datetime-local"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
                <span className="text-[10px] text-slate-500 block mt-0.5">
                  निविदा, अर्ज किंवा नागरिक प्रतिसादासाठी अंतिम मुदत (Asia/Kolkata). मुदत उलटल्यास सार्वजनिक यादीतून सूचना हटणार नाही.
                </span>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsNotices.summary}:
                </label>
                <textarea
                  rows={2}
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder="नागरिकांसाठी संक्षिप्त सारांश..."
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsNotices.content} (Markdown):
                </label>
                <textarea
                  rows={4}
                  value={bodyMarkdown}
                  onChange={(e) => setBodyMarkdown(e.target.value)}
                  placeholder="संपूर्ण सूचनेचा मजकूर..."
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white font-mono"
                />
              </div>

              {isSuperAdmin && (
                <label className="flex items-center gap-2 cursor-pointer bg-blue-50 border border-blue-200 p-2 rounded-lg">
                  <input
                    type="checkbox"
                    checked={publishNow}
                    onChange={(e) => setPublishNow(e.target.checked)}
                    className="rounded text-[#1e3a8a] focus:ring-blue-600"
                  />
                  <div>
                    <span className="text-[#1e3a8a] font-bold block">{t.cmsNotices.publishNow}</span>
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
                  {submitting ? t.common.loading : t.governance.btnSaveDraft}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Notice Modal */}
      {editingItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">✏️</span>
                <span>{t.cmsNotices.editDraft}</span>
              </h3>
              <button
                onClick={() => setEditingItem(null)}
                aria-label={t.common.close}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleUpdateNotice} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsNotices.noticeTitle}:
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
                  {t.cmsNotices.summary}:
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
                  अंतिम मुदत व वेळ (Deadline - Optional):
                </label>
                <input
                  type="datetime-local"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsNotices.content} (Markdown):
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
                  {submitting ? t.common.loading : 'बदल जतन करा (Save Changes)'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
