'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';

export type PortalTheme = 'light' | 'dark' | 'contrast';
export type FontSize = 'small' | 'normal' | 'large' | 'x-large';

interface AccessibilityContextType {
  theme: PortalTheme;
  setTheme: (theme: PortalTheme) => void;
  fontSize: FontSize;
  setFontSize: (size: FontSize) => void;
  increaseFontSize: () => void;
  decreaseFontSize: () => void;
  resetFontSize: () => void;
}

const AccessibilityContext = createContext<AccessibilityContextType | undefined>(undefined);

const THEME_KEY = 'gramsetu_theme_pref';
const FONT_SIZE_KEY = 'gramsetu_fontsize_pref';

export function AccessibilityProvider({ children }: { children: React.ReactNode }) {
  // Deterministic initial render: Always start with default 'light' and 'normal'
  // on both SSR and initial client hydration to prevent hydration mismatches.
  const [theme, setThemeState] = useState<PortalTheme>('light');
  const [fontSize, setFontSizeState] = useState<FontSize>('normal');

  // Restore saved accessibility preferences strictly after initial hydration
  useEffect(() => {
    try {
      const savedTheme = localStorage.getItem(THEME_KEY) as PortalTheme;
      const savedFont = localStorage.getItem(FONT_SIZE_KEY) as FontSize;

      if (savedTheme && ['light', 'dark', 'contrast'].includes(savedTheme) && savedTheme !== 'light') {
        setThemeState(savedTheme);
      }
      if (savedFont && ['small', 'normal', 'large', 'x-large'].includes(savedFont) && savedFont !== 'normal') {
        setFontSizeState(savedFont);
      }
    } catch {
      // Ignore storage errors
    }
  }, []);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', theme);
      document.documentElement.setAttribute('data-font-size', fontSize);
    }
  }, [theme, fontSize]);

  const setTheme = (newTheme: PortalTheme) => {
    setThemeState(newTheme);
    try {
      localStorage.setItem(THEME_KEY, newTheme);
    } catch {
      // Ignore storage errors
    }
  };

  const setFontSize = (size: FontSize) => {
    setFontSizeState(size);
    try {
      localStorage.setItem(FONT_SIZE_KEY, size);
    } catch {
      // Ignore storage errors
    }
  };

  const increaseFontSize = () => {
    if (fontSize === 'small') setFontSize('normal');
    else if (fontSize === 'normal') setFontSize('large');
    else if (fontSize === 'large') setFontSize('x-large');
  };

  const decreaseFontSize = () => {
    if (fontSize === 'x-large') setFontSize('large');
    else if (fontSize === 'large') setFontSize('normal');
    else if (fontSize === 'normal') setFontSize('small');
  };

  const resetFontSize = () => {
    setFontSize('normal');
  };

  return (
    <AccessibilityContext.Provider
      value={{
        theme,
        setTheme,
        fontSize,
        setFontSize,
        increaseFontSize,
        decreaseFontSize,
        resetFontSize,
      }}
    >
      {children}
    </AccessibilityContext.Provider>
  );
}

export function useAccessibility() {
  const context = useContext(AccessibilityContext);
  if (!context) {
    throw new Error('useAccessibility must be used within an AccessibilityProvider');
  }
  return context;
}
