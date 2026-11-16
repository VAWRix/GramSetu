'use client';

import React from 'react';
import { useLanguage } from '@/context/LanguageContext';
import { Badge } from './Badge';

interface PlaceholderNoticeProps {
  title?: string;
  description?: string;
  domainName?: string;
  className?: string;
}

export function PlaceholderNotice({
  title,
  description,
  domainName,
  className = '',
}: PlaceholderNoticeProps) {
  const { t } = useLanguage();

  return (
    <div
      role="region"
      aria-label={t.placeholders.pendingDataBadge}
      className={`border-2 border-dashed border-[var(--border-primary)] bg-[var(--bg-surface)] p-6 rounded-lg text-center ${className}`}
    >
      <div className="flex justify-center mb-3">
        <Badge variant="warning">
          {t.placeholders.pendingDataBadge}
        </Badge>
      </div>
      <h3 className="text-base font-semibold text-[var(--text-primary)] mb-1">
        {title || (domainName ? `${domainName} — ${t.placeholders.pendingDataBadge}` : t.placeholders.pendingDataBadge)}
      </h3>
      <p className="text-sm text-[var(--text-secondary)] max-w-xl mx-auto mb-2 leading-relaxed">
        {description || t.placeholders.pendingDataNotice}
      </p>
      <p className="text-xs text-[var(--text-muted)] italic">
        {t.placeholders.noFabricationWarning}
      </p>
    </div>
  );
}
