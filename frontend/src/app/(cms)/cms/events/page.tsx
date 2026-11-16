'use client';

import React, { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Alert } from '@/components/ui/Alert';
import { useLanguage } from '@/context/LanguageContext';
import {
  fetchCmsEvents,
  createCmsEvent,
  updateCmsEvent,
  executeGovernanceAction,
  fetchAuthMe,
} from '@/lib/api';
import type { CmsEventItem, AuthUser } from '@/lib/types';

export default function CmsEventsPage() {
  const { t, language } = useLanguage();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [events, setEvents] = useState<CmsEventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editEventItem, setEditEventItem] = useState<CmsEventItem | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Form states
  const [title, setTitle] = useState('');
  const [eventType, setEventType] = useState('gram_sabha');
  const [startDt, setStartDt] = useState('');
  const [endDt, setEndDt] = useState('');
  const [venue, setVenue] = useState('ग्रामपंचायत कार्यालय सभागृह');
  const [description, setDescription] = useState('');
  const [agenda, setAgenda] = useState('');
  const [publishNow, setPublishNow] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const isSuperAdmin = currentUser?.role === 'super_admin';

  async function loadUser() {
    try {
      const me = await fetchAuthMe();
      if (me?.user) {
        setCurrentUser(me.user);
      }
    } catch (err) {
      console.error('Failed to load user profile', err);
    }
  }

  async function loadEvents() {
    setLoading(true);
    try {
      const res = await fetchCmsEvents();
      if (res) {
        setEvents(res.results);
      }
    } catch (err) {
      console.error('Failed to load events', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUser();
    loadEvents();
  }, []);

  function openCreateModal() {
    setTitle('');
    setEventType('gram_sabha');
    setStartDt('');
    setEndDt('');
    setVenue('ग्रामपंचायत कार्यालय सभागृह');
    setDescription('');
    setAgenda('');
    setPublishNow(false);
    setFeedback(null);
    setShowCreateModal(true);
  }

  function openEditModal(ev: CmsEventItem) {
    const tr = ev.translations[0];
    setTitle(tr?.title || '');
    setEventType(ev.event_type);
    setVenue(ev.venue_mr || '');
    setDescription(tr?.description || '');
    setAgenda(tr?.agenda || '');
    try {
      setStartDt(new Date(ev.start_datetime).toISOString().slice(0, 16));
      setEndDt(new Date(ev.end_datetime).toISOString().slice(0, 16));
    } catch {
      setStartDt('');
      setEndDt('');
    }
    setEditEventItem(ev);
    setFeedback(null);
  }

  async function handleCreateEvent(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !startDt || !endDt) {
      setFeedback({ type: 'error', message: 'Title, start time, and end time are required.' });
      return;
    }

    const startDate = new Date(startDt);
    const endDate = new Date(endDt);
    if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
      setFeedback({ type: 'error', message: 'Invalid start or end datetime format.' });
      return;
    }

    if (endDate.getTime() < startDate.getTime()) {
      setFeedback({
        type: 'error',
        message: language === 'mr'
          ? 'समाप्ती वेळ ही सुरुवातीच्या वेळेनंतर किंवा समान असावी (End time must be after or equal to start time).'
          : language === 'hi'
          ? 'समाप्ति समय प्रारंभ समय के बाद या बराबर होना चाहिए (End time must be after start time).'
          : 'End time must be greater than or equal to start time.',
      });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const payload: any = {
      title: title.trim(),
      event_type: eventType,
      start_datetime: startDate.toISOString(),
      end_datetime: endDate.toISOString(),
      venue_mr: venue.trim(),
      description: description.trim(),
      agenda: agenda.trim(),
      language_code: language,
    };
    if (publishNow && isSuperAdmin) {
      payload.publish_now = true;
    }

    const res = await createCmsEvent(payload);
    setSubmitting(false);

    if (res.success) {
      setFeedback({ type: 'success', message: t.cmsEvents.meetingScheduled });
      setShowCreateModal(false);
      loadEvents();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Failed to schedule meeting.' });
    }
  }

  async function handleUpdateEvent(e: React.FormEvent) {
    e.preventDefault();
    if (!editEventItem) return;
    if (!title.trim() || !startDt || !endDt) {
      setFeedback({ type: 'error', message: 'Title, start time, and end time are required.' });
      return;
    }

    const startDate = new Date(startDt);
    const endDate = new Date(endDt);
    if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
      setFeedback({ type: 'error', message: 'Invalid start or end datetime format.' });
      return;
    }

    if (endDate.getTime() < startDate.getTime()) {
      setFeedback({
        type: 'error',
        message: language === 'mr'
          ? 'समाप्ती वेळ ही सुरुवातीच्या वेळेनंतर किंवा समान असावी (End time must be after or equal to start time).'
          : language === 'hi'
          ? 'समाप्ति समय प्रारंभ समय के बाद या बराबर होना चाहिए (End time must be after start time).'
          : 'End time must be greater than or equal to start time.',
      });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const res = await updateCmsEvent(editEventItem.id, {
      title: title.trim(),
      event_type: eventType,
      start_datetime: startDate.toISOString(),
      end_datetime: endDate.toISOString(),
      venue_mr: venue.trim(),
      description: description.trim(),
      agenda: agenda.trim(),
      language_code: language,
    });

    setSubmitting(false);

    if (res.success) {
      setFeedback({ type: 'success', message: 'Meeting draft updated successfully.' });
      setEditEventItem(null);
      loadEvents();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Failed to update meeting.' });
    }
  }

  async function handleSubmitEvent(eventId: string) {
    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'event',
      action: 'submit',
      target_id: eventId,
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.governance.successApprove });
      loadEvents();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Submission failed.' });
    }
  }

  async function handlePublishEvent(eventId: string) {
    const notes = window.prompt(t.governance.notesLabel) || 'Direct publication by Super Administrator';
    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'event',
      action: 'publish',
      target_id: eventId,
      notes,
    });

    if (res.success) {
      setFeedback({ type: 'success', message: t.governance.successPublish });
      loadEvents();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Publish failed.' });
    }
  }

  async function handleCancelEvent(eventId: string) {
    const reason = window.prompt(t.cmsEvents.cancelReasonLabel);
    if (!reason || reason.trim().length < 10) {
      alert('Cancellation reason must be at least 10 characters.');
      return;
    }

    setFeedback(null);
    const res = await executeGovernanceAction({
      entity_type: 'event',
      action: 'cancel',
      target_id: eventId,
      reason: reason.trim(),
    });

    if (res.success) {
      setFeedback({ type: 'success', message: 'Meeting has been cancelled.' });
      loadEvents();
    } else {
      setFeedback({ type: 'error', message: res.error || 'Cancellation failed.' });
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white p-5 rounded-lg border shadow-sm">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span aria-hidden="true">📅</span>
            <span>{t.cmsEvents.pageTitle}</span>
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            {t.cmsEvents.pageSubtitle}
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold self-start sm:self-auto transition-colors shadow-sm inline-flex items-center gap-1.5"
        >
          <span aria-hidden="true">+</span>
          <span>{t.cmsEvents.scheduleMeeting}</span>
        </button>
      </div>

      {/* Feedback Alert */}
      {feedback && (
        <Alert
          severity={feedback.type === 'success' ? 'info' : 'danger'}
          title={feedback.type === 'success' ? 'Success' : 'Error'}
        >
          <p>{feedback.message}</p>
        </Alert>
      )}

      <Alert severity="info" title={t.cmsEvents.historicalRuleTitle}>
        <p>{t.cmsEvents.historicalRuleDesc}</p>
      </Alert>

      {/* Events List */}
      <div className="space-y-3">
        {loading ? (
          <div className="p-8 text-center bg-white rounded-lg border border-slate-200 text-slate-500 text-xs shadow-sm">
            {t.common.loading}
          </div>
        ) : events.length === 0 ? (
          <div className="p-10 text-center bg-white rounded-lg border border-slate-200 text-slate-600 text-xs shadow-sm">
            {t.cmsEvents.emptyList}
          </div>
        ) : (
          events.map((ev) => (
            <div
              key={ev.id}
              className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 shadow-sm hover:border-slate-300 transition-all"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2 py-0.5 bg-blue-50 text-blue-800 border border-blue-200 rounded text-[10px] font-bold uppercase font-mono">
                    {ev.event_type}
                  </span>
                  <Badge
                    variant={
                      ev.status === 'published'
                        ? 'success'
                        : ev.status === 'completed'
                        ? 'primary'
                        : ev.status === 'cancelled'
                        ? 'danger'
                        : 'warning'
                    }
                  >
                    {ev.status}
                  </Badge>
                  <h3 className="text-sm font-bold text-slate-900">
                    {ev.translations[0]?.title || `Event (${ev.event_type})`}
                  </h3>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {/* Draft State */}
                  {ev.status === 'draft' && (
                    <>
                      <button
                        onClick={() => openEditModal(ev)}
                        className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded text-xs font-medium inline-flex items-center gap-1 transition-colors"
                      >
                        <span aria-hidden="true">✏️</span>
                        <span>{t.cmsEvents.editDraft}</span>
                      </button>
                      <button
                        onClick={() => handleSubmitEvent(ev.id)}
                        className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold shadow-sm transition-colors"
                      >
                        {t.governance.btnSubmitReview}
                      </button>
                      {isSuperAdmin && (
                        <button
                          onClick={() => handlePublishEvent(ev.id)}
                          className="px-3 py-1 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-xs font-semibold shadow-sm transition-colors"
                        >
                          {t.cmsEvents.publishDirectly}
                        </button>
                      )}
                    </>
                  )}

                  {/* Pending Review State */}
                  {ev.status === 'pending_approval' && (
                    isSuperAdmin ? (
                      <button
                        onClick={() => handlePublishEvent(ev.id)}
                        className="px-3 py-1 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded text-xs font-semibold shadow-sm transition-colors inline-flex items-center gap-1"
                      >
                        <span aria-hidden="true">✓</span>
                        <span>{t.governance.btnPublish}</span>
                      </button>
                    ) : (
                      <span className="px-2.5 py-1 bg-amber-50 text-amber-800 border border-amber-300 rounded text-xs font-semibold">
                        {t.governance.btnAwaitingReview}
                      </span>
                    )
                  )}

                  {/* Cancel Action */}
                  {ev.status !== 'cancelled' && ev.status !== 'completed' && (
                    <button
                      onClick={() => handleCancelEvent(ev.id)}
                      className="px-2.5 py-1 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-300 rounded text-xs font-medium transition-colors"
                    >
                      {t.cmsEvents.cancelMeeting}
                    </button>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-700">
                <div>
                  <span className="text-slate-500 font-medium">{t.cmsEvents.venue}: </span>
                  <span className="text-slate-900 font-semibold">{ev.venue_mr}</span>
                </div>
                <div>
                  <span className="text-slate-500 font-medium">{t.cmsEvents.schedule}: </span>
                  <span className="text-slate-900 font-medium">
                    {new Date(ev.start_datetime).toLocaleString('en-IN')} - {new Date(ev.end_datetime).toLocaleTimeString('en-IN')}
                  </span>
                </div>
              </div>

              {ev.cancellation_reason && (
                <div className="p-2.5 bg-rose-50 rounded-lg border border-rose-200 text-xs text-rose-800">
                  <strong>Cancellation Reason:</strong> {ev.cancellation_reason}
                </div>
              )}

              {ev.translations[0]?.agenda && (
                <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-700 space-y-1">
                  <div className="font-semibold text-slate-800 text-[11px] uppercase tracking-wider">{t.cmsEvents.agenda}:</div>
                  <pre className="font-sans text-xs whitespace-pre-wrap text-slate-700">{ev.translations[0].agenda}</pre>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Schedule / Create Event Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">📅</span>
                <span>{t.cmsEvents.scheduleMeeting}</span>
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                aria-label={t.common.close}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateEvent} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsEvents.titleLabel}:
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="उदा. विशेष महिला ग्रामसभा / Special Gram Sabha or Monthly Review"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsEvents.typeLabel}:
                  </label>
                  <select
                    value={eventType}
                    onChange={(e) => setEventType(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  >
                    <option value="gram_sabha">
                      {language === 'mr' ? 'ग्रामसभा बैठक (Gram Sabha)' : language === 'hi' ? 'ग्राम सभा बैठक (Gram Sabha)' : 'Gram Sabha Meeting'}
                    </option>
                    <option value="ward_meeting">
                      {language === 'mr' ? 'वॉर्ड सभा बैठक (Ward Sabha)' : language === 'hi' ? 'वार्ड सभा बैठक (Ward Sabha)' : 'Ward Sabha Meeting'}
                    </option>
                    <option value="health_camp">
                      {language === 'mr' ? 'आरोग्य / लसीकरण शिबिर (Health Camp)' : language === 'hi' ? 'स्वास्थ्य शिविर (Health Camp)' : 'Health / Vaccination Camp'}
                    </option>
                    <option value="hearing">
                      {language === 'mr' ? 'प्रशासकीय सुनावणी (Grievance Hearing)' : language === 'hi' ? 'प्रशासनिक सुनवाई (Hearing)' : 'Administrative Grievance Hearing'}
                    </option>
                    <option value="cultural">
                      {language === 'mr' ? 'राष्ट्रीय / सांस्कृतिक कार्यक्रम (Cultural Event)' : language === 'hi' ? 'सांस्कृतिक कार्यक्रम (Cultural Event)' : 'National / Cultural Event'}
                    </option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsEvents.venue}:
                  </label>
                  <input
                    type="text"
                    required
                    value={venue}
                    onChange={(e) => setVenue(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsEvents.startTime}:
                  </label>
                  <input
                    type="datetime-local"
                    required
                    value={startDt}
                    onChange={(e) => setStartDt(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsEvents.endTime}:
                  </label>
                  <input
                    type="datetime-local"
                    required
                    value={endDt}
                    onChange={(e) => setEndDt(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsEvents.agenda}:
                </label>
                <textarea
                  rows={3}
                  value={agenda}
                  onChange={(e) => setAgenda(e.target.value)}
                  placeholder="उदा. १. मागील सभेचे इतिवृत्त वाचन / Review of previous minutes..."
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsEvents.description}:
                </label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Additional instructions..."
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              {/* Super Admin Direct Publish Option */}
              {isSuperAdmin && (
                <label className="flex items-center gap-2 cursor-pointer bg-blue-50 border border-blue-200 p-2.5 rounded-lg mt-2">
                  <input
                    type="checkbox"
                    checked={publishNow}
                    onChange={(e) => setPublishNow(e.target.checked)}
                    className="rounded text-[#1e3a8a] focus:ring-blue-600"
                  />
                  <div>
                    <span className="text-[#1e3a8a] font-bold block">{t.cmsEvents.publishNow}</span>
                    <span className="text-[11px] text-blue-700 block">{t.governance.publishNowHelp}</span>
                  </div>
                </label>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.close}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {submitting ? t.common.loading : (publishNow ? t.cmsEvents.publishDirectly : t.governance.btnSaveDraft)}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Event Modal */}
      {editEventItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span aria-hidden="true">✏️</span>
                <span>{t.cmsEvents.editDraft}</span>
              </h3>
              <button
                onClick={() => setEditEventItem(null)}
                aria-label={t.common.close}
                className="text-slate-400 hover:text-slate-700 text-lg font-bold p-1 rounded"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleUpdateEvent} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsEvents.titleLabel}:
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsEvents.typeLabel}:
                  </label>
                  <select
                    value={eventType}
                    onChange={(e) => setEventType(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  >
                    <option value="gram_sabha">
                      {language === 'mr' ? 'ग्रामसभा बैठक (Gram Sabha)' : language === 'hi' ? 'ग्राम सभा बैठक (Gram Sabha)' : 'Gram Sabha Meeting'}
                    </option>
                    <option value="ward_meeting">
                      {language === 'mr' ? 'वॉर्ड सभा बैठक (Ward Sabha)' : language === 'hi' ? 'वार्ड सभा बैठक (Ward Sabha)' : 'Ward Sabha Meeting'}
                    </option>
                    <option value="health_camp">
                      {language === 'mr' ? 'आरोग्य / लसीकरण शिबिर (Health Camp)' : language === 'hi' ? 'स्वास्थ्य शिविर (Health Camp)' : 'Health / Vaccination Camp'}
                    </option>
                    <option value="hearing">
                      {language === 'mr' ? 'प्रशासकीय सुनावणी (Grievance Hearing)' : language === 'hi' ? 'प्रशासनिक सुनवाई (Hearing)' : 'Administrative Grievance Hearing'}
                    </option>
                    <option value="cultural">
                      {language === 'mr' ? 'राष्ट्रीय / सांस्कृतिक कार्यक्रम (Cultural Event)' : language === 'hi' ? 'सांस्कृतिक कार्यक्रम (Cultural Event)' : 'National / Cultural Event'}
                    </option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsEvents.venue}:
                  </label>
                  <input
                    type="text"
                    required
                    value={venue}
                    onChange={(e) => setVenue(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsEvents.startTime}:
                  </label>
                  <input
                    type="datetime-local"
                    required
                    value={startDt}
                    onChange={(e) => setStartDt(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">
                    {t.cmsEvents.endTime}:
                  </label>
                  <input
                    type="datetime-local"
                    required
                    value={endDt}
                    onChange={(e) => setEndDt(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsEvents.agenda}:
                </label>
                <textarea
                  rows={3}
                  value={agenda}
                  onChange={(e) => setAgenda(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  {t.cmsEvents.description}:
                </label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setEditEventItem(null)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                >
                  {t.common.close}
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-[#1e3a8a] hover:bg-blue-900 text-white rounded-lg text-xs font-semibold shadow-sm"
                >
                  {submitting ? t.common.loading : t.governance.btnSaveDraft}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
