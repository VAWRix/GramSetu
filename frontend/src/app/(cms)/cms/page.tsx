'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useLanguage } from '@/context/LanguageContext';
import { fetchCmsDashboard } from '@/lib/api';
import type { CmsDashboardResponse } from '@/lib/types';

export default function CmsDashboardPage() {
  const { t, language } = useLanguage();
  const [dashboard, setDashboard] = useState<CmsDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await fetchCmsDashboard();
        if (data) {
          setDashboard(data);
        }
      } catch (err) {
        console.error('Failed to load CMS dashboard', err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const domains = [
    {
      title: t.cms.contentPages,
      desc: language === 'mr' ? 'गावाची माहिती, इतिहास व प्रोफाइल पाने' : language === 'hi' ? 'गांव की जानकारी, इतिहास और प्रोफाइल पृष्ठ' : 'Village profile, history, and official pages',
      href: '/cms/content',
      stats: dashboard?.domains.pages,
    },
    {
      title: t.cms.noticesManagement,
      desc: language === 'mr' ? 'निविदा, तात्काळ सूचना व मुदत व्यवस्थापन' : language === 'hi' ? 'निविदा, तत्काल सूचना और समय सीमा प्रबंधन' : 'Tenders, urgent notices, and expiry management',
      href: '/cms/notices',
      stats: dashboard?.domains.notices,
    },
    {
      title: t.cms.documentsDisclosure,
      desc: language === 'mr' ? 'ग्रामसभा ठराव, इतिवृत्त व प्रकटीकरण मंजुरी' : language === 'hi' ? 'ग्रामसभा प्रस्ताव, कार्यवृत्त और प्रकटीकरण अनुमोदन' : 'Gram Sabha resolutions, minutes, and statutory disclosures',
      href: '/cms/documents',
      stats: dashboard?.domains.documents,
    },
    {
      title: t.cms.eventsMeetings,
      desc: language === 'mr' ? 'बैठक वेळापत्रक, विषयपत्रिका व वृत्तांत' : language === 'hi' ? 'बैठक कार्यक्रम, कार्यसूची और कार्यवाही विवरण' : 'Meeting schedules, agendas, and proceedings',
      href: '/cms/events',
      stats: dashboard?.domains.events,
    },
    {
      title: t.cms.schemesManagement,
      desc: language === 'mr' ? 'कल्याणकारी योजना, निकष व अधिकृत दुवे' : language === 'hi' ? 'कल्याणकारी योजनाएं, पात्रता और आधिकारिक लिंक' : 'Welfare schemes, eligibility criteria, and official links',
      href: '/cms/schemes',
      stats: dashboard?.domains.schemes,
    },
    {
      title: t.cms.galleryManagement,
      desc: language === 'mr' ? 'विकासकामे व उपक्रमांचे सुरक्षित फोटो' : language === 'hi' ? 'विकास कार्य और आयोजनों के सुरक्षित चित्र' : 'Development works and village event photo albums',
      href: '/cms/gallery',
      stats: dashboard?.domains.gallery,
    },
    {
      title: t.cms.profileManagement,
      desc: language === 'mr' ? 'ग्रामपंचायत माहिती, सरपंच व ग्रामसेवक पदाधिकारी व्यवस्थापन' : language === 'hi' ? 'ग्राम पंचायत जानकारी, सरपंच और ग्रामसेवक पदाधिकारी प्रबंधन' : 'Gram Panchayat profile, Sarpanch, and official contact details',
      href: '/cms/profile',
      stats: undefined,
    },
  ];

  const rbacRoles = [
    {
      role: 'SUPER_ADMIN (ग्रामसेवक / ग्रामविकास अधिकारी)',
      desc: language === 'mr'
        ? 'प्रशासकीय नियंत्रण, पुनरावलोकन, मंजुरी, थेट प्रकाशन, पंचायत प्रोफाईल व्यवस्थापन व लेखापरीक्षण'
        : language === 'hi'
        ? 'प्रशासनिक नियंत्रण, समीक्षा, अनुमोदन, प्रत्यक्ष प्रकाशन, पंचायत प्रोफ़ाइल प्रबंधन और लेखापरीक्षा'
        : 'Administrative executive, review, approvals, direct publishing, Panchayat profile management, and audit records',
    },
    {
      role: 'OPERATOR (संगणक चालक / डेटा एंट्री ऑपरेटर)',
      desc: language === 'mr'
        ? 'नवीन मसुदा तयार करणे, माहिती भरणे व मंजुरीसाठी सादर करणे (स्वतः मंजुरीचा अधिकार नाही)'
        : language === 'hi'
        ? 'नया मसौदा तैयार करना, प्रविष्टि करना और अनुमोदन हेतु प्रस्तुत करना (स्वयं अनुमोदन का अधिकार नहीं)'
        : 'Content drafting, editing, and submission for review (no self-approval rights)',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Title & Introduction */}
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
            {t.cms.dashboardTitle}
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            {t.cms.dashboardSubtitle}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/cms/governance"
            className="px-3 py-1.5 bg-blue-700 hover:bg-blue-800 text-white rounded text-xs font-semibold inline-flex items-center gap-1.5 transition-colors shadow-sm"
          >
            <span>{t.cms.reviewQueueButton}</span>
            {dashboard && dashboard.overview.pending_review_count > 0 && (
              <span className="px-1.5 py-0.5 bg-amber-400 text-slate-950 font-bold rounded-full text-[10px]">
                {dashboard.overview.pending_review_count}
              </span>
            )}
          </Link>
          <Link
            href="/cms/audit"
            className="px-3 py-1.5 bg-white hover:bg-slate-100 text-slate-700 rounded text-xs font-semibold border border-slate-300 transition-colors shadow-sm"
          >
            {t.cms.auditLogs}
          </Link>
        </div>
      </div>

      {/* Governance Workflow Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-600 uppercase font-bold tracking-wider">{t.cms.draftsCard}</span>
            <span className="text-base">📝</span>
          </div>
          <p className="text-2xl font-bold text-amber-600 mt-2">
            {loading ? '...' : dashboard?.overview.drafts_count ?? 0}
          </p>
          <p className="text-[11px] text-slate-500 mt-1">
            {language === 'mr' ? 'संपादकांकडील चालू कामे' : language === 'hi' ? 'संपादकों के चालू कार्य' : 'Active work by editors'}
          </p>
        </div>

        <Link href="/cms/governance?status=pending" className="block group">
          <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm group-hover:border-blue-600 group-hover:shadow-md transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs text-blue-700 uppercase font-bold tracking-wider">{t.cms.pendingReviewCard}</span>
              <span className="text-base">⏳</span>
            </div>
            <p className="text-2xl font-bold text-blue-700 mt-2">
              {loading ? '...' : dashboard?.overview.pending_review_count ?? 0}
            </p>
            <p className="text-[11px] text-slate-500 mt-1">
              {language === 'mr' ? 'ग्रामसेवक (मुख्य प्रशासक) पुनरावलोकन रांग →' : language === 'hi' ? 'ग्रामसेवक (मुख्य प्रशासक) समीक्षा कतार →' : 'Gram Sevak (Super Admin) review queue →'}
            </p>
          </div>
        </Link>

        <Link href="/cms/governance?status=approved" className="block group">
          <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm group-hover:border-purple-600 group-hover:shadow-md transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs text-purple-700 uppercase font-bold tracking-wider">
                {language === 'mr' ? 'मंजूर (प्रकाशन प्रतीक्षेत)' : language === 'hi' ? 'स्वीकृत (प्रकाशन प्रतीक्षारत)' : 'Approved (Ready to Publish)'}
              </span>
              <span className="text-base">⚖️</span>
            </div>
            <p className="text-2xl font-bold text-purple-700 mt-2">
              {loading ? '...' : (dashboard?.overview as any)?.approved_count ?? 0}
            </p>
            <p className="text-[11px] text-slate-500 mt-1">
              {language === 'mr' ? 'सुपर ॲडमिन प्रकाशन रांग →' : language === 'hi' ? 'सुपर एडमिन प्रकाशन कतार →' : 'Super Admin publish queue →'}
            </p>
          </div>
        </Link>

        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs text-emerald-700 uppercase font-bold tracking-wider">{t.cms.publishedCard}</span>
            <span className="text-base">✅</span>
          </div>
          <p className="text-2xl font-bold text-emerald-600 mt-2">
            {loading ? '...' : dashboard?.overview.published_count ?? 0}
          </p>
          <p className="text-[11px] text-slate-500 mt-1">
            {language === 'mr' ? 'सार्वजनिक पोर्टलवर थेट दृश्यमान' : language === 'hi' ? 'सार्वजनिक पोर्टल पर सीधे दृश्यमान' : 'Directly live on public portal'}
          </p>
        </div>
      </div>

      {/* Domain Management Workflows */}
      <section>
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-3">
          {t.cms.managementDomains}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {domains.map((dom) => (
            <Link key={dom.href} href={dom.href} className="group">
              <Card
                className="bg-white border-slate-200 text-slate-900 shadow-sm group-hover:border-blue-600 group-hover:shadow-md transition-all h-full"
                title={dom.title}
                badge={
                  dom.stats && dom.stats.pending > 0 ? (
                    <Badge variant="warning">
                      {dom.stats.pending} {language === 'mr' ? 'प्रलंबित' : language === 'hi' ? 'प्रलंबित' : 'Pending'}
                    </Badge>
                  ) : (
                    <Badge variant="success">
                      {dom.stats
                        ? `${dom.stats.published} ${language === 'mr' ? 'प्रसिद्ध' : language === 'hi' ? 'प्रकाशित' : 'Published'}`
                        : (language === 'mr' ? 'सक्रिय' : language === 'hi' ? 'सक्रिय' : 'Active')}
                    </Badge>
                  )
                }
              >
                <p className="text-xs text-slate-600">{dom.desc}</p>
                {dom.stats && (
                  <div className="mt-2.5 flex items-center gap-3 text-[11px] text-slate-500 border-t border-slate-100 pt-2">
                    <span>
                      {language === 'mr' ? 'मसुदा' : language === 'hi' ? 'मसौदा' : 'Draft'}: <strong className="text-slate-700">{dom.stats.drafts}</strong>
                    </span>
                    <span>•</span>
                    <span>
                      {language === 'mr' ? 'प्रलंबित' : language === 'hi' ? 'प्रलंबित' : 'Pending'}: <strong className="text-blue-700">{dom.stats.pending}</strong>
                    </span>
                    <span>•</span>
                    <span>
                      {language === 'mr' ? 'प्रसिद्ध' : language === 'hi' ? 'प्रकाशित' : 'Published'}: <strong className="text-emerald-700">{dom.stats.published}</strong>
                    </span>
                  </div>
                )}
                <div className="mt-3 text-xs text-blue-700 group-hover:text-blue-900 font-bold inline-flex items-center gap-1">
                  {language === 'mr' ? 'व्यवस्थापन करा →' : language === 'hi' ? 'प्रबंधन करें →' : 'Manage →'}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      {/* Recent Publication & Governance Events */}
      {dashboard && dashboard.recent_events.length > 0 && (
        <section className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm text-slate-900">
          <div className="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
              {language === 'mr' ? 'अलीकडील शासन व प्रकाशन घटना' : language === 'hi' ? 'हालिया शासन और प्रकाशन घटनाएं' : 'Recent Governance & Publication Events'}
            </h2>
            <Link href="/cms/audit" className="text-xs text-blue-700 font-semibold hover:underline">
              {language === 'mr' ? 'सर्व नोंदी →' : language === 'hi' ? 'सभी प्रविष्टियां →' : 'All records →'}
            </Link>
          </div>
          <div className="space-y-2 text-xs">
            {dashboard.recent_events.map((ev) => (
              <div
                key={ev.id}
                className="p-3 bg-slate-50 rounded border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
              >
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-blue-100 text-blue-800 border border-blue-300 rounded font-mono text-[10px] font-bold uppercase">
                    {ev.event_type_code}
                  </span>
                  <span className="text-slate-800 font-semibold">{ev.event_type}</span>
                  <span className="text-slate-400">•</span>
                  <span className="text-slate-600 font-mono text-[11px]">{ev.target_type}</span>
                </div>
                <div className="flex items-center gap-3 text-slate-600 text-[11px]">
                  <span>
                    {language === 'mr' ? 'कर्ता' : language === 'hi' ? 'कर्ता' : 'Actor'}: <strong className="text-slate-800">{ev.actor_name}</strong>
                  </span>
                  <span>•</span>
                  <span>{new Date(ev.created_at).toLocaleString(language === 'mr' ? 'mr-IN' : language === 'hi' ? 'hi-IN' : 'en-IN')}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Role-Based Access Control Architecture Overview */}
      <section className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm text-slate-900">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-2">
          {t.cms.rbacSummaryTitle}
        </h2>
        <p className="text-xs text-slate-600 mb-4">
          {language === 'mr' ? 'ग्रामसेतू प्रणालीमध्ये कामाचे काटेकोर विभाजन (Separation of Duties) लागू आहे:' : language === 'hi' ? 'ग्रामसेतु प्रणाली में कर्तव्यों का सख्त पृथक्करण लागू है:' : 'Strict separation of duties is enforced across the GramSetu backoffice:'}
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          {rbacRoles.map((r) => (
            <div key={r.role} className="p-3 bg-slate-50 rounded border border-slate-200">
              <div className="font-mono font-bold text-blue-900 mb-1">{r.role}</div>
              <div className="text-slate-700">{r.desc}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
