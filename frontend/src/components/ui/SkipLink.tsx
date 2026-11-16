'use client';

import React from 'react';
import { useLanguage } from '@/context/LanguageContext';

export function SkipLink({ targetId = 'main-content' }: { targetId?: string }) {
  const { t } = useLanguage();

  return (
    <a
      href={`#${targetId}`}
      className="skip-link"
    >
      {t.accessibility.skipToMain}
    </a>
  );
}
