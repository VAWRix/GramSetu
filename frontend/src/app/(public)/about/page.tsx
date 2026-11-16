'use client';

import React, { useState, useEffect } from 'react';
import { useLanguage } from '@/context/LanguageContext';
import { Card } from '@/components/ui/Card';
import { PlaceholderNotice } from '@/components/ui/PlaceholderNotice';
import { VillageKnowledgeArticle } from '@/components/knowledge/VillageKnowledgeArticle';
import { fetchSiteConfig, fetchPublicPages } from '@/lib/api';
import { PanchayatProfile, PublicPageItem } from '@/lib/types';

export default function AboutPage() {
  const { t, language } = useLanguage();
  const [profile, setProfile] = useState<PanchayatProfile | null>(null);
  const [pages, setPages] = useState<PublicPageItem[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    Promise.all([
      fetchSiteConfig(language),
      fetchPublicPages(language),
    ]).then(([configData, pagesData]) => {
      if (isMounted) {
        if (configData?.profile) {
          setProfile(configData.profile);
        }
        if (pagesData && Array.isArray(pagesData.results)) {
          setPages(pagesData.results);
          if (pagesData.results.length > 0) {
            setSelectedPageId(pagesData.results[0].id);
          }
        } else {
          setPages([]);
        }
        setLoading(false);
      }
    }).catch(() => {
      if (isMounted) {
        setLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [language]);

  const activePage = pages.find((p) => p.id === selectedPageId) || pages[0] || null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <header className="border-b border-[var(--border-muted)] pb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            {t.about.title}
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t.about.subtitle}
          </p>
        </div>

        {/* Page selector pills if multiple pages exist */}
        {pages.length > 1 && (
          <div className="flex flex-wrap items-center gap-1.5 self-start sm:self-auto text-xs">
            {pages.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setSelectedPageId(p.id)}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                  (activePage?.id === p.id)
                    ? 'bg-[var(--brand-navy)] text-white shadow-xs'
                    : 'bg-[var(--bg-muted)] text-[var(--text-secondary)] hover:bg-slate-200 border border-[var(--border-muted)]'
                }`}
              >
                {p.title}
              </button>
            ))}
          </div>
        )}
      </header>

      {loading ? (
        <div className="py-12 text-center text-xs text-[var(--text-muted)]">
          {t.common.loading}
        </div>
      ) : activePage ? (
        <div className="space-y-6">
          {/* Statutory Administrative Header Bar */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title={t.about.geoCardTitle}>
              <div className="space-y-2 text-xs text-[var(--text-secondary)]">
                <p><strong>{t.about.panchayatName}:</strong> {profile?.panchayat_name || (language === 'en' ? 'Gram Panchayat Narayangaon' : language === 'hi' ? 'ग्राम पंचायत कार्यालय, नारायणगांव' : 'ग्रामपंचायत कार्यालय, नारायणगाव')}</p>
                <p><strong>{t.about.district}:</strong> {profile?.district_name || (language === 'en' ? 'Chhatrapati Sambhajinagar' : language === 'hi' ? 'छत्रपति संभाजीनगर' : 'छत्रपती संभाजीनगर')}</p>
                <p><strong>{t.about.taluka}:</strong> {profile?.taluka_name || (language === 'en' ? 'Paithan' : 'पैठण')}</p>
                <p><strong>{t.about.officeAddress}:</strong> {profile?.office_address || (language === 'en' ? 'At Post Narayangaon, Taluka Paithan, Dist. Chhatrapati Sambhajinagar, Maharashtra — 431148' : 'मु. पो. नारायणगाव, ता. पैठण, जि. छत्रपती संभाजीनगर, महाराष्ट्र — ४३११४८')}</p>
                <p><strong>{t.about.lgdCode}:</strong> <span className="font-mono font-bold text-[var(--brand-navy)]">{profile?.lgd_code || '549493'}</span></p>
              </div>
            </Card>

            <Card title={t.about.statsCardTitle}>
              <div className="space-y-2 text-xs text-[var(--text-secondary)]">
                <p><strong>{t.about.censusCode}:</strong> <span className="font-mono">{profile?.census_code || '549493'}</span></p>
                <p><strong>{t.about.contactPhone}:</strong> <span className="font-mono">{profile?.contact_phone || '02431-223022'}</span></p>
                <p><strong>{t.about.contactEmail}:</strong> {profile?.contact_email || 'grampanchayat.narayangaon@gov.in'}</p>
                <p><strong>{t.about.sarpanch}:</strong> {profile?.sarpanch_name || (language === 'en' ? '[Name Pending Verification]' : '[नाव प्रलंबित]')}</p>
                <p><strong>{t.about.gramSevak}:</strong> {profile?.gram_sevak_name || (language === 'en' ? 'ASHOK GANPAT WALE' : 'अशोक गणपत वाले')}</p>
              </div>
            </Card>
          </div>

          {/* Full Wikipedia-Style Knowledge Article */}
          <VillageKnowledgeArticle
            page={activePage}
            profile={profile}
            language={language}
          />
        </div>
      ) : (
        <PlaceholderNotice
          title={t.about.title}
          description={t.placeholders.pendingDataNotice}
        />
      )}
    </div>
  );
}
