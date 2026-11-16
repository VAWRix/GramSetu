'use client';

import React from 'react';
import { useLanguage } from '@/context/LanguageContext';
import { useAccessibility } from '@/context/AccessibilityContext';
import { SupportedLanguage } from '@/lib/i18n';
import { SkipLink } from '../ui/SkipLink';

export function AccessibilityBar() {
  const { language, setLanguage, t } = useLanguage();
  const { theme, setTheme, fontSize, increaseFontSize, decreaseFontSize, resetFontSize } = useAccessibility();

  const handleLanguageChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setLanguage(e.target.value as SupportedLanguage);
  };

  const handleThemeToggle = () => {
    if (theme === 'contrast') {
      setTheme('light');
    } else {
      setTheme('contrast');
    }
  };

  return (
    <div
      role="region"
      aria-label="Accessibility and Language Bar"
      className="bg-[var(--brand-navy-dark)] text-white text-xs py-1.5 px-4 border-b border-blue-900"
    >
      <SkipLink />
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
        {/* Left: Official Government of Maharashtra attribution */}
        <div className="flex items-center gap-2">
          <span className="font-semibold tracking-wide">
            {t.accessibility.govOfMaharashtra}
          </span>
          <span className="text-blue-300 hidden sm:inline">|</span>
          <span className="text-blue-200 hidden sm:inline">
            {t.accessibility.panchayatRajDept}
          </span>
        </div>

        {/* Right: Accessibility toolbar and Language Switcher */}
        <div className="flex items-center gap-3 ml-auto">
          {/* Text Resize Controls (GIGW) */}
          <div className="flex items-center border border-blue-800 rounded bg-blue-950/50">
            <button
              type="button"
              onClick={decreaseFontSize}
              aria-label={t.accessibility.decreaseFont}
              title={t.accessibility.decreaseFont}
              disabled={fontSize === 'small'}
              className="px-2 py-0.5 hover:bg-blue-800 focus-visible:outline-white disabled:opacity-40"
            >
              A-
            </button>
            <button
              type="button"
              onClick={resetFontSize}
              aria-label={t.accessibility.normalFont}
              title={t.accessibility.normalFont}
              className="px-2 py-0.5 border-x border-blue-800 hover:bg-blue-800 focus-visible:outline-white"
            >
              A
            </button>
            <button
              type="button"
              onClick={increaseFontSize}
              aria-label={t.accessibility.increaseFont}
              title={t.accessibility.increaseFont}
              disabled={fontSize === 'x-large'}
              className="px-2 py-0.5 hover:bg-blue-800 focus-visible:outline-white disabled:opacity-40"
            >
              A+
            </button>
          </div>

          {/* High Contrast Toggle (GIGW) */}
          <button
            type="button"
            onClick={handleThemeToggle}
            aria-pressed={theme === 'contrast'}
            aria-label={t.accessibility.highContrast}
            title={t.accessibility.highContrast}
            className={`px-2 py-0.5 rounded border border-blue-700 transition-colors focus-visible:outline-white ${
              theme === 'contrast'
                ? 'bg-yellow-400 text-black font-bold'
                : 'hover:bg-blue-800 text-white'
            }`}
          >
            {theme === 'contrast' ? t.accessibility.standardTheme : t.accessibility.highContrast}
          </button>

          {/* Theme Selector (Light / Dark) */}
          {theme !== 'contrast' && (
            <button
              type="button"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label={theme === 'dark' ? t.accessibility.themeLight : t.accessibility.themeDark}
              title={theme === 'dark' ? t.accessibility.themeLight : t.accessibility.themeDark}
              className="px-2 py-0.5 rounded border border-blue-700 hover:bg-blue-800 transition-colors focus-visible:outline-white"
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
          )}

          {/* Explicit Language Selector */}
          <div className="flex items-center gap-1">
            <label htmlFor="portal-lang-select" className="sr-only">
              {t.accessibility.language}
            </label>
            <select
              id="portal-lang-select"
              value={language}
              onChange={handleLanguageChange}
              className="bg-blue-950 text-white border border-blue-700 rounded px-2 py-0.5 text-xs focus-visible:outline-white cursor-pointer"
            >
              <option value="mr">मराठी (Default)</option>
              <option value="hi">हिंदी</option>
              <option value="en">English</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}
