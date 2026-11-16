'use client';

import React, { useState, useEffect } from 'react';
import { useLanguage } from '@/context/LanguageContext';
import { Alert, AlertSeverity } from '../ui/Alert';
import { fetchSiteConfig } from '@/lib/api';
import { EmergencyBannerData } from '@/lib/types';

interface EmergencyBannerProps {
  isActive?: boolean;
  severity?: AlertSeverity;
  message?: string;
  actionUrl?: string;
  actionLabel?: string;
}

export function EmergencyBanner({
  isActive: propIsActive,
  severity: propSeverity,
  message: propMessage,
  actionUrl: propActionUrl,
  actionLabel: propActionLabel,
}: EmergencyBannerProps = {}) {
  const { language } = useLanguage();
  const [fetchedBanner, setFetchedBanner] = useState<EmergencyBannerData | null>(null);

  useEffect(() => {
    if (propMessage !== undefined) return;
    let isMounted = true;
    fetchSiteConfig(language).then((data) => {
      if (isMounted) {
        setFetchedBanner(data?.emergency_banner || null);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [language, propMessage]);

  const activeMessage = propMessage ?? fetchedBanner?.message;
  const activeSeverity = (propSeverity ?? fetchedBanner?.severity ?? 'warning') as AlertSeverity;
  const activeActionUrl = propActionUrl ?? fetchedBanner?.action_url;
  const activeActionLabel = propActionLabel ?? fetchedBanner?.action_label;
  const isVisible = propIsActive ?? Boolean(fetchedBanner && fetchedBanner.message);

  if (!isVisible || !activeMessage) {
    return null;
  }

  const defaultTitles: Record<string, Record<AlertSeverity, string>> = {
    mr: {
      info: 'महत्त्वाची सूचना',
      warning: 'दक्षतेचा इशारा',
      danger: 'तातडीची आणीबाणी सूचना',
    },
    hi: {
      info: 'महत्वपूर्ण सूचना',
      warning: 'सतर्कता चेतावनी',
      danger: 'आपातकालीन चेतावनी',
    },
    en: {
      info: 'Official Advisory',
      warning: 'Public Alert',
      danger: 'Critical Emergency Broadcast',
    },
  };

  const title = defaultTitles[language]?.[activeSeverity] || defaultTitles.mr[activeSeverity];

  return (
    <div className="w-full bg-[var(--bg-surface)] border-b border-[var(--border-muted)] px-4 py-2">
      <div className="max-w-7xl mx-auto">
        <Alert
          severity={activeSeverity}
          title={title}
          actionUrl={activeActionUrl}
          actionLabel={activeActionLabel}
        >
          {activeMessage}
        </Alert>
      </div>
    </div>
  );
}
