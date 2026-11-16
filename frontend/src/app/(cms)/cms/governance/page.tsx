'use client';

import React, { useEffect, useState, useRef } from 'react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { useLanguage } from '@/context/LanguageContext';
import { fetchCmsPendingSubmissions, executeGovernanceAction, fetchAuthMe, getApiBaseUrl } from '@/lib/api';
import type { CmsPendingItem, GovernanceActionPayload, AuthUser } from '@/lib/types';

export default function CmsGovernancePage() {
  const { t } = useLanguage();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [items, setItems] = useState<CmsPendingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'pending' | 'approved' | 'published' | 'all'>('pending');

  const [actionModal, setActionModal] = useState<{
    item: CmsPendingItem;
    type: 'approve' | 'reject' | 'publish' | 'inspect';
  } | null>(null);

  const [notes, setNotes] = useState('');
  const [reason, setReason] = useState('');
  const [justification, setJustification] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const currentRequestId = useRef(0);

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

  async function loadQueue(tab: 'pending' | 'approved' | 'published' | 'all' = activeTab) {
    const reqId = ++currentRequestId.current;
    setLoading(true);
    try {
      const res = await fetchCmsPendingSubmissions(tab);
      if (reqId === currentRequestId.current) {
        if (res) {
          setItems(res.results);
        } else {
          setItems([]);
        }
      }
    } catch (err) {
      if (reqId === currentRequestId.current) {
        console.error('Failed to load governance queue', err);
        setItems([]);
      }
    } finally {
      if (reqId === currentRequestId.current) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    loadUser();
    loadQueue('pending');
  }, []);

  function handleTabChange(tab: 'pending' | 'approved' | 'published' | 'all') {
    setActiveTab(tab);
    setFeedback(null);
    loadQueue(tab);
  }

  async function handleConfirmAction() {
    if (!actionModal || actionModal.type === 'inspect') return;
    const { item, type } = actionModal;

    if (type === 'reject' && reason.trim().length < 10) {
      setFeedback({
        type: 'error',
        message: 'नकाराचे कारण किमान १० अक्षरांचे असणे बंधनकारक आहे. (Rejection reason must be at least 10 characters).',
      });
      return;
    }

    if (type === 'publish' && justification.trim().length < 10) {
      setFeedback({
        type: 'error',
        message: 'प्रकाशन समर्थन शेरा किमान १० अक्षरांचा असणे बंधनकारक आहे. (Publication justification must be at least 10 characters).',
      });
      return;
    }

    setActionLoading(true);
    setFeedback(null);

    const payload: GovernanceActionPayload = {
      entity_type: item.entity_type,
      action: type,
      target_id: item.translation_id || item.target_id || item.entity_id,
      revision_id: item.revision_id || item.version_id || item.entity_id,
      notes: notes.trim(),
      reason: reason.trim(),
      justification: justification.trim(),
    };

    const res = await executeGovernanceAction(payload);
    setActionLoading(false);

    if (res.success) {
      let successMsg = t.governance.successApprove;
      if (type === 'reject') successMsg = t.governance.successReject;
      if (type === 'publish') successMsg = t.governance.successPublish;

      setFeedback({
        type: 'success',
        message: successMsg,
      });
      setActionModal(null);
      setNotes('');
      setReason('');
      setJustification('');
      loadQueue(activeTab);
    } else {
      setFeedback({
        type: 'error',
        message: res.error || 'कार्यवाही अयशस्वी झाली. कृपया पुन्हा प्रयत्न करा. (Action failed)',
      });
    }
  }

  const steps = [
    { title: t.governance.step1Title, actor: t.governance.step1Actor, desc: t.governance.step1Desc },
    { title: t.governance.step2Title, actor: t.governance.step2Actor, desc: t.governance.step2Desc },
    { title: t.governance.step3Title, actor: t.governance.step3Actor, desc: t.governance.step3Desc },
    { title: t.governance.step4Title, actor: t.governance.step4Actor, desc: t.governance.step4Desc },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white p-5 rounded-lg border shadow-sm">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span>🛡️</span>
            <span>{t.governance.pageTitle}</span>
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            {t.governance.pageSubtitle}
          </p>
        </div>
        <button
          onClick={() => loadQueue(activeTab)}
          disabled={loading}
          className="px-3.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md text-xs font-semibold border border-slate-300 self-start sm:self-auto transition-colors inline-flex items-center gap-1.5 shadow-sm"
        >
          <span>🔄</span>
          <span>{loading ? 'लोड होत आहे...' : t.governance.refresh}</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-2">
        <button
          onClick={() => handleTabChange('pending')}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all flex items-center gap-2 ${
            activeTab === 'pending'
              ? 'bg-[#1e3a8a] text-white shadow-sm ring-2 ring-blue-700'
              : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
          }`}
        >
          <span>⏳</span>
          <span>{t.governance.tabPending}</span>
          {activeTab === 'pending' && items.length > 0 && (
            <span className="px-1.5 py-0.2 bg-amber-500 text-white rounded-full text-[10px] font-bold">
              {items.length}
            </span>
          )}
        </button>

        <button
          onClick={() => handleTabChange('approved')}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all flex items-center gap-2 ${
            activeTab === 'approved'
              ? 'bg-[#1e3a8a] text-white shadow-sm ring-2 ring-blue-700'
              : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
          }`}
        >
          <span>✅</span>
          <span>{t.governance.tabApproved}</span>
          {activeTab === 'approved' && items.length > 0 && (
            <span className="px-1.5 py-0.2 bg-emerald-600 text-white rounded-full text-[10px] font-bold">
              {items.length}
            </span>
          )}
        </button>

        <button
          onClick={() => handleTabChange('published')}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all flex items-center gap-2 ${
            activeTab === 'published'
              ? 'bg-[#1e3a8a] text-white shadow-sm ring-2 ring-blue-700'
              : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
          }`}
        >
          <span>🌐</span>
          <span>{t.governance.tabPublished}</span>
        </button>

        <button
          onClick={() => handleTabChange('all')}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all flex items-center gap-2 ${
            activeTab === 'all'
              ? 'bg-[#1e3a8a] text-white shadow-sm ring-2 ring-blue-700'
              : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
          }`}
        >
          <span>📋</span>
          <span>{t.governance.tabAll}</span>
        </button>
      </div>

      {/* Feedback Alert */}
      {feedback && (
        <Alert
          severity={feedback.type === 'success' ? 'info' : 'danger'}
          title={feedback.type === 'success' ? 'यशस्वी (Success)' : 'त्रुटी (Error)'}
        >
          <p>{feedback.message}</p>
        </Alert>
      )}

      {/* Items Queue Section */}
      <section>
        {loading ? (
          <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-slate-500 text-xs shadow-sm">
            माहिती लोड होत आहे... (Loading governance items...)
          </div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center bg-white rounded-lg border border-slate-200 text-slate-600 text-xs shadow-sm space-y-2">
            <span className="text-3xl block">🎉</span>
            <p className="font-semibold text-slate-800 text-sm">
              {activeTab === 'pending'
                ? t.governance.emptyPending
                : activeTab === 'approved'
                ? t.governance.emptyApproved
                : activeTab === 'published'
                ? t.governance.emptyPublished
                : t.governance.emptyAll}
            </p>
            <p className="text-slate-500 text-[11px]">
              सर्व प्रशासकीय प्रक्रिया अद्ययावत आहेत. (All records are up to date.)
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item, idx) => {
              const isSuperAdmin = currentUser?.role === 'super_admin';
              const isAuthor = Boolean(
                currentUser && (
                  (item.author_id && String(currentUser.id) === String(item.author_id)) ||
                  (item.author_name && (currentUser.email === item.author_name || currentUser.full_name === item.author_name))
                )
              );
              const isPendingReview = item.status === 'submitted' || item.status === 'pending_approval';
              const cannotApprove = (!isSuperAdmin && isAuthor) || item.can_approve === false;
              const canPublishItem = isSuperAdmin || item.can_publish || (item.status === 'approved' && item.translation_status !== 'published');

              return (
                <div
                  key={`${item.entity_type}-${item.revision_id || item.version_id || item.entity_id}-${idx}`}
                  className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm hover:border-slate-300 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-2 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="px-2 py-0.5 bg-blue-50 text-blue-800 border border-blue-200 rounded text-[10px] font-bold uppercase tracking-wider">
                        {item.entity_type}
                      </span>
                      <span className="px-2 py-0.5 bg-slate-100 text-slate-700 border border-slate-200 rounded text-[10px] uppercase font-mono font-bold">
                        {item.language_code}
                      </span>
                      {item.version_number && (
                        <span className="text-[11px] text-slate-500 font-mono font-medium">
                          v{item.version_number}
                        </span>
                      )}
                      {item.status && (
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                            isPendingReview
                              ? 'bg-amber-50 text-amber-800 border-amber-300'
                              : item.status === 'approved'
                              ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                              : item.status === 'published'
                              ? 'bg-blue-50 text-blue-800 border-blue-300'
                              : 'bg-slate-100 text-slate-700 border-slate-300'
                          }`}
                        >
                          {item.status}
                        </span>
                      )}
                      <h3 className="text-sm font-bold text-slate-900">{item.title}</h3>
                    </div>

                    {item.summary && (
                      <p className="text-xs text-slate-600 line-clamp-2">{item.summary}</p>
                    )}

                    <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 pt-1 border-t border-slate-100">
                      <span>
                        {t.governance.submittedBy}: <strong className="text-slate-800">{item.author_name}</strong>
                      </span>
                      <span>•</span>
                      <span>
                        {t.governance.submittedAt}: {new Date(item.submitted_at).toLocaleString('en-IN')}
                      </span>
                      {item.content_hash && (
                        <>
                          <span>•</span>
                          <span className="font-mono text-[10px] text-slate-500 truncate max-w-[140px]" title={item.content_hash}>
                            SHA: {item.content_hash.slice(0, 10)}...
                          </span>
                        </>
                      )}
                    </div>

                    {/* Proactive Anti-Self-Approval Alert for Operators ONLY */}
                    {!isSuperAdmin && isAuthor && isPendingReview && (
                      <div className="mt-2 text-xs bg-amber-50 text-amber-800 border border-amber-200 px-2.5 py-1 rounded inline-flex items-center gap-1.5 font-medium">
                        <span aria-hidden="true">⚠️</span>
                        <span>{t.governance.antiSelfApprovalWarning}</span>
                      </div>
                    )}
                  </div>

                  {/* Action Controls */}
                  <div className="flex flex-wrap items-center gap-2 shrink-0 self-start md:self-center">
                    {/* Inspect Full Submission Details */}
                    <button
                      onClick={() => {
                        setActionModal({ item, type: 'inspect' });
                        setNotes('');
                        setReason('');
                        setJustification('');
                        setFeedback(null);
                      }}
                      className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded text-xs font-semibold inline-flex items-center gap-1.5 transition-colors"
                      title="सर्व सादर केलेले तपशील तपासा (Inspect full submission)"
                    >
                      <span aria-hidden="true">🔍</span>
                      <span>तपशील (Inspect)</span>
                    </button>

                    {/* Approve Action */}
                    {isPendingReview && (
                      <button
                        disabled={cannotApprove}
                        onClick={() => {
                          setActionModal({ item, type: 'approve' });
                          setNotes('');
                          setReason('');
                          setJustification('');
                          setFeedback(null);
                        }}
                        className={`px-3 py-1.5 rounded text-xs font-semibold inline-flex items-center gap-1.5 transition-colors shadow-sm ${
                          cannotApprove
                            ? 'bg-slate-100 text-slate-400 border border-slate-300 cursor-not-allowed opacity-60'
                            : 'bg-emerald-600 hover:bg-emerald-700 text-white'
                        }`}
                        title={cannotApprove ? t.governance.antiSelfApprovalWarning : undefined}
                      >
                        <span aria-hidden="true">✓</span>
                        <span>{t.governance.btnApprove}</span>
                      </button>
                    )}

                    {/* Reject Action */}
                    {isPendingReview && (
                      <button
                        onClick={() => {
                          setActionModal({ item, type: 'reject' });
                          setNotes('');
                          setReason('');
                          setJustification('');
                          setFeedback(null);
                        }}
                        className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded text-xs font-semibold inline-flex items-center gap-1.5 transition-colors shadow-sm"
                      >
                        <span aria-hidden="true">✕</span>
                        <span>{t.governance.btnReject}</span>
                      </button>
                    )}

                    {/* Publish Action (for approved items or Super Admin direct publish) */}
                    {(canPublishItem || (isSuperAdmin && isPendingReview)) && (
                      <button
                        onClick={() => {
                          setActionModal({ item, type: 'publish' });
                          setNotes('');
                          setReason('');
                          setJustification('');
                          setFeedback(null);
                        }}
                        className="px-3 py-1.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-xs font-semibold inline-flex items-center gap-1.5 transition-colors shadow-sm"
                      >
                        <span aria-hidden="true">🚀</span>
                        <span>{t.governance.btnPublish}</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Interactive Modal Dialog for Inspect / Approve / Reject / Publish */}
      {actionModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white border border-slate-200 rounded-xl max-w-3xl w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold flex items-center gap-2">
                {actionModal.type === 'inspect' && (
                  <span className="text-slate-900 flex items-center gap-1.5">
                    <span aria-hidden="true">🔍</span>
                    <span>तपशील पुनरावलोकन व निर्णय (Inspect Submission & Review)</span>
                  </span>
                )}
                {actionModal.type === 'approve' && (
                  <span className="text-emerald-700 flex items-center gap-1.5">
                    <span aria-hidden="true">✓</span>
                    <span>{t.governance.modalApproveTitle}</span>
                  </span>
                )}
                {actionModal.type === 'reject' && (
                  <span className="text-rose-700 flex items-center gap-1.5">
                    <span aria-hidden="true">✕</span>
                    <span>{t.governance.modalRejectTitle}</span>
                  </span>
                )}
                {actionModal.type === 'publish' && (
                  <span className="text-blue-900 flex items-center gap-1.5">
                    <span aria-hidden="true">🚀</span>
                    <span>{t.governance.modalPublishTitle}</span>
                  </span>
                )}
              </h3>
              <button
                onClick={() => setActionModal(null)}
                aria-label="Close modal"
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded hover:bg-slate-100 transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Target Item Metadata Summary */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs">
              <div>
                <strong className="text-slate-600 block">शीर्षक (Title):</strong>
                <span className="text-slate-900 font-semibold">{actionModal.item.title}</span>
              </div>
              <div>
                <strong className="text-slate-600 block">डोमेन व भाषा:</strong>
                <span className="text-blue-800 font-semibold uppercase">{actionModal.item.entity_type}</span>{' '}
                <span className="px-1.5 py-0.2 bg-slate-200 text-slate-700 font-mono text-[10px] uppercase rounded">
                  {actionModal.item.language_code}
                </span>
                {actionModal.item.version_number && (
                  <span className="text-slate-500 font-mono ml-1">v{actionModal.item.version_number}</span>
                )}
              </div>
              <div>
                <strong className="text-slate-600 block">{t.governance.submittedBy}:</strong>
                <span className="text-slate-900 font-medium">{actionModal.item.author_name}</span>
              </div>
              <div>
                <strong className="text-slate-600 block">{t.governance.submittedAt}:</strong>
                <span className="text-slate-700">
                  {new Date(actionModal.item.submitted_at).toLocaleString('en-IN')}
                </span>
              </div>
              <div>
                <strong className="text-slate-600 block">सद्य स्थिती:</strong>
                <span className="font-semibold text-slate-800 uppercase">{actionModal.item.status}</span>
              </div>
              <div>
                <strong className="text-slate-600 block">Content Hash (SHA-256):</strong>
                <span className="font-mono text-[10px] text-slate-500 truncate block" title={actionModal.item.content_hash}>
                  {actionModal.item.content_hash ? `${actionModal.item.content_hash.slice(0, 16)}...` : 'None'}
                </span>
              </div>
            </div>

            {/* Complete Submitted Content Inspection Panel */}
            <div className="space-y-3 pt-1">
              <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5 border-b border-slate-200 pb-1.5">
                <span>📄</span>
                <span>सादर केलेला संपूर्ण तपशील (Submitted Content Fields)</span>
              </h4>

              {/* Page Domain */}
              {actionModal.item.entity_type === 'page' && (
                <div className="space-y-2 text-xs">
                  {actionModal.item.slug && (
                    <div>
                      <span className="text-slate-500 font-bold block">Page URL / Slug:</span>
                      <span className="font-mono text-blue-800 bg-slate-50 px-2 py-1 rounded border border-slate-200 block">
                        /{actionModal.item.slug}
                      </span>
                    </div>
                  )}
                  {actionModal.item.summary && (
                    <div>
                      <span className="text-slate-500 font-bold block">संक्षिप्त सारांश (Summary):</span>
                      <p className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800">
                        {actionModal.item.summary}
                      </p>
                    </div>
                  )}
                  <div>
                    <span className="text-slate-500 font-bold block">मुख्य मजकूर (Markdown Content):</span>
                    <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 font-mono text-[11px] text-slate-800 whitespace-pre-wrap max-h-56 overflow-y-auto">
                      {actionModal.item.body_markdown || 'मजकूर उपलब्ध नाही'}
                    </div>
                  </div>
                </div>
              )}

              {/* Notice Domain */}
              {actionModal.item.entity_type === 'notice' && (
                <div className="space-y-2 text-xs">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <div>
                      <span className="text-slate-500 font-bold block">सूचना प्रकार (Notice Type):</span>
                      <span className="font-semibold text-slate-800">
                        {actionModal.item.notice_type_display || actionModal.item.notice_type}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">संदर्भ क्रमांक (Ref No):</span>
                      <span className="font-mono text-slate-800">
                        {actionModal.item.reference_number || 'उपलब्ध नाही'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">तातडीची सूचना (Urgent):</span>
                      <span className={actionModal.item.is_urgent ? 'text-rose-700 font-bold' : 'text-slate-600'}>
                        {actionModal.item.is_urgent ? 'होय (Urgent Statutory)' : 'नाही'}
                      </span>
                    </div>
                  </div>

                  {(actionModal.item.effective_from || actionModal.item.effective_to) && (
                    <div className="text-[11px] text-slate-600 bg-blue-50 p-2 rounded border border-blue-200">
                      प्रभावी कालावधी:{' '}
                      <strong>{actionModal.item.effective_from ? new Date(actionModal.item.effective_from).toLocaleDateString('en-IN') : 'तात्काळ'}</strong>
                      {' '}ते{' '}
                      <strong>{actionModal.item.effective_to ? new Date(actionModal.item.effective_to).toLocaleDateString('en-IN') : 'पुढील आदेशापर्यंत'}</strong>
                    </div>
                  )}

                  {actionModal.item.summary && (
                    <div>
                      <span className="text-slate-500 font-bold block">संक्षिप्त सारांश (Summary):</span>
                      <p className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800">
                        {actionModal.item.summary}
                      </p>
                    </div>
                  )}

                  <div>
                    <span className="text-slate-500 font-bold block">सूचनेचा संपूर्ण मजकूर (Full Body):</span>
                    <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 font-mono text-[11px] text-slate-800 whitespace-pre-wrap max-h-56 overflow-y-auto">
                      {actionModal.item.body_markdown || actionModal.item.summary || 'मजकूर उपलब्ध नाही'}
                    </div>
                  </div>
                </div>
              )}

              {/* Document Domain */}
              {actionModal.item.entity_type === 'document' && (
                <div className="space-y-2 text-xs">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <div>
                      <span className="text-slate-500 font-bold block">प्रवर्ग (Category):</span>
                      <span className="font-semibold text-slate-800">
                        {actionModal.item.category_display || actionModal.item.category}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">संदर्भ क्र. (Ref No):</span>
                      <span className="font-mono text-slate-800">
                        {actionModal.item.reference_number || 'उपलब्ध नाही'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">विभाग (Department):</span>
                      <span className="text-slate-800">
                        {actionModal.item.issuing_department || 'ग्रामपंचायत कार्यालय'}
                      </span>
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold text-slate-900">{actionModal.item.original_filename}</div>
                      <div className="text-[11px] text-slate-500">
                        आकार: {((actionModal.item.file_size_bytes || 0) / 1024).toFixed(1)} KB • MIME: {actionModal.item.mime_type || 'application/pdf'}
                      </div>
                      <div className="font-mono text-[10px] text-slate-500 mt-0.5">
                        SHA-256: {actionModal.item.checksum_sha256}
                      </div>
                    </div>
                    {actionModal.item.download_url && (
                      <a
                        href={`${getApiBaseUrl()}${actionModal.item.download_url}`}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-1.5 bg-[#1e3a8a] text-white hover:bg-blue-900 rounded text-xs font-semibold shrink-0 transition-colors inline-flex items-center gap-1"
                      >
                        <span>डाउनलोड व तपासणी 📥</span>
                      </a>
                    )}
                  </div>
                </div>
              )}

              {/* Event Domain */}
              {actionModal.item.entity_type === 'event' && (
                <div className="space-y-2 text-xs">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <div>
                      <span className="text-slate-500 font-bold block">सभा प्रकार (Meeting Type):</span>
                      <span className="font-semibold text-slate-800">
                        {actionModal.item.event_type_display || actionModal.item.event_type}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">अध्यक्ष / पीठसीन अधिकारी:</span>
                      <span className="text-slate-800">
                        {actionModal.item.meeting_chair || 'सरपंच / ग्रामसेवक'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">वैधानिक सभा (Statutory):</span>
                      <span className={actionModal.item.is_statutory ? 'text-emerald-700 font-bold' : 'text-slate-600'}>
                        {actionModal.item.is_statutory ? 'होय (Statutory Gram Sabha)' : 'नाही'}
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div>
                      <span className="text-slate-500 font-bold block">स्थान / ठिकाण (Venue):</span>
                      <span className="text-slate-800 bg-slate-50 px-2.5 py-1.5 rounded border border-slate-200 block">
                        {actionModal.item.venue || actionModal.item.venue_mr}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">दिनांक व वेळ (Date & Time):</span>
                      <span className="text-slate-800 bg-slate-50 px-2.5 py-1.5 rounded border border-slate-200 block">
                        {actionModal.item.start_datetime ? new Date(actionModal.item.start_datetime).toLocaleString('en-IN') : ''}
                        {' '}ते{' '}
                        {actionModal.item.end_datetime ? new Date(actionModal.item.end_datetime).toLocaleTimeString('en-IN') : ''}
                      </span>
                    </div>
                  </div>

                  <div>
                    <span className="text-slate-500 font-bold block">सभेची विषयपत्रिका (Meeting Agenda):</span>
                    <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 text-slate-800 whitespace-pre-wrap max-h-40 overflow-y-auto">
                      {actionModal.item.agenda || 'विषयपत्रिका उपलब्ध नाही'}
                    </div>
                  </div>

                  {actionModal.item.description && (
                    <div>
                      <span className="text-slate-500 font-bold block">सविस्तर वर्णन (Description):</span>
                      <p className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800">
                        {actionModal.item.description}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Scheme Domain */}
              {actionModal.item.entity_type === 'scheme' && (
                <div className="space-y-2 text-xs">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <div>
                      <span className="text-slate-500 font-bold block">योजना स्तर (Level):</span>
                      <span className="font-semibold text-blue-900">
                        {actionModal.item.scheme_level_display || actionModal.item.scheme_level}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">लक्षित लाभार्थी:</span>
                      <span className="font-semibold text-emerald-800">
                        {actionModal.item.target_beneficiary_display || actionModal.item.target_beneficiary}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">Slug:</span>
                      <span className="font-mono text-slate-800">/{actionModal.item.slug}</span>
                    </div>
                  </div>

                  {actionModal.item.official_portal_url && (
                    <div>
                      <span className="text-slate-500 font-bold block">शासकीय अधिकृत पोर्टल:</span>
                      <a
                        href={actionModal.item.official_portal_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-700 hover:underline break-all"
                      >
                        {actionModal.item.official_portal_url} &rarr;
                      </a>
                    </div>
                  )}

                  {actionModal.item.short_summary && (
                    <div>
                      <span className="text-slate-500 font-bold block">संक्षिप्त उद्दिष्ट (Summary):</span>
                      <p className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800">
                        {actionModal.item.short_summary}
                      </p>
                    </div>
                  )}

                  {actionModal.item.benefits && (
                    <div>
                      <span className="text-slate-500 font-bold block">मिळणारे लाभ (Benefits):</span>
                      <p className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800">
                        {actionModal.item.benefits}
                      </p>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div>
                      <span className="text-slate-500 font-bold block">पात्रतेचे निकष (Eligibility):</span>
                      <div className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800 whitespace-pre-wrap">
                        {actionModal.item.eligibility_criteria || 'पात्रतेचे निकष लागू'}
                      </div>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">आवश्यक कागदपत्रे (Required Docs):</span>
                      <div className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800 whitespace-pre-wrap">
                        {actionModal.item.required_documents || 'कागदपत्रे लागू'}
                      </div>
                    </div>
                  </div>

                  {actionModal.item.application_process && (
                    <div>
                      <span className="text-slate-500 font-bold block">अर्ज प्रक्रिया (Application Process):</span>
                      <p className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800">
                        {actionModal.item.application_process}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Gallery Domain */}
              {actionModal.item.entity_type === 'gallery' && (
                <div className="space-y-2 text-xs">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <div>
                      <span className="text-slate-500 font-bold block">वर्गवारी (Category):</span>
                      <span className="font-semibold text-slate-800">
                        {actionModal.item.category_display || actionModal.item.category}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-bold block">छायाचित्रे संख्या:</span>
                      <span className="font-semibold text-slate-800">
                        {actionModal.item.items_count || 0} छायाचित्रे
                      </span>
                    </div>
                  </div>

                  {actionModal.item.description && (
                    <div>
                      <span className="text-slate-500 font-bold block">वर्णन (Description):</span>
                      <p className="bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-800">
                        {actionModal.item.description}
                      </p>
                    </div>
                  )}

                  {actionModal.item.sample_items && actionModal.item.sample_items.length > 0 && (
                    <div>
                      <span className="text-slate-500 font-bold block mb-1">नमुना छायाचित्रे (Sample Photos):</span>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {actionModal.item.sample_items.map((photo) => (
                          <div key={photo.id} className="relative rounded border border-slate-200 overflow-hidden bg-slate-100 aspect-video">
                            {photo.image_url ? (
                              <img
                                src={photo.image_url}
                                alt={photo.caption || 'Gallery photo'}
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <div className="flex items-center justify-center h-full text-slate-400 text-[10px]">
                                छायाचित्र
                              </div>
                            )}
                            {photo.caption && (
                              <div className="absolute inset-x-0 bottom-0 bg-slate-900/70 text-white text-[10px] px-1.5 py-0.5 truncate">
                                {photo.caption}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Inspect Mode Decision Transition Buttons */}
            {actionModal.type === 'inspect' && (
              <div className="space-y-3 pt-3 border-t border-slate-200">
                <span className="text-xs font-bold text-slate-800 block">प्रशासकीय कार्यवाही निवडा (Select Action):</span>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setActionModal({ item: actionModal.item, type: 'approve' })}
                    className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors inline-flex items-center gap-1"
                  >
                    <span>✓</span>
                    <span>{t.governance.btnApprove} (Approve)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setActionModal({ item: actionModal.item, type: 'reject' })}
                    className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors inline-flex items-center gap-1"
                  >
                    <span>✕</span>
                    <span>{t.governance.btnReject} (Reject)</span>
                  </button>
                  {currentUser?.role === 'super_admin' && (
                    <button
                      type="button"
                      onClick={() => setActionModal({ item: actionModal.item, type: 'publish' })}
                      className="px-3 py-1.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors inline-flex items-center gap-1"
                    >
                      <span>🚀</span>
                      <span>{t.governance.btnPublish} (Publish)</span>
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Approve Modal Form */}
            {actionModal.type === 'approve' && (
              <div className="space-y-2 pt-2 border-t border-slate-200">
                <label className="block text-xs font-semibold text-slate-800">
                  {t.governance.notesLabel}
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder={t.governance.notesPlaceholder}
                  rows={3}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:bg-white"
                />
                <p className="text-[11px] text-slate-500">
                  * मंजुरी दिल्यानंतर अपरिवर्तनीय ApprovalRecord तयार होतो. स्वतःचा मसुदा स्वतः मंजूर केल्यास प्रणाली तात्काळ नकार देईल (Anti-Self-Approval).
                </p>
              </div>
            )}

            {/* Reject Modal Form */}
            {actionModal.type === 'reject' && (
              <div className="space-y-2 pt-2 border-t border-slate-200">
                <label className="block text-xs font-semibold text-slate-800">
                  {t.governance.reasonLabel}
                </label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={t.governance.reasonPlaceholder}
                  rows={3}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-rose-500 focus:bg-white"
                />
                <p className="text-[11px] text-slate-500">
                  * नकाराचे कारण तपासणी लेजर (RejectionRecord) मध्ये कायमचे नोंदवले जाईल आणि संपादकाला दुरुस्तीसाठी दिसेल.
                </p>
              </div>
            )}

            {/* Publish Modal Form */}
            {actionModal.type === 'publish' && (
              <div className="space-y-2 pt-2 border-t border-slate-200">
                <label className="block text-xs font-semibold text-slate-800">
                  {t.governance.justificationLabel}
                </label>
                <textarea
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  placeholder={t.governance.justificationPlaceholder}
                  rows={3}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
                <p className="text-[11px] text-slate-500">
                  * प्रकाशनानंतर हा मजकूर नागरिक सार्वजनिक पोर्टलवर तात्काळ थेट दृश्यमान होईल आणि PublicationEvent नोंदवला जाईल.
                </p>
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex items-center justify-between pt-3 border-t border-slate-200">
              {actionModal.type !== 'inspect' ? (
                <button
                  type="button"
                  onClick={() => setActionModal({ item: actionModal.item, type: 'inspect' })}
                  className="text-xs text-slate-600 hover:text-slate-900 font-medium inline-flex items-center gap-1"
                >
                  <span>&larr;</span>
                  <span>तपशील पुनरावलोकनाकडे परत जा</span>
                </button>
              ) : (
                <div />
              )}

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setActionModal(null)}
                  disabled={actionLoading}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold transition-colors"
                >
                  {t.common.close}
                </button>

                {actionModal.type !== 'inspect' && (
                  <button
                    type="button"
                    onClick={handleConfirmAction}
                    disabled={actionLoading}
                    className={`px-4 py-2 rounded-lg text-xs font-semibold text-white transition-colors shadow-sm ${
                      actionModal.type === 'approve'
                        ? 'bg-emerald-600 hover:bg-emerald-700'
                        : actionModal.type === 'reject'
                        ? 'bg-rose-600 hover:bg-rose-700'
                        : 'bg-[#1e3a8a] hover:bg-blue-900'
                    }`}
                  >
                    {actionLoading
                      ? t.common.loading
                      : actionModal.type === 'approve'
                      ? t.governance.btnApprove
                      : actionModal.type === 'reject'
                      ? t.governance.btnReject
                      : t.governance.btnPublish}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Governance Dual-Control Architecture Summary */}
      <div className="border-t border-slate-200 pt-6">
        <Alert severity="info" title={t.governance.immutableAuditNoticeTitle}>
          <p>{t.governance.immutableAuditNoticeDesc}</p>
        </Alert>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
          {steps.map((st, i) => (
            <Card
              key={i}
              className="bg-white border-slate-200 text-slate-800 shadow-sm"
              title={st.title}
              badge={<Badge variant="primary">{st.actor}</Badge>}
            >
              <p className="text-xs text-slate-600 leading-relaxed">
                {st.desc}
              </p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
