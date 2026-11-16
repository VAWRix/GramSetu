'use client';

import React, { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { useLanguage } from '@/context/LanguageContext';
import {
  fetchCmsDocuments,
  createCmsDocument,
  uploadCmsDocumentVersion,
  executeGovernanceAction,
  fetchAuthMe,
  getApiBaseUrl,
} from '@/lib/api';
import type { CmsDocumentItem, AuthUser } from '@/lib/types';

export default function CmsDocumentsPage() {
  const { t, language } = useLanguage();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [documents, setDocuments] = useState<CmsDocumentItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Filter and search states
  const [activeTab, setActiveTab] = useState<'all' | 'draft' | 'pending' | 'published' | 'withdrawn'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showReplaceModal, setShowReplaceModal] = useState<string | null>(null);
  const [inspectDoc, setInspectDoc] = useState<CmsDocumentItem | null>(null);
  const [withdrawModal, setWithdrawModal] = useState<{ transId: string; docTitle: string } | null>(null);
  const [withdrawReason, setWithdrawReason] = useState('');
  const [withdrawLoading, setWithdrawLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Form states
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('resolution');
  const [refNo, setRefNo] = useState('');
  const [department, setDepartment] = useState('ग्रामपंचायत कार्यालय');
  const [isConfidential, setIsConfidential] = useState(false);
  const [retentionHold, setRetentionHold] = useState(false);
  const [publishNow, setPublishNow] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
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

  async function loadDocuments() {
    setLoading(true);
    try {
      const res = await fetchCmsDocuments();
      if (res) {
        setDocuments(res.results);
      }
    } catch (err) {
      console.error('Failed to load documents', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUser();
    loadDocuments();
  }, []);

  async function handleCreateDocument(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !selectedFile) {
      setFeedback({ type: 'error', message: t.cmsDocuments.uploadError });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const formData = new FormData();
    formData.append('title', title.trim());
    formData.append('category', category);
    formData.append('reference_number', refNo.trim());
    formData.append('issuing_department', department.trim());
    formData.append('is_confidential', isConfidential ? 'true' : 'false');
    formData.append('retention_hold', retentionHold ? 'true' : 'false');
    formData.append('language_code', language);
    formData.append('file', selectedFile);
    if (publishNow && isSuperAdmin) {
      formData.append('publish_now', 'true');
    }

    const res = await createCmsDocument(formData);
    setSubmitting(false);

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsDocuments.uploadSuccess });
      setShowCreateModal(false);
      setTitle('');
      setRefNo('');
      setSelectedFile(null);
      setIsConfidential(false);
      setRetentionHold(false);
      setPublishNow(false);
      loadDocuments();
    } else {
      setFeedback({ type: 'error', message: res.error || t.cmsDocuments.uploadError });
    }
  }

  async function handleReplaceVersion(e: React.FormEvent, docId: string) {
    e.preventDefault();
    if (!selectedFile) {
      setFeedback({ type: 'error', message: t.cmsDocuments.uploadError });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('language_code', language);

    const res = await uploadCmsDocumentVersion(docId, formData);
    setSubmitting(false);

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsDocuments.uploadSuccess });
      setShowReplaceModal(null);
      setSelectedFile(null);
      loadDocuments();
    } else {
      setFeedback({ type: 'error', message: res.error || t.cmsDocuments.uploadError });
    }
  }

  async function handleSubmitForDisclosure(versionId: string) {
    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'document',
      action: 'submit',
      target_id: versionId,
      version_id: versionId,
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.governance.successApprove });
      loadDocuments();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Submission failed' });
    }
  }

  async function handleApproveDisclosure(versionId: string) {
    const justification = window.prompt(t.governance.justificationLabel);
    if (!justification || justification.trim().length < 10) {
      alert('Justification of at least 10 characters required.');
      return;
    }

    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'document',
      action: 'approve',
      target_id: versionId,
      version_id: versionId,
      justification: justification.trim(),
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsDocuments.discloseSuccess });
      loadDocuments();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Approval failed' });
    }
  }

  async function handleConfirmWithdraw() {
    if (!withdrawModal) return;
    if (withdrawReason.trim().length < 10) {
      alert('मागे घेण्याचे कारण किमान १० अक्षरांचे असणे बंधनकारक आहे. (Withdrawal justification must be at least 10 characters).');
      return;
    }

    setWithdrawLoading(true);
    setFeedback(null);

    const res = await executeGovernanceAction({
      entity_type: 'document',
      action: 'withdraw',
      target_id: withdrawModal.transId,
      justification: withdrawReason.trim(),
    });

    setWithdrawLoading(false);
    setWithdrawModal(null);
    setWithdrawReason('');

    if (res.success) {
      setFeedback({
        type: 'success',
        message: 'दस्तऐवज सार्वजनिक पोर्टलवरून यशस्वीरित्या मागे घेण्यात आला आहे. (Document successfully withdrawn from public portal).',
      });
      loadDocuments();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Withdrawal failed.' });
    }
  }

  // Filter documents by tab, search, and category
  const filteredDocuments = documents.filter((doc) => {
    // Category match
    if (selectedCategory !== 'all' && doc.category !== selectedCategory) {
      return false;
    }

    // Search query match
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      const matchRef = doc.reference_number?.toLowerCase().includes(q);
      const matchDept = doc.issuing_department?.toLowerCase().includes(q);
      const matchTitle = doc.translations.some((t) => t.title?.toLowerCase().includes(q));
      if (!matchRef && !matchDept && !matchTitle) {
        return false;
      }
    }

    // Tab match based on translation statuses and version disclosure statuses
    if (activeTab === 'all') return true;

    const hasMatchingStatus = doc.translations.some((t) => {
      const isDisclosed = t.status === 'disclosed';
      const isWithdrawn = t.status === 'withdrawn';
      const isPending =
        t.status === 'pending_approval' ||
        t.versions.some((v) => v.disclosure_status === 'pending_approval');
      const isDraft =
        t.status === 'draft' ||
        t.versions.every((v) => v.disclosure_status === 'draft');

      if (activeTab === 'published') return isDisclosed;
      if (activeTab === 'withdrawn') return isWithdrawn;
      if (activeTab === 'pending') return isPending && !isDisclosed;
      if (activeTab === 'draft') return isDraft && !isDisclosed && !isWithdrawn && !isPending;
      return true;
    });

    return hasMatchingStatus;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white p-5 rounded-lg border shadow-sm">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span aria-hidden="true">📑</span>
            <span>{t.cmsDocuments.pageTitle}</span>
          </h1>
          <p className="text-xs text-slate-600 mt-1">{t.cmsDocuments.pageSubtitle}</p>
        </div>
        <button
          onClick={() => {
            setShowCreateModal(true);
            setFeedback(null);
          }}
          className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold self-start sm:self-auto transition-colors shadow-sm inline-flex items-center gap-1.5"
        >
          <span aria-hidden="true">+</span>
          <span>{t.cmsDocuments.uploadDocument}</span>
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

      {/* Governance & Integrity Advisory */}
      <Alert severity="info" title={t.cmsDocuments.integrityNoticeTitle}>
        <p>{t.cmsDocuments.integrityNoticeDesc}</p>
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
            सर्व दस्तऐवज (All)
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
            <span>प्रसिद्ध / प्रकटीकृत (Published)</span>
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
            <span>मागे घेतलेले (Withdrawn)</span>
          </button>
        </div>

        {/* Search & Category Filter Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
          <div className="flex-1 max-w-md">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="शीर्षक, संदर्भ क्रमांक किंवा विभागाने शोधा (Search title, ref, or dept)..."
              className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
            />
          </div>

          <div className="flex items-center gap-2 text-xs">
            <label className="text-slate-500 font-medium whitespace-nowrap">प्रवर्ग (Category):</label>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
            >
              <option value="all">सर्व प्रवर्ग (All Categories)</option>
              <option value="resolution">ठराव व इतिवृत्त (Resolutions & Minutes)</option>
              <option value="tender">निविदा दस्तऐवज (Tender Documents)</option>
              <option value="budget">अंदाजपत्रक व लेखापरीक्षण (Budget & Audit)</option>
              <option value="citizen_charter">नागरिक सनद व अर्ज (Citizen Charter & Forms)</option>
              <option value="statutory_report">वैधानिक व प्रशासकीय अहवाल (Statutory Reports)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Documents List */}
      <div className="space-y-4">
        {loading ? (
          <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-slate-500 text-xs shadow-sm">
            {t.cmsDocuments.loading}
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className="p-10 text-center bg-white rounded-lg border border-slate-200 text-slate-600 text-xs shadow-sm">
            {searchQuery || selectedCategory !== 'all' || activeTab !== 'all'
              ? 'निवडलेल्या निकषांनुसार कोणतेही दस्तऐवज आढळले नाहीत. (No matching documents found).'
              : t.cmsDocuments.emptyList}
          </div>
        ) : (
          filteredDocuments.map((doc) => (
            <div
              key={doc.id}
              className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 shadow-sm hover:border-slate-300 transition-all"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2 py-0.5 bg-blue-50 text-blue-800 border border-blue-200 rounded text-[10px] font-bold uppercase font-mono">
                    {doc.category_display || doc.category}
                  </span>
                  {doc.reference_number && (
                    <span className="text-xs text-slate-500 font-mono">
                      {t.cmsDocuments.referenceNo}: {doc.reference_number}
                    </span>
                  )}
                  {doc.issuing_department && (
                    <span className="text-xs text-slate-500">
                      • {doc.issuing_department}
                    </span>
                  )}
                  {doc.is_confidential && (
                    <Badge variant="danger">{t.cmsDocuments.confidentialBadge}</Badge>
                  )}
                  {doc.retention_hold && (
                    <Badge variant="warning">{t.cmsDocuments.retentionHoldBadge}</Badge>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setInspectDoc(doc)}
                    className="px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-800 border border-blue-200 rounded text-xs font-semibold transition-colors inline-flex items-center gap-1"
                  >
                    <span aria-hidden="true">🔍</span>
                    <span>तपशील पहा (View Details)</span>
                  </button>

                  <button
                    onClick={() => setShowReplaceModal(doc.id)}
                    className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded text-xs font-medium transition-colors inline-flex items-center gap-1"
                  >
                    <span aria-hidden="true">+</span>
                    <span>{t.cmsDocuments.replaceVersion}</span>
                  </button>
                </div>
              </div>

              {/* Translations & Versions */}
              <div className="space-y-3 pt-1">
                {doc.translations.map((trans) => (
                  <div key={trans.id} className="bg-slate-50 rounded-lg p-3.5 border border-slate-200 space-y-2.5">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-white text-slate-800 border border-slate-300 font-mono text-[10px] uppercase rounded font-bold">
                          {trans.language_code}
                        </span>
                        <span className="text-xs font-bold text-slate-900">{trans.title}</span>
                        <Badge
                          variant={
                            trans.status === 'disclosed'
                              ? 'success'
                              : trans.status === 'withdrawn'
                              ? 'danger'
                              : trans.status === 'pending_approval'
                              ? 'warning'
                              : 'neutral'
                          }
                        >
                          {trans.status === 'disclosed'
                            ? 'प्रसिद्ध / Disclosed'
                            : trans.status === 'withdrawn'
                            ? 'मागे घेतलेले / Withdrawn'
                            : trans.status}
                        </Badge>
                      </div>

                      {/* Withdrawal Action for Super Admins on Disclosed Documents */}
                      {trans.status === 'disclosed' && isSuperAdmin && (
                        <button
                          onClick={() => setWithdrawModal({ transId: trans.id, docTitle: trans.title })}
                          className="px-2.5 py-1 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-300 rounded text-xs font-semibold transition-colors inline-flex items-center gap-1 shadow-sm self-start sm:self-auto"
                        >
                          <span aria-hidden="true">🚫</span>
                          <span>मागे घ्या (Withdraw from Portal)</span>
                        </button>
                      )}
                    </div>

                    {/* Versions list */}
                    <div className="space-y-1.5 pt-1">
                      {trans.versions.map((ver) => (
                        <div
                          key={ver.id}
                          className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2.5 bg-white rounded-md border border-slate-200 text-xs text-slate-700"
                        >
                          <div className="space-y-0.5">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-[11px] text-blue-700 font-bold">
                                v{ver.version_number}
                              </span>
                              <span className="font-medium text-slate-900">{ver.original_filename}</span>
                              <span className="text-[10px] text-slate-500 font-mono">
                                ({(ver.file_size_bytes / 1024).toFixed(1)} KB)
                              </span>
                              <Badge
                                variant={
                                  ver.disclosure_status === 'approved_for_disclosure'
                                    ? 'success'
                                    : ver.disclosure_status === 'pending_approval'
                                    ? 'warning'
                                    : 'neutral'
                                }
                              >
                                {ver.disclosure_status}
                              </Badge>
                            </div>
                            <div
                              className="text-[10px] font-mono text-slate-500 truncate max-w-sm"
                              title={ver.checksum_sha256}
                            >
                              SHA-256: {ver.checksum_sha256}
                            </div>
                          </div>

                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            {/* Download Link */}
                            <a
                              href={`${getApiBaseUrl()}/api/cms/documents/versions/${ver.id}/download/`}
                              target="_blank"
                              rel="noreferrer"
                              className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded text-[10px] font-medium transition-colors inline-flex items-center gap-1"
                            >
                              <span aria-hidden="true">📥</span>
                              <span>{t.cmsDocuments.downloadFile}</span>
                            </a>

                            {/* Operator / Super Admin primary workflow actions */}
                            {ver.disclosure_status === 'draft' && !doc.is_confidential && (
                              <button
                                onClick={() => handleSubmitForDisclosure(ver.id)}
                                className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[10px] font-semibold shadow-sm transition-colors"
                              >
                                {t.governance.btnSubmitReview}
                              </button>
                            )}

                            {ver.disclosure_status === 'pending_approval' && (
                              isSuperAdmin ? (
                                <button
                                  onClick={() => handleApproveDisclosure(ver.id)}
                                  className="px-2.5 py-1 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-[10px] font-semibold shadow-sm transition-colors inline-flex items-center gap-1"
                                >
                                  <span aria-hidden="true">✓</span>
                                  <span>{t.cmsDocuments.discloseAction}</span>
                                </button>
                              ) : (
                                <span className="px-2.5 py-1 bg-amber-50 text-amber-800 border border-amber-300 rounded text-[10px] font-semibold">
                                  {t.governance.btnAwaitingReview}
                                </span>
                              )
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

      {/* Complete Record Details Modal (Workstream A3) */}
      {inspectDoc && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">📋</span>
                <span>दस्तऐवज संपूर्ण माहिती (Complete Document Record Details)</span>
              </h3>
              <button
                onClick={() => setInspectDoc(null)}
                aria-label="Close"
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-slate-50 p-3.5 rounded-lg border border-slate-200">
              <div>
                <span className="text-slate-500 font-medium">दस्तऐवज आयडी (UUID): </span>
                <span className="font-mono text-slate-800 text-[11px] block">{inspectDoc.id}</span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">संदर्भ क्रमांक (Ref No): </span>
                <span className="font-mono font-bold text-slate-900 block">{inspectDoc.reference_number || 'उपलब्ध नाही'}</span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">प्रवर्ग (Category): </span>
                <span className="font-semibold text-blue-900 block">{inspectDoc.category_display || inspectDoc.category}</span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">जारी करणारा विभाग (Department): </span>
                <span className="font-semibold text-slate-800 block">{inspectDoc.issuing_department}</span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">जारी दिनांक (Issue Date): </span>
                <span className="text-slate-800 block">{inspectDoc.issue_date || 'उपलब्ध नाही'}</span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">नोंदणी दिनांक (Created At): </span>
                <span className="text-slate-800 block">{new Date(inspectDoc.created_at).toLocaleString('en-IN')}</span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">गोपनीयता (Confidentiality): </span>
                <span className="block">
                  {inspectDoc.is_confidential ? (
                    <Badge variant="danger">गोपनीय / Restricted</Badge>
                  ) : (
                    <Badge variant="neutral">सार्वजनिक / Public</Badge>
                  )}
                </span>
              </div>
              <div>
                <span className="text-slate-500 font-medium">धारणा स्थगिती (Retention Hold): </span>
                <span className="block">
                  {inspectDoc.retention_hold ? (
                    <Badge variant="warning">होय / Active Hold</Badge>
                  ) : (
                    <span className="text-slate-600 font-medium">नाही / None</span>
                  )}
                </span>
              </div>
            </div>

            {/* Translation & Version Details */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                उपलब्ध भाषांतरे व आवृत्त्या (Translations & Versions)
              </h4>
              {inspectDoc.translations.map((t) => (
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
                        t.status === 'disclosed'
                          ? 'success'
                          : t.status === 'withdrawn'
                          ? 'danger'
                          : 'neutral'
                      }
                    >
                      {t.status}
                    </Badge>
                  </div>

                  {t.description && (
                    <p className="text-slate-600 text-xs">{t.description}</p>
                  )}

                  {t.publication_date && (
                    <div className="text-[11px] text-slate-500">
                      प्रकाशन दिनांक: <strong>{new Date(t.publication_date).toLocaleString('en-IN')}</strong>
                      {t.published_by && <span> • प्राधिकृत अधिकारी: <strong>{t.published_by}</strong></span>}
                    </div>
                  )}

                  {/* Versions Table */}
                  <div className="space-y-1.5 pt-1">
                    <span className="text-[11px] font-bold text-slate-700 block">फाईल आवृत्त्या (File Versions):</span>
                    {t.versions.map((v) => (
                      <div
                        key={v.id}
                        className="p-2 bg-slate-50 rounded border border-slate-200 text-[11px] flex flex-col sm:flex-row sm:items-center justify-between gap-1.5"
                      >
                        <div>
                          <span className="font-mono font-bold text-blue-700">v{v.version_number}</span>{' '}
                          <span className="font-medium text-slate-900">{v.original_filename}</span>{' '}
                          <span className="text-slate-500">({(v.file_size_bytes / 1024).toFixed(1)} KB)</span>{' '}
                          <span className="font-mono text-slate-400 text-[10px]">[{v.disclosure_status}]</span>
                          <div className="text-[10px] font-mono text-slate-500">SHA-256: {v.checksum_sha256}</div>
                        </div>
                        <a
                          href={`${getApiBaseUrl()}/api/cms/documents/versions/${v.id}/download/`}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2 py-0.5 bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 rounded text-[10px] font-medium transition-colors shrink-0"
                        >
                          डाउनलोड 📥
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end pt-3 border-t border-slate-200">
              <button
                type="button"
                onClick={() => setInspectDoc(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold"
              >
                बंद करा (Close)
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Withdrawal Confirmation Dialog (Workstream A4) */}
      {withdrawModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-md w-full p-6 space-y-4 shadow-2xl text-slate-900">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-rose-700 flex items-center gap-2">
                <span aria-hidden="true">🚫</span>
                <span>दस्तऐवज मागे घेण्याची पुष्टी (Withdraw from Public Portal)</span>
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
                <strong>सावधान:</strong> हा दस्तऐवज (<strong>{withdrawModal.docTitle}</strong>) सार्वजनिक संकेतस्थळावरून तात्काळ काढला जाईल आणि सामान्य नागरिक डाऊनलोड करू शकणार नाहीत.
              </p>
              <p className="text-[11px] text-rose-600">
                दस्तऐवजाची मूळ फाईल व आवृत्ती कायदेशीर ऑडिटसाठी लेजरमध्ये सुरक्षित ठेवली जाईल.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                मागे घेण्याचे वैधानिक औचित्य / कारण (Withdrawal Justification):
              </label>
              <textarea
                rows={3}
                required
                value={withdrawReason}
                onChange={(e) => setWithdrawReason(e.target.value)}
                placeholder="उदा. सक्षम अधिकाऱ्यांच्या निर्देशानुसार सुधारित मसुद्यासाठी हा दस्तऐवज मागे घेण्यात येत आहे..."
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
                onClick={handleConfirmWithdraw}
                className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold shadow-sm disabled:opacity-50"
              >
                {withdrawLoading ? 'प्रक्रिया सुरू आहे...' : 'मागे घ्या (Confirm Withdrawal)'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Upload Document Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">📑</span>
                <span>{t.cmsDocuments.uploadDocument}</span>
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                aria-label="Close"
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateDocument} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsDocuments.docTitle}:
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="उदा. ग्रामसभा ठराव क्र. १२/२०२६"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsDocuments.category}:
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  >
                    <option value="resolution">ठराव व इतिवृत्त (Resolutions & Minutes)</option>
                    <option value="tender">निविदा दस्तऐवज (Tender Documents)</option>
                    <option value="budget">अंदाजपत्रक व लेखापरीक्षण (Budget & Audit)</option>
                    <option value="citizen_charter">नागरिक सनद व अर्ज (Citizen Charter & Forms)</option>
                    <option value="statutory_report">वैधानिक व प्रशासकीय अहवाल (Statutory Reports)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsDocuments.referenceNo}:
                  </label>
                  <input
                    type="text"
                    value={refNo}
                    onChange={(e) => setRefNo(e.target.value)}
                    placeholder="उदा. GP/2026/RES-12"
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsDocuments.department}:
                </label>
                <input
                  type="text"
                  required
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsDocuments.file}:
                </label>
                <input
                  type="file"
                  required
                  accept=".pdf,.doc,.docx"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white file:mr-2 file:py-1 file:px-2.5 file:rounded file:border-0 file:text-[11px] file:bg-blue-50 file:text-blue-700 file:font-semibold hover:file:bg-blue-100"
                />
              </div>

              <div className="space-y-2 pt-1 border-t border-slate-100">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isConfidential}
                    onChange={(e) => setIsConfidential(e.target.checked)}
                    className="rounded text-[#1e3a8a] focus:ring-blue-600"
                  />
                  <span className="text-slate-700 font-medium">
                    {t.cmsDocuments.isConfidential}
                  </span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={retentionHold}
                    onChange={(e) => setRetentionHold(e.target.checked)}
                    className="rounded text-[#1e3a8a] focus:ring-blue-600"
                  />
                  <span className="text-slate-700 font-medium">
                    {t.cmsDocuments.retentionHold}
                  </span>
                </label>

                {isSuperAdmin && (
                  <label className="flex items-center gap-2 cursor-pointer bg-blue-50 border border-blue-200 p-2 rounded-lg">
                    <input
                      type="checkbox"
                      checked={publishNow}
                      onChange={(e) => setPublishNow(e.target.checked)}
                      className="rounded text-[#1e3a8a] focus:ring-blue-600"
                    />
                    <div>
                      <span className="text-[#1e3a8a] font-bold block">{t.cmsDocuments.publishNow}</span>
                      <span className="text-[11px] text-blue-700 block">{t.governance.publishNowHelp}</span>
                    </div>
                  </label>
                )}
              </div>

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
                  {submitting ? t.common.loading : t.common.save}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Replace Version Modal */}
      {showReplaceModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-md w-full p-6 space-y-4 shadow-2xl text-slate-900">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900">
                {t.cmsDocuments.replaceVersion}
              </h3>
              <button
                onClick={() => setShowReplaceModal(null)}
                aria-label="Close"
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={(e) => handleReplaceVersion(e, showReplaceModal)} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  नवीन फाईल निवडा (Select New File):
                </label>
                <input
                  type="file"
                  required
                  accept=".pdf,.doc,.docx"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white file:mr-2 file:py-1 file:px-2.5 file:rounded file:border-0 file:text-[11px] file:bg-blue-50 file:text-blue-700 file:font-semibold hover:file:bg-blue-100"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowReplaceModal(null)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.close}
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
    </div>
  );
}
