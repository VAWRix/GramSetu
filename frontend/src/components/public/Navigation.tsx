'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/context/LanguageContext';

export function Navigation() {
  const { t } = useLanguage();
  const [pathname, setPathname] = useState('');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    setPathname(window.location.pathname);
    const onPopState = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navLinks = [
    { href: '/', label: t.nav.home },
    { href: '/about', label: t.nav.about },
    { href: '/notices', label: t.nav.notices },
    { href: '/documents', label: t.nav.documents },
    { href: '/events', label: t.nav.events },
    { href: '/schemes', label: t.nav.schemes },
    { href: '/gallery', label: t.nav.gallery },
    { href: '/search', label: t.nav.search },
  ];

  const isActive = (href: string) => {
    if (!pathname) return false;
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  return (
    <nav
      role="navigation"
      aria-label="Main Navigation"
      className="bg-[var(--brand-navy)] text-white shadow-xs sticky top-0 z-40"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between">
        {/* Mobile menu toggle */}
        <div className="flex items-center md:hidden py-2.5">
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-nav-menu"
            aria-label={t.nav.menuToggle}
            className="p-1.5 rounded text-white hover:bg-blue-800 focus-visible:outline-white"
          >
            <span className="sr-only">{t.nav.menuToggle}</span>
            {mobileMenuOpen ? (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
          <span className="ml-2 font-semibold text-sm">{t.nav.menuToggle}</span>
        </div>

        {/* Desktop Navigation Links */}
        <ul className="hidden md:flex items-center space-x-1 py-1">
          {navLinks.map((item) => {
            const active = isActive(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setPathname(item.href)}
                  className={`inline-block px-3 py-2 rounded text-xs font-medium transition-colors focus-visible:outline-white ${
                    active
                      ? 'bg-blue-950 text-white font-bold border-b-2 border-[var(--brand-saffron)]'
                      : 'hover:bg-blue-800 text-blue-50'
                  }`}
                  aria-current={active ? 'page' : undefined}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>

        {/* Right side: Staff CMS Portal Link */}
        <div className="py-2">
          <Link
            href="/cms"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold bg-[var(--brand-saffron)] text-black hover:bg-amber-400 transition-colors focus-visible:outline-white"
            title={t.nav.staffPortal}
          >
            <span>🔐</span>
            <span>{t.nav.staffPortal}</span>
          </Link>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div
          id="mobile-nav-menu"
          className="md:hidden border-t border-blue-800 bg-blue-950 px-4 py-3 space-y-1"
        >
          {navLinks.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => { setPathname(item.href); setMobileMenuOpen(false); }}
                className={`block px-3 py-2 rounded text-sm font-medium transition-colors ${
                  active
                    ? 'bg-blue-900 text-white font-bold border-l-4 border-[var(--brand-saffron)]'
                    : 'text-blue-100 hover:bg-blue-900'
                }`}
                aria-current={active ? 'page' : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      )}
    </nav>
  );
}
