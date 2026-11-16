'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useLanguage } from '@/context/LanguageContext';
import { fetchSchemeDetail, getApiBaseUrl } from '@/lib/api';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import type { PublicSchemeDetail } from '@/lib/types';

function SchemeDetailContent() {
  const { slug } = useParams() as { slug: string };
  const { t, language } = useLanguage();
  const [scheme, setScheme] = useState<PublicSchemeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    if (!slug) return;

    setLoading(true);
    setError(null);

    fetchSchemeDetail(slug, language)
      .then((data) => {
        if (isMounted) {
          if (data) {
            setScheme(data);
          } else {
            setError(
              language === 'mr'
                ? 'ही योजना उपलब्ध नाही अथवा सार्वजनिकरित्या प्रसिद्ध केलेली नाही.'
                : language === 'hi'
                ? 'यह योजना उपलब्ध नहीं है अथवा सार्वजनिक रूप से प्रकाशित नहीं की गई है।'
                : 'This welfare scheme is not available or has not been publicly disclosed.'
            );
          }
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(
            language === 'mr'
              ? 'योजनेची माहिती लोड करताना त्रुटी आढळली.'
              : 'Failed to load welfare scheme details.'
          );
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [slug, language]);

  if (loading) {
    return (
      <div className="py-20 text-center text-xs text-slate-500">
        <p>{t.common.loading}</p>
      </div>
    );
  }

  if (error || !scheme) {
    return (
      <div className="py-12 max-w-2xl mx-auto space-y-4">
        <Alert severity="warning" title={t.common.error}>
          <p>{error || 'Scheme not found.'}</p>
        </Alert>
        <Link
          href="/schemes"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#1e3a8a] hover:underline"
        >
          &larr; {language === 'mr' ? 'सर्व योजनांकडे परत जा' : 'Back to all schemes'}
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* GIGW Breadcrumb Navigation */}
      <nav aria-label="Breadcrumb" className="text-xs text-slate-500 flex items-center gap-2">
        <Link href="/" className="hover:text-slate-900 transition-colors">
          {language === 'mr' ? 'मुख्य पृष्ठ' : language === 'hi' ? 'मुख्य पृष्ठ' : 'Home'}
        </Link>
        <span aria-hidden="true">/</span>
        <Link href="/schemes" className="hover:text-slate-900 transition-colors">
          {t.schemes.title}
        </Link>
        <span aria-hidden="true">/</span>
        <span className="text-slate-800 font-semibold truncate max-w-xs" aria-current="page">
          {scheme.scheme_name || scheme.title}
        </span>
      </nav>

      {/* Header card with print & official actions */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 border-b border-slate-100 pb-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="primary">{scheme.scheme_level_display}</Badge>
              <span className="px-2.5 py-0.5 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded text-xs font-medium">
                {scheme.target_beneficiary_display}
              </span>
              <span className="px-2 py-0.5 bg-slate-100 text-slate-700 font-mono text-[11px] rounded">
                /{scheme.slug}
              </span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
              {scheme.scheme_name || scheme.title}
            </h1>
          </div>

          <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
            <button
              type="button"
              onClick={() => window.print()}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded-lg text-xs font-medium transition-colors inline-flex items-center gap-1.5 shadow-sm"
              title="Print official scheme details"
            >
              <span aria-hidden="true">🖨️</span>
              <span>{language === 'mr' ? 'प्रिन्ट करा' : 'Print'}</span>
            </button>
          </div>
        </div>

        {/* Short Summary / Overview */}
        {scheme.short_summary && (
          <div className="bg-blue-50/60 p-4 rounded-lg border border-blue-100 text-slate-800 text-sm leading-relaxed">
            <strong className="block text-xs font-bold uppercase tracking-wider text-[#1e3a8a] mb-1">
              {language === 'mr' ? 'संक्षिप्त माहिती / उद्देश' : 'Overview & Objective'}
            </strong>
            <p>{scheme.short_summary}</p>
          </div>
        )}

        {/* Department & Contact Information Grid */}
        {(scheme.department || scheme.contact_details || scheme.updated_at) && (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 bg-slate-50 p-4 rounded-lg border border-slate-200 text-xs">
            {scheme.department && (
              <div>
                <span className="text-slate-500 font-semibold block text-[11px] uppercase tracking-wider">
                  {language === 'mr' ? 'संबंधित शासकीय विभाग' : language === 'hi' ? 'संबंधित विभाग' : 'Concerned Department'}
                </span>
                <span className="font-bold text-slate-800 text-xs block mt-0.5">
                  {scheme.department}
                </span>
              </div>
            )}
            {scheme.contact_details && (
              <div>
                <span className="text-slate-500 font-semibold block text-[11px] uppercase tracking-wider">
                  {language === 'mr' ? 'मार्गदर्शन व हेल्पलाईन' : language === 'hi' ? 'मार्गदर्शन व हेल्पलाइन' : 'Helpline & Contact'}
                </span>
                <span className="font-bold text-slate-800 text-xs block mt-0.5">
                  {scheme.contact_details}
                </span>
              </div>
            )}
            {scheme.updated_at && (
              <div>
                <span className="text-slate-500 font-semibold block text-[11px] uppercase tracking-wider">
                  {language === 'mr' ? 'शेवटचे अद्यतन' : language === 'hi' ? 'अंतिम अद्यतन' : 'Last Updated'}
                </span>
                <span className="font-mono text-slate-700 text-xs block mt-0.5">
                  {new Date(scheme.updated_at).toLocaleDateString(
                    language === 'mr' ? 'mr-IN' : language === 'hi' ? 'hi-IN' : 'en-IN',
                    { day: '2-digit', month: 'short', year: 'numeric' }
                  )}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Detailed Sections Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-2">
          {/* Eligibility Criteria */}
          {scheme.eligibility_criteria && (
            <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 space-y-2">
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5 text-blue-900">
                <span aria-hidden="true">✅</span>
                <span>{language === 'mr' ? 'पात्रतेचे निकष (Eligibility Criteria)' : 'Eligibility Criteria'}</span>
              </h2>
              <div className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed font-sans">
                {scheme.eligibility_criteria}
              </div>
            </div>
          )}

          {/* Benefits */}
          {scheme.benefits && (
            <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 space-y-2">
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5 text-emerald-900">
                <span aria-hidden="true">🎁</span>
                <span>{language === 'mr' ? 'मिळणारे लाभ (Benefits)' : 'Benefits'}</span>
              </h2>
              <div className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed font-sans">
                {scheme.benefits}
              </div>
            </div>
          )}

          {/* Required Documents */}
          {scheme.required_documents && (
            <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 space-y-2">
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5 text-amber-900">
                <span aria-hidden="true">📑</span>
                <span>{language === 'mr' ? 'आवश्यक कागदपत्रे (Required Documents)' : 'Required Documents'}</span>
              </h2>
              <div className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed font-sans">
                {scheme.required_documents}
              </div>
            </div>
          )}

          {/* Application Process */}
          {scheme.application_process && (
            <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 space-y-2">
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5 text-indigo-900">
                <span aria-hidden="true">📝</span>
                <span>{language === 'mr' ? 'अर्ज करण्याची पद्धत (Application Process)' : 'Application Process'}</span>
              </h2>
              <div className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed font-sans">
                {scheme.application_process}
              </div>
            </div>
          )}
        </div>

        {/* Official Portal Link & Supporting Documents */}
        <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {scheme.official_portal_url ? (
            <a
              href={scheme.official_portal_url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 shadow-sm transition-colors self-start sm:self-auto"
            >
              <span>{language === 'mr' ? 'अधिकृत शासकीय पोर्टलला भेट द्या' : 'Visit Official Government Portal'}</span>
              <span aria-hidden="true">&nearr;</span>
            </a>
          ) : (
            <span className="text-xs text-slate-500">
              {language === 'mr' ? 'स्थानिक ग्रामपंचायत कार्यालयात संपर्क साधा.' : 'Contact local Gram Panchayat office.'}
            </span>
          )}

          <Link
            href="/schemes"
            className="text-xs text-slate-600 hover:text-slate-900 font-medium inline-flex items-center gap-1 self-start sm:self-auto"
          >
            &larr; {language === 'mr' ? 'सर्व योजनांकडे परत' : 'Back to schemes'}
          </Link>
        </div>

        {/* Supporting Documents (if any) */}
        {scheme.supporting_documents && scheme.supporting_documents.length > 0 && (
          <div className="pt-4 border-t border-slate-100 space-y-2">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              {language === 'mr' ? 'संलग्न अधिकृत शासन निर्णय व मार्गदर्शक तत्त्वे' : 'Supporting Government Resolutions & Guidelines'}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {scheme.supporting_documents.map((doc) => (
                <a
                  key={doc.id}
                  href={`${getApiBaseUrl()}${doc.download_url}`}
                  target="_blank"
                  rel="noreferrer"
                  className="p-2.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg text-xs flex items-center justify-between transition-colors"
                >
                  <div className="truncate pr-2">
                    <span className="font-semibold text-slate-900 block truncate">{doc.title}</span>
                    <span className="text-[10px] text-slate-500 font-mono">{doc.reference_number || doc.category_display}</span>
                  </div>
                  <span className="text-blue-700 shrink-0 font-medium text-[11px]">डाउनलोड 📥</span>
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Citizen Notice */}
        {scheme.portal_notice && (
          <div className="text-[11px] text-slate-500 bg-slate-50 p-3 rounded-lg border border-slate-200">
            <strong>{language === 'mr' ? 'महत्त्वाची सूचना:' : 'Notice:'}</strong> {scheme.portal_notice}
          </div>
        )}
      </div>
    </div>
  );
}

export default function PublicSchemeDetailPage() {
  return (
    <React.Suspense
      fallback={
        <div className="max-w-4xl mx-auto px-4 py-12 text-center text-slate-500 text-xs">
          योजनेची माहिती लोड होत आहे...
        </div>
      }
    >
      <SchemeDetailContent />
    </React.Suspense>
  );
}
