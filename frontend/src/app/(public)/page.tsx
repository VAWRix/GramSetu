'use client';

import React from 'react';
import Link from 'next/link';
import { useLanguage } from '@/context/LanguageContext';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PlaceholderNotice } from '@/components/ui/PlaceholderNotice';

export default function HomePage() {
  const { t } = useLanguage();

  const services = [
    {
      title: t.nav.notices,
      desc: t.home.noticesCardDesc,
      href: '/notices',
      icon: '📢',
      badgeText: t.home.publicBadge,
    },
    {
      title: t.nav.documents,
      desc: t.home.documentsCardDesc,
      href: '/documents',
      icon: '📑',
      badgeText: t.home.downloadBadge,
    },
    {
      title: t.nav.events,
      desc: t.home.eventsCardDesc,
      href: '/events',
      icon: '📅',
      badgeText: t.home.scheduleBadge,
    },
    {
      title: t.nav.schemes,
      desc: t.home.schemesCardDesc,
      href: '/schemes',
      icon: '🏛️',
      badgeText: t.home.statutoryBadge,
    },
    {
      title: t.nav.gallery,
      desc: t.home.galleryCardDesc,
      href: '/gallery',
      icon: '🖼️',
      badgeText: t.home.galleryBadge,
    },
    {
      title: t.nav.search,
      desc: t.home.searchCardDesc,
      href: '/search',
      icon: '🔍',
      badgeText: t.home.searchBadge,
    },
  ];

  return (
    <div className="space-y-8">
      {/* Official Hero / Statutory Welcome Banner */}
      <section
        aria-labelledby="welcome-heading"
        className="bg-gradient-to-r from-blue-950 via-slate-900 to-blue-900 text-white rounded-xl p-6 sm:p-8 shadow-sm border border-blue-900"
      >
        <div className="max-w-3xl">
          <Badge variant="warning" className="mb-3">
            {t.home.statutoryWelcomeBadge}
          </Badge>
          <h2 id="welcome-heading" className="text-2xl sm:text-3xl font-extrabold tracking-tight mb-3">
            {t.header.panchayatOffice} — {t.home.statutoryWelcomeTitle}
          </h2>
          <p className="text-slate-300 text-sm sm:text-base leading-relaxed mb-4">
            {t.home.statutoryWelcomeDesc}
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/notices"
              className="inline-flex items-center px-4 py-2 rounded-md bg-[var(--brand-saffron)] text-black font-semibold text-xs hover:bg-amber-400 transition-colors focus-visible:outline-white"
            >
              📢 {t.nav.notices}
            </Link>
            <Link
              href="/documents"
              className="inline-flex items-center px-4 py-2 rounded-md bg-blue-800 text-white font-medium text-xs hover:bg-blue-700 transition-colors focus-visible:outline-white"
            >
              📑 {t.nav.documents}
            </Link>
            <Link
              href="/about"
              className="inline-flex items-center px-4 py-2 rounded-md bg-slate-800 text-slate-200 font-medium text-xs hover:bg-slate-700 transition-colors focus-visible:outline-white border border-slate-700"
            >
              ℹ️ {t.nav.about}
            </Link>
          </div>
        </div>
      </section>

      {/* Statutory Services & Quick Access Grid */}
      <section aria-labelledby="services-heading">
        <div className="flex items-center justify-between mb-4">
          <h2 id="services-heading" className="text-lg font-bold text-[var(--text-primary)]">
            {t.home.servicesHeading}
          </h2>
          <span className="text-xs text-[var(--text-muted)]">
            {t.home.servicesSubheading}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {services.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="group focus-visible:outline-2 rounded-lg"
            >
              <Card
                className="h-full hover:border-[var(--brand-navy)] hover:shadow-md transition-all duration-150"
                badge={<Badge variant="primary">{item.badgeText}</Badge>}
              >
                <div className="flex items-start gap-3">
                  <span className="text-2xl p-2 rounded-lg bg-[var(--bg-muted)] group-hover:scale-105 transition-transform shrink-0">
                    {item.icon}
                  </span>
                  <div>
                    <h3 className="font-semibold text-sm text-[var(--text-primary)] group-hover:text-[var(--brand-navy)] transition-colors">
                      {item.title}
                    </h3>
                    <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">
                      {item.desc}
                    </p>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      {/* Authentic Content Notice Placeholder */}
      <section aria-labelledby="authenticity-heading">
        <PlaceholderNotice
          title={t.home.authenticityNoticeTitle}
          description={t.home.authenticityNoticeDesc}
        />
      </section>
    </div>
  );
}
