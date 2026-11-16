'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useLanguage } from '@/context/LanguageContext';

export function CmsSidebar() {
  const { t } = useLanguage();
  const pathname = usePathname();

  const links = [
    { href: '/cms', label: t.cms.dashboard, icon: '📊' },
    { href: '/cms/content', label: t.cms.contentPages, icon: '📄' },
    { href: '/cms/notices', label: t.cms.noticesManagement, icon: '📢' },
    { href: '/cms/documents', label: t.cms.documentsDisclosure, icon: '📑' },
    { href: '/cms/events', label: t.cms.eventsMeetings, icon: '📅' },
    { href: '/cms/schemes', label: t.cms.schemesManagement, icon: '🏛️' },
    { href: '/cms/gallery', label: t.cms.galleryManagement, icon: '🖼️' },
    { href: '/cms/profile', label: t.cms.profileManagement, icon: '🏛️' },
    { href: '/cms/governance', label: t.cms.governanceApprovals, icon: '⚖️' },
    { href: '/cms/audit', label: t.cms.auditLogs, icon: '🔒' },
  ];

  const isActive = (href: string) => {
    if (href === '/cms') return pathname === '/cms';
    return pathname.startsWith(href);
  };

  return (
    <aside
      role="navigation"
      aria-label="CMS Navigation"
      className="w-full md:w-64 bg-white border-r border-slate-200 text-slate-700 flex flex-col shrink-0 shadow-sm"
    >
      <div className="p-4 border-b border-slate-200 bg-slate-50">
        <h2 className="text-xs uppercase font-bold text-slate-700 tracking-wider">
          {t.cms.managementDomains}
        </h2>
      </div>

      <nav className="p-3 space-y-1 flex-1 bg-white">
        {links.map((link) => {
          const active = isActive(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded text-xs transition-colors focus-visible:outline-blue-600 ${
                active
                  ? 'bg-blue-50 text-blue-900 font-bold border-l-4 border-blue-700 shadow-sm'
                  : 'hover:bg-slate-100 text-slate-700 hover:text-slate-950 font-medium'
              }`}
              aria-current={active ? 'page' : undefined}
            >
              <span className="text-sm shrink-0">{link.icon}</span>
              <span className="truncate">{link.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Statutory Security Footnote */}
      <div className="p-3 bg-amber-50 border-t border-amber-200 text-[11px] text-amber-900 space-y-1">
        <p className="font-bold text-amber-900">सुरक्षा / Security:</p>
        <p className="text-amber-800 leading-tight">{t.cms.sessionTimeoutWarning}</p>
      </div>
    </aside>
  );
}
