'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/context/LanguageContext';
import { fetchSiteConfig } from '@/lib/api';
import { PanchayatProfile } from '@/lib/types';

export function PublicFooter() {
  const { t, language } = useLanguage();
  const [profile, setProfile] = useState<PanchayatProfile | null>(null);
  const currentYear = '2026';
  const lastUpdated = '2026-10-18';

  useEffect(() => {
    let isMounted = true;
    fetchSiteConfig(language).then((data) => {
      if (isMounted && data?.profile) {
        setProfile(data.profile);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [language]);

  return (
    <footer
      role="contentinfo"
      aria-label="Portal Footer"
      className="bg-[var(--brand-navy-dark)] text-white border-t-4 border-[var(--brand-saffron)] mt-auto"
    >
      {/* Top Footer: Contact, Office, Key Links */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 sm:py-10 grid grid-cols-1 md:grid-cols-4 gap-8 text-xs">
        {/* Column 1: Office Address & Contacts */}
        <div>
          <h3 className="font-bold text-sm text-[var(--brand-saffron-light)] mb-3 pb-1 border-b border-blue-800">
            {t.footer.panchayatAddress}
          </h3>
          <p className="text-slate-300 leading-relaxed mb-2">
            {profile?.panchayat_name || t.header.panchayatOffice}, {profile?.office_address || '[पत्ता प्रलंबित]'}<br />
            {t.header.talukaTitle} {profile?.taluka_name || '[प्रलंबित]'}, {t.header.districtTitle} {profile?.district_name || '[प्रलंबित]'}, महाराष्ट्र
          </p>
          <div className="space-y-1 text-slate-300">
            <p><span className="text-slate-400 font-semibold">{t.footer.phone}:</span> {profile?.contact_phone || '[प्रलंबित]'}</p>
            <p><span className="text-slate-400 font-semibold">{t.footer.email}:</span> {profile?.contact_email || '[अधिकृत ई-मेल प्रलंबित]'}</p>
            <p className="text-[11px] text-slate-400 mt-2">{t.footer.officeHours}</p>
          </div>
        </div>

        {/* Column 2: Key Panchayat Officials */}
        <div>
          <h3 className="font-bold text-sm text-[var(--brand-saffron-light)] mb-3 pb-1 border-b border-blue-800">
            {t.footer.officialsTitle}
          </h3>
          <div className="space-y-3 text-slate-300">
            <div className="bg-blue-950/60 p-2.5 rounded border border-blue-800/80">
              <span className="text-amber-400 font-semibold text-[11px] block">{t.footer.sarpanch}</span>
              <span className="text-slate-200 font-medium">{profile?.sarpanch_name || (language === 'en' ? '[Name Pending Verification]' : '[सरपंच नाव प्रलंबित]')}</span>
            </div>
            <div className="bg-blue-950/60 p-2.5 rounded border border-blue-800/80">
              <span className="text-emerald-400 font-semibold text-[11px] block">{t.footer.gramSevak}</span>
              <span className="text-slate-200 font-medium">{profile?.gram_sevak_name || (language === 'en' ? 'ASHOK GANPAT WALE' : 'अशोक गणपत वाले')}</span>
            </div>
          </div>
        </div>

        {/* Column 3: Important External Links */}
        <div>
          <h3 className="font-bold text-sm text-[var(--brand-saffron-light)] mb-3 pb-1 border-b border-blue-800">
            {t.footer.importantLinks}
          </h3>
          <ul className="space-y-2 text-slate-300">
            <li>
              <a
                href="https://aaplesarkar.mahaonline.gov.in"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-amber-300 underline focus-visible:outline-white inline-flex items-center gap-1"
              >
                <span>🔗</span> {t.footer.aapleSarkar}
              </a>
            </li>
            <li>
              <a
                href="https://www.maharashtra.gov.in"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-amber-300 underline focus-visible:outline-white inline-flex items-center gap-1"
              >
                <span>🔗</span> {t.footer.maharashtraGov}
              </a>
            </li>
            <li>
              <a
                href="https://www.digitalindia.gov.in"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-amber-300 underline focus-visible:outline-white inline-flex items-center gap-1"
              >
                <span>🔗</span> {t.footer.digitalIndia}
              </a>
            </li>
            <li>
              <a
                href="https://panchayat.gov.in"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-amber-300 underline focus-visible:outline-white inline-flex items-center gap-1"
              >
                <span>🔗</span> {t.footer.nationalPanchayat}
              </a>
            </li>
          </ul>
        </div>

        {/* Column 4: Compliance & Digital India Attribution */}
        <div>
          <h3 className="font-bold text-sm text-[var(--brand-saffron-light)] mb-3 pb-1 border-b border-blue-800">
            {t.footer.complianceNotice}
          </h3>
          <p className="text-slate-300 leading-relaxed mb-3">
            {t.footer.accessibilityStatement}
          </p>
          <div className="bg-blue-950/70 p-3 rounded border border-blue-800 text-[11px] text-slate-300 space-y-1">
            <p>
              <strong className="text-white">GIGW Compliant:</strong> Level AA
            </p>
            <p>
              <strong className="text-white">WCAG Target:</strong> 2.2 AA
            </p>
            <p>
              <strong className="text-white">{t.footer.lastUpdated}:</strong> {lastUpdated}
            </p>
          </div>
        </div>
      </div>

      {/* Middle Footer: Policies & Standards Navigation */}
      <div className="border-t border-blue-900 bg-blue-950/80 py-3 px-4">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-slate-300">
          <Link href="/about" className="hover:text-white underline focus-visible:outline-white">
            {t.footer.termsOfUse}
          </Link>
          <span className="text-blue-700">|</span>
          <Link href="/about" className="hover:text-white underline focus-visible:outline-white">
            {t.footer.privacyPolicy}
          </Link>
          <span className="text-blue-700">|</span>
          <Link href="/about" className="hover:text-white underline focus-visible:outline-white">
            {t.footer.copyrightPolicy}
          </Link>
          <span className="text-blue-700">|</span>
          <Link href="/about" className="hover:text-white underline focus-visible:outline-white">
            {t.footer.hyperlinkPolicy}
          </Link>
        </div>
      </div>

      {/* Bottom Footer: Copyright and Disclaimer */}
      <div className="border-t border-blue-950 bg-[#070d1e] py-4 px-4 text-center text-xs text-slate-400">
        <div className="max-w-7xl mx-auto space-y-1">
          <p>
            &copy; {currentYear} {t.header.panchayatOffice}. {t.footer.copyrightText}
          </p>
          <p className="text-[11px] text-slate-400">
            {t.footer.portalDisclaimer}
          </p>
        </div>
      </div>
    </footer>
  );
}
