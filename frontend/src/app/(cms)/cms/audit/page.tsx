'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { useLanguage } from '@/context/LanguageContext';
import { fetchCmsAuditLogs } from '@/lib/api';
import type { CmsAuditLogItem } from '@/lib/types';

export default function CmsAuditPage() {
  const { t } = useLanguage();
  const [logs, setLogs] = useState<CmsAuditLogItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Filter states
  const [filterType, setFilterType] = useState('all');
  const [filterContentType, setFilterContentType] = useState('all');
  const [filterActor, setFilterActor] = useState('');
  const [filterStartDate, setFilterStartDate] = useState('');
  const [filterEndDate, setFilterEndDate] = useState('');

  async function loadLogs() {
    setLoading(true);
    try {
      const params: any = {
        limit: 100,
      };
      if (filterType !== 'all') {
        params.type = filterType;
      }
      if (filterContentType !== 'all') {
        params.content_type = filterContentType;
      }
      if (filterActor.trim()) {
        params.actor = filterActor.trim();
      }
      if (filterStartDate) {
        params.start_date = filterStartDate;
      }
      if (filterEndDate) {
        params.end_date = filterEndDate;
      }

      const res = await fetchCmsAuditLogs(params);
      if (res) {
        setLogs(res.results);
      }
    } catch (err) {
      console.error('Failed to load audit logs', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLogs();
  }, [filterType, filterContentType, filterStartDate, filterEndDate]);

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    loadLogs();
  }

  function handleResetFilters() {
    setFilterType('all');
    setFilterContentType('all');
    setFilterActor('');
    setFilterStartDate('');
    setFilterEndDate('');
  }

  const filterTabs = [
    { id: 'all', label: t.cmsAudit.allLogs },
    { id: 'approvals', label: t.cmsAudit.approvals },
    { id: 'rejections', label: t.cmsAudit.rejections },
    { id: 'publications', label: t.cmsAudit.publications },
    { id: 'urgent_notices', label: t.cmsAudit.urgentNotices },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white p-5 rounded-lg border shadow-sm">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span aria-hidden="true">📜</span>
            <span>{t.cmsAudit.pageTitle}</span>
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            सामग्री-जागरूक अपरिवर्तनीय ऑडिट ट्रेल (Content-Aware Immutable Audit Trail & Governance Ledger)
          </p>
        </div>
        <button
          onClick={loadLogs}
          disabled={loading}
          className="px-3.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold border border-slate-300 self-start sm:self-auto transition-colors shadow-sm inline-flex items-center gap-1.5"
        >
          <span aria-hidden="true">🔄</span>
          <span>{loading ? t.common.loading : t.cmsAudit.refresh}</span>
        </button>
      </div>

      <Alert severity="info" title="वैधानिक व अपरिवर्तनीय नोंदवही (Statutory Immutable Ledger)">
        <p>
          ग्रामसेतू प्रशासकीय कार्यप्रणालीतील सर्व मंजुऱ्या (Approvals), नकारादेश (Rejections), प्रसिद्धी (Publications), तात्काळ जाहीरनामे (Urgent Disclosures) व मागे घेणे (Withdrawals) ची नोंद येथे सुरक्षित व फेरफार-प्रतिबंधित पद्धतीने साठवली जाते.
        </p>
      </Alert>

      {/* Filter and Query Controls */}
      <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-3">
        {/* Record Type Tabs */}
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-3">
          {filterTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilterType(tab.id)}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                filterType === tab.id
                  ? 'bg-[#1e3a8a] text-white shadow-sm ring-2 ring-blue-700'
                  : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content-Aware Filter Bar */}
        <form onSubmit={handleSearchSubmit} className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs pt-1">
          <div>
            <label className="block text-slate-600 font-semibold mb-1">
              सामग्री प्रकार (Content Type):
            </label>
            <select
              value={filterContentType}
              onChange={(e) => setFilterContentType(e.target.value)}
              className="w-full bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
            >
              <option value="all">सर्व सामग्री प्रकार (All Types)</option>
              <option value="page">माहिती पृष्ठ (Pages)</option>
              <option value="notice">सूचना व जाहीरनामे (Notices)</option>
              <option value="document">दस्तऐवज (Documents)</option>
              <option value="event">बैठक व कार्यक्रम (Events)</option>
              <option value="scheme">कल्याणकारी योजना (Schemes)</option>
              <option value="gallery">छायाचित्र दालन (Gallery)</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-600 font-semibold mb-1">
              अधिकारी / ऑपरेटर (Actor):
            </label>
            <input
              type="text"
              value={filterActor}
              onChange={(e) => setFilterActor(e.target.value)}
              placeholder="उदा. admin, operator..."
              className="w-full bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
            />
          </div>

          <div>
            <label className="block text-slate-600 font-semibold mb-1">
              प्रारंभ तारीख (Start Date):
            </label>
            <input
              type="date"
              value={filterStartDate}
              onChange={(e) => setFilterStartDate(e.target.value)}
              className="w-full bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
            />
          </div>

          <div className="flex items-end gap-2">
            <div className="flex-1">
              <label className="block text-slate-600 font-semibold mb-1">
                अंतिम तारीख (End Date):
              </label>
              <input
                type="date"
                value={filterEndDate}
                onChange={(e) => setFilterEndDate(e.target.value)}
                className="w-full bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
              />
            </div>
            <button
              type="submit"
              className="px-3 py-1.5 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
            >
              शोधा
            </button>
            <button
              type="button"
              onClick={handleResetFilters}
              className="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium border border-slate-300 transition-colors"
              title="Reset Filters"
            >
              रीसेट
            </button>
          </div>
        </form>
      </div>

      {/* Audit Log Ledger Table */}
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
        <div className="p-3.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-xs font-bold text-slate-800">
          <span>नोंदवही सूची (Audit Log Ledger)</span>
          <span className="text-slate-500 font-mono text-[11px] bg-white px-2 py-0.5 rounded border border-slate-200">
            एकूण नोंदी: {logs.length}
          </span>
        </div>

        {loading ? (
          <div className="p-12 text-center text-slate-500 text-xs">
            {t.common.loading}
          </div>
        ) : logs.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-xs">
            {t.cmsAudit.emptyLogs}
          </div>
        ) : (
          <div className="divide-y divide-slate-100 text-xs">
            {logs.map((log) => {
              const displayTitle = log.content_title || log.notice_title || log.target_type || 'अनाम नोंद (Unnamed)';
              return (
                <div key={`${log.record_type}-${log.id}`} className="p-4 hover:bg-slate-50/70 transition-colors space-y-2.5">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                    <div className="space-y-1">
                      {/* Action & Content Category Badges */}
                      <div className="flex flex-wrap items-center gap-1.5">
                        {log.record_type === 'approval' && (
                          <span className="px-2 py-0.5 bg-emerald-50 text-emerald-800 border border-emerald-300 rounded font-mono text-[10px] font-bold uppercase">
                            ✓ {t.cmsAudit.approvals} (Approval)
                          </span>
                        )}
                        {log.record_type === 'rejection' && (
                          <span className="px-2 py-0.5 bg-rose-50 text-rose-800 border border-rose-300 rounded font-mono text-[10px] font-bold uppercase">
                            ✕ {t.cmsAudit.rejections} (Rejection)
                          </span>
                        )}
                        {log.record_type === 'publication' && (
                          <span className="px-2 py-0.5 bg-blue-50 text-blue-800 border border-blue-300 rounded font-mono text-[10px] font-bold uppercase">
                            🚀 {log.event_type_display || t.cmsAudit.publications}
                          </span>
                        )}
                        {log.record_type === 'urgent_notice_log' && (
                          <span className="px-2 py-0.5 bg-amber-50 text-amber-800 border border-amber-300 rounded font-mono text-[10px] font-bold uppercase">
                            ⚡ {t.cmsAudit.urgentNotices}
                          </span>
                        )}

                        {/* Content Type Badge */}
                        <span className="px-2 py-0.5 bg-indigo-50 text-indigo-800 border border-indigo-200 rounded text-[10px] font-semibold">
                          {log.content_type_display || log.target_type || 'सामग्री'}
                        </span>

                        {log.is_self_approval && (
                          <span className="px-2 py-0.5 bg-purple-50 text-purple-800 border border-purple-200 rounded text-[10px] font-semibold">
                            थेट प्रसिद्धी (Direct Publication)
                          </span>
                        )}
                      </div>

                      {/* Content Title Snapshot */}
                      <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-1.5 pt-0.5">
                        <span>{displayTitle}</span>
                      </h3>
                    </div>

                    <div className="flex flex-col sm:items-end gap-1 text-[11px] text-slate-500 shrink-0">
                      <span className="font-mono bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                        {new Date(log.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST
                      </span>
                      {log.content_link && (
                        <Link
                          href={log.content_link}
                          className="text-blue-700 hover:text-blue-900 font-semibold underline text-[11px] inline-flex items-center gap-0.5"
                        >
                          <span>सामग्रीकडे जा (View Record)</span>
                          <span aria-hidden="true">&rarr;</span>
                        </Link>
                      )}
                    </div>
                  </div>

                  {/* Actor, Role, Revision & Identifiers Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 text-slate-700 bg-slate-50/60 p-2.5 rounded-lg border border-slate-100 text-[11px]">
                    <div>
                      <span className="text-slate-500 font-medium">{t.cmsAudit.actor}: </span>
                      <strong className="text-slate-900">
                        {log.actor_name || log.operator_name || 'System'}
                      </strong>
                      {log.actor_role_display && (
                        <span className="text-slate-500 block text-[10px]">
                          ({log.actor_role_display})
                        </span>
                      )}
                    </div>

                    <div>
                      <span className="text-slate-500 font-medium">सामग्री ओळख (Target ID): </span>
                      <span className="font-mono text-slate-700 text-[10px] block truncate" title={log.target_id || log.notice_id}>
                        {log.target_id || log.notice_id || 'उपलब्ध नाही'}
                      </span>
                    </div>

                    <div>
                      {log.revision_number !== undefined && (
                        <div>
                          <span className="text-slate-500 font-medium">आवृत्ती (Revision): </span>
                          <span className="font-mono text-blue-800 font-bold">r{log.revision_number}</span>
                        </div>
                      )}
                      {log.revision_hash && (
                        <div className="font-mono text-[10px] text-slate-500 truncate" title={log.revision_hash}>
                          SHA: {log.revision_hash.slice(0, 16)}...
                        </div>
                      )}
                      {log.authorization_id && (
                        <div className="font-mono text-[10px] text-amber-800">
                          Auth: {log.authorization_id}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Justification or Reason or Notes */}
                  {(log.reason || log.justification || log.notes) && (
                    <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-[11px] text-slate-700 space-y-1">
                      {log.reason && (
                        <p>
                          <strong className="text-rose-700">{t.cmsAudit.notesOrReason} (Rejection Reason):</strong> {log.reason}
                        </p>
                      )}
                      {log.justification && (
                        <p>
                          <strong className="text-blue-800">समर्थन / औचित्य (Justification):</strong> {log.justification}
                        </p>
                      )}
                      {log.notes && (
                        <p>
                          <strong className="text-emerald-700">टीप (Notes):</strong> {log.notes}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Statutory Guidance Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-slate-200">
        <Card
          className="bg-white border-slate-200 text-slate-800 shadow-sm"
          title={t.cmsAudit.approvals}
          badge={<Badge variant="success">Immutable</Badge>}
        >
          <p className="text-xs text-slate-600">
            मुख्य प्रशासक किंवा सक्षम प्राधिकाऱ्यांनी दिलेल्या सर्व मंजुरी नोंदी व डिजिटल स्वाक्षरी संदर्भ.
          </p>
        </Card>

        <Card
          className="bg-white border-slate-200 text-slate-800 shadow-sm"
          title={t.cmsAudit.publications}
          badge={<Badge variant="primary">Immutable</Badge>}
        >
          <p className="text-xs text-slate-600">
            सार्वजनिक संकेतस्थळावर थेट प्रसिद्ध किंवा अद्यतनित केलेल्या सर्व सामग्री आवृत्त्यांचा अखंड इतिहास.
          </p>
        </Card>

        <Card
          className="bg-white border-slate-200 text-slate-800 shadow-sm"
          title={t.cmsAudit.urgentNotices}
          badge={<Badge variant="warning">Immutable</Badge>}
        >
          <p className="text-xs text-slate-600">
            आपत्कालीन किंवा तात्काळ जाहीरनाम्यांचे वैधानिक अधिकार पत्र व कार्योत्तर मंजुरी स्थिती (Ratification).
          </p>
        </Card>
      </div>
    </div>
  );
}
