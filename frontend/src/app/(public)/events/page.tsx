'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/context/LanguageContext';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PlaceholderNotice } from '@/components/ui/PlaceholderNotice';
import { fetchPublicEvents } from '@/lib/api';
import { PublicEventItem } from '@/lib/types';

export default function EventsPage() {
  const { t, language } = useLanguage();
  const [filter, setFilter] = useState<'upcoming' | 'past' | 'all'>('upcoming');
  const [events, setEvents] = useState<PublicEventItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    fetchPublicEvents(language, filter).then((data) => {
      if (isMounted) {
        if (data && Array.isArray(data.results)) {
          setEvents(data.results as PublicEventItem[]);
        } else {
          setEvents([]);
        }
        setLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [language, filter]);

  // Cancelled events with active alert window (or cancelled events in current view)
  const activeCancellationAlerts = events.filter(
    (ev) => ev.status === 'cancelled' && (ev.is_cancellation_alert_active || filter === 'upcoming')
  );

  return (
    <div className="space-y-6">
      <header className="border-b border-[var(--border-muted)] pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            {t.events.title}
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t.events.subtitle}
          </p>
        </div>

        {/* Filter buttons */}
        <div className="inline-flex rounded-md border border-[var(--border-primary)] p-0.5 bg-[var(--bg-muted)] text-xs">
          <button
            type="button"
            onClick={() => setFilter('upcoming')}
            className={`px-3 py-1 rounded font-medium transition-colors ${
              filter === 'upcoming'
                ? 'bg-[var(--brand-navy)] text-white shadow-xs'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {t.events.filterUpcoming}
          </button>
          <button
            type="button"
            onClick={() => setFilter('past')}
            className={`px-3 py-1 rounded font-medium transition-colors ${
              filter === 'past'
                ? 'bg-[var(--brand-navy)] text-white shadow-xs'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {t.events.filterPast}
          </button>
          <button
            type="button"
            onClick={() => setFilter('all')}
            className={`px-3 py-1 rounded font-medium transition-colors ${
              filter === 'all'
                ? 'bg-[var(--brand-navy)] text-white shadow-xs'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {t.events.filterAll}
          </button>
        </div>
      </header>

      {/* Prominent Active Cancellation Alert Banners (with 6-Hour Alert Lifecycle) */}
      {activeCancellationAlerts.length > 0 && (
        <div className="space-y-3">
          {activeCancellationAlerts.map((cev) => (
            <div
              key={`alert-${cev.id}`}
              className="bg-rose-50 border-2 border-rose-500 rounded-xl p-4 sm:p-5 shadow-sm text-rose-950 space-y-2.5"
              role="alert"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rose-200 pb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xl" aria-hidden="true">⚠️</span>
                  <span className="font-bold text-sm sm:text-base text-rose-900 uppercase tracking-wide">
                    {language === 'mr'
                      ? 'महत्त्वाची वैधानिक सूचना: सभा / बैठक रद्द'
                      : language === 'hi'
                      ? 'महत्वपूर्ण सूचना: बैठक रद्द'
                      : 'Statutory Notice: Meeting Cancelled'}
                  </span>
                </div>
                <Badge variant="danger">
                  {cev.status_display || (language === 'mr' ? 'रद्द / Cancelled' : 'Cancelled')}
                </Badge>
              </div>

              <div className="space-y-1.5 text-xs">
                <div className="font-bold text-sm text-slate-900">{cev.title}</div>
                <div className="text-slate-700">
                  <strong>{language === 'mr' ? 'नियोजित दिनांक व वेळ:' : 'Scheduled Date & Time:'}</strong>{' '}
                  <span className="line-through text-slate-500">{new Date(cev.start_datetime).toLocaleString('en-IN')}</span>
                  {' '}• <strong>{language === 'mr' ? 'स्थान:' : 'Venue:'}</strong> {cev.venue}
                </div>
                <div className="bg-white p-3 rounded-lg border border-rose-200 mt-2">
                  <strong className="text-rose-900 block font-bold mb-1">
                    {language === 'mr'
                      ? 'रद्द करण्याचे अधिकृत कारण (Official Cancellation Reason):'
                      : 'Official Cancellation Reason:'}
                  </strong>
                  <p className="text-rose-800 text-xs sm:text-sm font-semibold whitespace-pre-wrap">
                    {cev.cancellation_reason || (language === 'mr' ? 'प्रशासकीय कारणास्तव सभा स्थगित करण्यात आली आहे.' : 'Cancelled due to administrative reasons.')}
                  </p>
                  {cev.cancelled_at && (
                    <div className="text-[11px] text-slate-500 mt-2 pt-1 border-t border-rose-100 flex flex-wrap items-center justify-between gap-2">
                      <span>
                        {language === 'mr' ? 'रद्द केल्याची अधिकृत वेळ:' : 'Cancelled on:'}{' '}
                        <strong>{new Date(cev.cancelled_at).toLocaleString('en-IN')}</strong>
                      </span>
                      <span className="text-amber-800 font-medium">
                        {language === 'mr'
                          ? 'सदर तातडीची सूचना ६ तास सक्रिय राहील'
                          : 'Public alert window active for 6 hours'}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-xs text-[var(--text-muted)]">
          {t.common.loading}
        </div>
      ) : events.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {events.map((ev) => {
            const isCancelled = ev.status === 'cancelled';
            return (
              <Card
                key={ev.id}
                title={
                  <span className={isCancelled ? 'line-through text-slate-500' : 'text-slate-900'}>
                    {ev.title || t.events.defaultEventTitle}
                  </span>
                }
                subtitle={`${ev.event_type_display} • ${ev.venue}`}
                badge={
                  <div className="flex items-center gap-1.5">
                    {ev.is_fallback && (
                      <span className="px-1.5 py-0.5 text-[10px] bg-slate-100 text-slate-600 rounded border border-slate-200">
                        {language === 'hi' ? 'मूल मराठी' : 'Marathi Record'}
                      </span>
                    )}
                    <Badge variant={isCancelled ? 'danger' : 'primary'}>
                      {ev.status_display}
                    </Badge>
                  </div>
                }
              >
                <div className="space-y-2 text-xs text-[var(--text-secondary)]">
                  <p>
                    <strong>{t.events.datetimeLabel}</strong>{' '}
                    <span className={isCancelled ? 'line-through text-slate-400' : ''}>
                      {new Date(ev.start_datetime).toLocaleString('en-IN')}
                    </span>
                  </p>
                  {ev.agenda && <p><strong>{t.events.agendaLabel}</strong> {ev.agenda}</p>}
                  {ev.venue && <p><strong>{t.events.venueLabel}</strong> {ev.venue}</p>}

                  {/* Prominent Cancellation Callout */}
                  {isCancelled && ev.cancellation_reason && (
                    <div className="mt-3 p-3 bg-rose-50 border border-rose-300 rounded-lg text-rose-900 space-y-1">
                      <div className="flex items-center gap-1.5 font-bold text-xs text-rose-800">
                        <span aria-hidden="true">⚠️</span>
                        <span>{t.events.cancellationReason}</span>
                      </div>
                      <p className="text-xs font-semibold text-rose-950 whitespace-pre-wrap pl-4">
                        {ev.cancellation_reason}
                      </p>
                      {ev.cancelled_at && (
                        <p className="text-[10px] text-slate-500 pl-4 pt-1">
                          नोंदणी दिनांक:{' '}
                          <strong>{new Date(ev.cancelled_at).toLocaleString('en-IN')}</strong>
                        </p>
                      )}
                    </div>
                  )}

                  {ev.requires_registration && !isCancelled && (
                    <div className="bg-blue-50 border border-blue-200 p-2.5 rounded text-blue-900 text-xs">
                      <strong>उपस्थिती सूचना: </strong>
                      {ev.registration_instructions || 'नागरिकांनी वेळेवर उपस्थित राहावे.'}
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <PlaceholderNotice
          title={filter === 'upcoming' ? t.events.emptyUpcomingTitle : t.events.emptyPastTitle}
          description={t.events.emptyDesc}
        />
      )}
    </div>
  );
}
