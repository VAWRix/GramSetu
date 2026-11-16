"""
Public views for Panchayat events and meetings.

Only approved, published, completed, or cancelled events are visible to citizens.
Draft or unapproved events strictly return 404 to anonymous users.
"""

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from apps.events.models import (
    PanchayatEvent,
    EventTranslation,
    LANGUAGE_MARATHI,
    LANGUAGE_CHOICES,
)
from apps.identity.permissions import is_super_admin, is_operator


def event_list_view(request):
    """
    Public listing of approved Panchayat events.
    Supports ?lang=mr|hi|en and ?filter=upcoming|past|all.
    """
    lang = request.GET.get('lang', LANGUAGE_MARATHI)
    valid_langs = [c[0] for c in LANGUAGE_CHOICES]
    if lang not in valid_langs:
        lang = LANGUAGE_MARATHI

    time_filter = request.GET.get('filter', 'upcoming')
    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')
    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')

    qs = PanchayatEvent.objects.public_eligible(allow_archived=allow_archived)
    if allow_fallback:
        # Filter events that have either the requested language or primary statutory Marathi translation
        qs = qs.filter(translations__language_code__in=[lang, LANGUAGE_MARATHI]).distinct()
    else:
        qs = qs.for_language(lang)

    if time_filter == 'upcoming':
        qs = qs.upcoming().order_by('start_datetime')
    elif time_filter == 'past':
        qs = qs.past().order_by('-start_datetime')
    else:
        qs = qs.order_by('-start_datetime')

    events_data = []
    for ev in qs:
        trans = ev.translations.filter(language_code=lang).first()
        is_fallback = False
        if not trans and allow_fallback:
            trans = ev.translations.filter(language_code=LANGUAGE_MARATHI).first()
            is_fallback = True

        if not trans:
            continue

        events_data.append({
            'id': str(ev.id),
            'event_type': ev.event_type,
            'event_type_display': ev.get_event_type_display(),
            'status': ev.status,
            'status_display': ev.get_status_display(),
            'title': trans.title if trans else "",
            'agenda': trans.agenda if trans else "",
            'venue': ev.get_venue(lang),
            'start_datetime': ev.start_datetime.isoformat(),
            'end_datetime': ev.end_datetime.isoformat(),
            'requires_registration': ev.requires_registration,
            'registration_instructions': ev.registration_instructions,
            'cancellation_reason': ev.cancellation_reason if ev.status == 'cancelled' else "",
            'cancelled_at': ev.cancelled_at.isoformat() if ev.cancelled_at else None,
            'is_cancellation_alert_active': ev.is_cancellation_alert_active(),
            'language_code': trans.language_code if trans else lang,
            'is_fallback': is_fallback and (lang != LANGUAGE_MARATHI),
        })

    return JsonResponse({
        'language': lang,
        'filter': time_filter,
        'count': len(events_data),
        'results': events_data,
    })


def event_detail_view(request, event_id):
    """
    Public detail view for a specific PanchayatEvent.
    Enforces the disclosure gate: unapproved events return 404 to anonymous users.
    Gracefully falls back to primary Marathi record if translation is missing.
    """
    try:
        event = PanchayatEvent.objects.get(id=event_id)
    except PanchayatEvent.DoesNotExist:
        raise Http404("Event not found.")

    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')
    if not event.is_publicly_visible(allow_archived=allow_archived):
        if request.user.is_anonymous or not (is_super_admin(request.user) or is_operator(request.user)):
            raise Http404("Event not found.")

    lang = request.GET.get('lang', LANGUAGE_MARATHI)
    valid_langs = [c[0] for c in LANGUAGE_CHOICES]
    if lang not in valid_langs:
        lang = LANGUAGE_MARATHI

    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')

    trans = event.translations.filter(language_code=lang).first()
    is_fallback = False
    if not trans and allow_fallback:
        trans = event.translations.filter(language_code=LANGUAGE_MARATHI).first()
        is_fallback = True

    if not trans:
        raise Http404(f"No translation available for language '{lang}'.")

    return JsonResponse({
        'id': str(event.id),
        'event_type': event.event_type,
        'event_type_display': event.get_event_type_display(),
        'status': event.status,
        'status_display': event.get_status_display(),
        'title': trans.title,
        'description': trans.description,
        'agenda': trans.agenda,
        'venue': event.get_venue(lang),
        'start_datetime': event.start_datetime.isoformat(),
        'end_datetime': event.end_datetime.isoformat(),
        'requires_registration': event.requires_registration,
        'registration_instructions': event.registration_instructions,
        'cancellation_reason': event.cancellation_reason if event.status == 'cancelled' else "",
        'cancelled_at': event.cancelled_at.isoformat() if event.cancelled_at else None,
        'is_cancellation_alert_active': event.is_cancellation_alert_active(),
        'language_code': trans.language_code,
        'is_fallback': is_fallback and (lang != LANGUAGE_MARATHI),
        'created_at': event.created_at.isoformat(),
    })
