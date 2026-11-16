"""
Comprehensive domain, governance, view, and admin tests for apps.events.

Verifies:
- PanchayatEvent model constraints, UUIDv7 PK, end-after-start date validation, event types, and cancellation tracking.
- EventTranslation multilingual uniqueness, explicit translation records, and no silent language fallback.
- Separation of duties in event publication approval (authors cannot approve their own events).
- Governance publishing workflows: submit, approve, reject, cancel, and archive.
- Public views and disclosure gate (draft events strictly return 404 to anonymous citizens).
- Django Admin interface permissions, retention protections, and separation of duties enforcement.
"""

from datetime import timedelta
import hashlib
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.identity.models import (
    User,
    RoleAssignment,
    ROLE_SUPER_ADMIN,
    ROLE_OPERATOR,
)
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
    EVENT_UPDATE_PUBLISH,
    EVENT_WITHDRAWAL,
    EVENT_SCHEDULED_PUBLISH,
    EVENT_ARCHIVAL,
)
from apps.governance.services import (
    submit_event_for_approval,
    approve_and_publish_event,
    reject_event,
    cancel_event,
    archive_concluded_events,
    mark_concluded_events_completed,
    archive_event,
    withdraw_event,
)
from apps.events.models import (
    PanchayatEvent,
    EventTranslation,
    EVENT_GRAM_SABHA,
    EVENT_WARD_MEETING,
    EVENT_HEALTH_CAMP,
    EVENT_HEARING,
    EVENT_CULTURAL,
    LANGUAGE_MARATHI,
    LANGUAGE_HINDI,
    LANGUAGE_ENGLISH,
    STATUS_DRAFT,
    STATUS_PENDING_APPROVAL,
    STATUS_APPROVED,
    STATUS_PUBLISHED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_ARCHIVED,
)
from apps.events.admin import (
    PanchayatEventAdmin,
    RejectEventActionForm,
    CancelEventActionForm,
    WithdrawEventActionForm,
)


class EventBaseTestCase(TestCase):
    """
    Base fixture establishing administrative and citizen users.
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='admin@gramsetu.in',
            full_name='Super Administrator',
            password='AdminPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.super_admin,
            role=ROLE_SUPER_ADMIN,
            assigned_by=self.super_admin,
        )

        self.operator = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Gram Panchayat Operator',
            password='OperatorPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.operator,
            role=ROLE_OPERATOR,
            assigned_by=self.super_admin,
        )

        self.second_admin = User.objects.create_user(
            email='second_admin@gramsetu.in',
            full_name='Second Administrator',
            password='AdminPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.second_admin,
            role=ROLE_SUPER_ADMIN,
            assigned_by=self.super_admin,
        )

        self.citizen = User.objects.create_user(
            email='citizen@gramsetu.in',
            full_name='Ordinary Citizen',
            password='CitizenPassword123!',
            is_staff=False,
        )


class PanchayatEventModelTests(EventBaseTestCase):
    """
    Tests for PanchayatEvent model constraints, end-after-start rules, and immutability.
    """

    def test_event_creation_valid(self):
        start = timezone.now() + timedelta(days=2)
        end = start + timedelta(hours=3)

        event = PanchayatEvent.objects.create(
            event_type=EVENT_GRAM_SABHA,
            start_datetime=start,
            end_datetime=end,
            venue_mr='ग्रामपंचायत सभागृह',
            venue_en='Gram Panchayat Hall',
            created_by=self.operator,
        )
        self.assertIsNotNone(event.id)
        self.assertEqual(event.event_type, EVENT_GRAM_SABHA)
        self.assertEqual(event.status, STATUS_DRAFT)
        self.assertFalse(event.is_published)

    def test_end_before_start_datetime_fails_check(self):
        start = timezone.now() + timedelta(days=2)
        end = start - timedelta(hours=1)  # Invalid: end before start

        event = PanchayatEvent(
            event_type=EVENT_GRAM_SABHA,
            start_datetime=start,
            end_datetime=end,
            venue_mr='ग्रामपंचायत सभागृह',
            created_by=self.operator,
        )
        with self.assertRaises(ValidationError) as ctx:
            event.clean()
        self.assertIn("greater than or equal to start datetime", str(ctx.exception))

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                event.save()

    def test_invalid_event_type_fails_check(self):
        start = timezone.now() + timedelta(days=1)
        end = start + timedelta(hours=2)

        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                PanchayatEvent.objects.create(
                    event_type='invalid_type',
                    start_datetime=start,
                    end_datetime=end,
                    venue_mr='सभागृह',
                    created_by=self.operator,
                )

    def test_cancellation_reason_mandatory_for_cancelled_status(self):
        start = timezone.now() + timedelta(days=1)
        end = start + timedelta(hours=2)

        event = PanchayatEvent(
            event_type=EVENT_WARD_MEETING,
            start_datetime=start,
            end_datetime=end,
            venue_mr='शाळा परिसर',
            status=STATUS_CANCELLED,
            cancellation_reason='',  # Missing reason
            created_by=self.operator,
        )
        with self.assertRaises(ValidationError) as ctx:
            event.clean()
        self.assertIn("cancellation reason", str(ctx.exception).lower())

    def test_cannot_delete_published_or_completed_event(self):
        start = timezone.now() + timedelta(days=1)
        end = start + timedelta(hours=2)

        event = PanchayatEvent.objects.create(
            event_type=EVENT_HEALTH_CAMP,
            start_datetime=start,
            end_datetime=end,
            venue_mr='प्राथमिक आरोग्य केंद्र',
            is_published=True,
            status=STATUS_PUBLISHED,
            created_by=self.operator,
        )
        with self.assertRaises(ValidationError) as ctx:
            event.delete()
        self.assertIn("cannot be deleted", str(ctx.exception))


class EventTranslationModelTests(EventBaseTestCase):
    """
    Tests for EventTranslation model (multilingual explicit entity, language constraints).
    """

    def setUp(self):
        super().setUp()
        start = timezone.now() + timedelta(days=3)
        end = start + timedelta(hours=2)
        self.event = PanchayatEvent.objects.create(
            event_type=EVENT_GRAM_SABHA,
            start_datetime=start,
            end_datetime=end,
            venue_mr='ग्रामपंचायत कार्यालय',
            created_by=self.operator,
        )

    def test_multilingual_translations_unique_per_language(self):
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_MARATHI,
            title='विशेष ग्रामसभा बैठक',
            agenda='वार्षिक विकास आराखडा मंजुरी',
        )
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_ENGLISH,
            title='Special Gram Sabha Meeting',
            agenda='Approval of Annual Development Plan',
        )

        # Duplicate language for same event must fail
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EventTranslation.objects.create(
                    event=self.event,
                    language_code=LANGUAGE_MARATHI,
                    title='Duplicate Marathi Translation',
                )

    def test_invalid_language_code_fails_check(self):
        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                EventTranslation.objects.create(
                    event=self.event,
                    language_code='de',
                    title='German Title',
                )

    def test_no_silent_language_fallback(self):
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_MARATHI,
            title='मराठी शीर्षक',
        )
        # Requesting English title when no English translation exists returns empty string (no silent fallback)
        self.assertEqual(self.event.get_title(LANGUAGE_MARATHI), 'मराठी शीर्षक')
        self.assertEqual(self.event.get_title(LANGUAGE_ENGLISH), '')


class EventGovernanceServicesTests(EventBaseTestCase):
    """
    Tests for governance workflow services (submit, approve, separation of duties, reject, cancel, archive).
    """

    def setUp(self):
        super().setUp()
        start = timezone.now() + timedelta(days=5)
        end = start + timedelta(hours=3)
        self.event = PanchayatEvent.objects.create(
            event_type=EVENT_GRAM_SABHA,
            start_datetime=start,
            end_datetime=end,
            venue_mr='ग्रामपंचायत सभागृह',
            venue_en='Panchayat Office Hall',
            created_by=self.operator,
            status=STATUS_DRAFT,
        )

    def test_submit_without_marathi_translation_fails(self):
        # Event has no translations yet
        with self.assertRaises(ValidationError) as ctx:
            submit_event_for_approval(self.event.id, self.operator)
        self.assertIn("Marathi translation (mr) is mandatory", str(ctx.exception))

    def test_submit_for_approval_success(self):
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_MARATHI,
            title='ग्रामसभा बैठक',
            agenda='जलजीवन मिशन आढावा',
        )
        ev = submit_event_for_approval(self.event.id, self.operator)
        self.assertEqual(ev.status, STATUS_PENDING_APPROVAL)

    def test_approve_and_publish_separation_of_duties_enforcement(self):
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_MARATHI,
            title='ग्रामसभा बैठक',
            agenda='विषय पत्रिका',
        )
        submit_event_for_approval(self.event.id, self.operator)

        # Author cannot approve their own event
        with self.assertRaises(ValidationError) as ctx:
            approve_and_publish_event(
                self.event.id,
                approver=self.operator,
                notes="Self-approval attempt",
                allow_self_approval=False,
            )
        self.assertIn("Separation of duties violation", str(ctx.exception))

        # Distinct Super Admin can approve
        ev, approval, pub_event = approve_and_publish_event(
            self.event.id,
            approver=self.super_admin,
            notes="Formal statutory approval by Sarpanch",
        )
        self.assertEqual(ev.status, STATUS_PUBLISHED)
        self.assertTrue(ev.is_published)
        self.assertIsNotNone(approval)
        self.assertEqual(approval.target_content_type, 'panchayatevent')
        self.assertEqual(approval.approved_by, self.super_admin)
        self.assertEqual(pub_event.event_type, EVENT_INITIAL_PUBLISH)

    def test_reject_event(self):
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_MARATHI,
            title='बैठक',
        )
        submit_event_for_approval(self.event.id, self.operator)

        # Reason < 10 chars fails
        with self.assertRaises(ValidationError):
            reject_event(self.event.id, self.super_admin, "Too short")

        ev, rejection = reject_event(
            self.event.id,
            self.super_admin,
            "Agenda is incomplete; specify quorum requirements.",
        )
        self.assertEqual(ev.status, STATUS_DRAFT)
        self.assertEqual(rejection.target_content_type, 'panchayatevent')
        self.assertIn("Agenda is incomplete", rejection.rejection_reason)

    def test_cancel_event_statutory_tracking(self):
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_MARATHI,
            title='आरोग्य शिबिर',
        )
        approve_and_publish_event(self.event.id, self.super_admin, allow_self_approval=True)

        # Cancellation reason < 10 chars fails
        with self.assertRaises(ValidationError):
            cancel_event(self.event.id, self.super_admin, "Short")

        ev, pub_event = cancel_event(
            self.event.id,
            self.super_admin,
            "Postponed due to heavy rainfall red alert issued by IMD.",
        )
        self.assertEqual(ev.status, STATUS_CANCELLED)
        self.assertIn("heavy rainfall", ev.cancellation_reason)
        self.assertEqual(pub_event.event_type, EVENT_WITHDRAWAL)

    def test_mark_concluded_events_completed(self):
        past_start = timezone.now() - timedelta(days=2)
        past_end = past_start + timedelta(hours=2)

        past_event = PanchayatEvent.objects.create(
            event_type=EVENT_HEARING,
            start_datetime=past_start,
            end_datetime=past_end,
            venue_mr='कार्यालय',
            status=STATUS_PUBLISHED,
            is_published=True,
            created_by=self.operator,
        )

        count = mark_concluded_events_completed()
        self.assertGreaterEqual(count, 1)

        past_event.refresh_from_db()
        self.assertEqual(past_event.status, STATUS_COMPLETED)

    def test_archive_concluded_events(self):
        aged_start = timezone.now() - timedelta(days=200)
        aged_end = aged_start + timedelta(hours=2)

        aged_event = PanchayatEvent.objects.create(
            event_type=EVENT_HEARING,
            start_datetime=aged_start,
            end_datetime=aged_end,
            venue_mr='कार्यालय',
            status=STATUS_COMPLETED,
            is_published=True,
            created_by=self.operator,
        )

        count = archive_concluded_events(older_than_days=180)
        self.assertGreaterEqual(count, 1)

        aged_event.refresh_from_db()
        self.assertEqual(aged_event.status, STATUS_ARCHIVED)

    def test_archive_event(self):
        past_start = timezone.now() - timedelta(days=2)
        past_end = past_start + timedelta(hours=2)
        completed_event = PanchayatEvent.objects.create(
            event_type=EVENT_HEARING,
            start_datetime=past_start,
            end_datetime=past_end,
            venue_mr='कार्यालय',
            status=STATUS_COMPLETED,
            is_published=True,
            created_by=self.operator,
        )

        ev, pub = archive_event(completed_event.id, self.super_admin, "Statutory archival after 6 months")
        self.assertEqual(ev.status, STATUS_ARCHIVED)
        self.assertEqual(pub.event_type, EVENT_ARCHIVAL)

        # Trying to archive a draft event fails
        draft_event = PanchayatEvent.objects.create(
            event_type=EVENT_HEARING,
            start_datetime=past_start,
            end_datetime=past_end,
            venue_mr='कार्यालय',
            status=STATUS_DRAFT,
            created_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            archive_event(draft_event.id, self.super_admin)

    def test_withdraw_event(self):
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_MARATHI,
            title='ग्रामसभा बैठक',
        )
        ev, _, _ = approve_and_publish_event(self.event.id, self.super_admin, allow_self_approval=True)
        self.assertTrue(ev.is_published)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_published)

        # Withdrawal with short reason fails
        with self.assertRaises(ValidationError):
            withdraw_event(self.event.id, self.super_admin, "Short")

        ev, pub = withdraw_event(
            self.event.id,
            self.super_admin,
            "Withdrawn due to administrative scheduling conflict with Zilla Parishad."
        )
        self.assertFalse(ev.is_published)
        self.assertEqual(pub.event_type, EVENT_WITHDRAWAL)

        # Public detail view returns 404 for withdrawn event
        url = reverse('events:event_detail', args=[self.event.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_scheduled_event_publication(self):
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_MARATHI,
            title='ग्रामसभा बैठक',
        )
        future_effective = timezone.now() + timedelta(days=1)
        ev, approval, pub_event = approve_and_publish_event(
            self.event.id,
            approver=self.super_admin,
            effective_from=future_effective,
            notes="Approved with future embargo",
        )
        self.assertEqual(pub_event.event_type, EVENT_SCHEDULED_PUBLISH)
        self.assertEqual(pub_event.scheduled_for, future_effective)


class EventPublicViewsTests(EventBaseTestCase):
    """
    Tests for public event listing and detail endpoints.
    """

    def setUp(self):
        super().setUp()
        start = timezone.now() + timedelta(days=4)
        end = start + timedelta(hours=3)
        self.published_event = PanchayatEvent.objects.create(
            event_type=EVENT_GRAM_SABHA,
            start_datetime=start,
            end_datetime=end,
            venue_mr='ग्रामपंचायत सभागृह',
            venue_en='Gram Panchayat Hall',
            status=STATUS_PUBLISHED,
            is_published=True,
            requires_registration=True,
            registration_instructions='Bring Aadhaar Card.',
            created_by=self.operator,
        )
        EventTranslation.objects.create(
            event=self.published_event,
            language_code=LANGUAGE_MARATHI,
            title='वार्षिक ग्रामसभा',
            agenda='विकास कामे',
        )
        EventTranslation.objects.create(
            event=self.published_event,
            language_code=LANGUAGE_ENGLISH,
            title='Annual Gram Sabha',
            agenda='Development works',
        )

        # Unapproved draft event
        self.draft_event = PanchayatEvent.objects.create(
            event_type=EVENT_WARD_MEETING,
            start_datetime=start,
            end_datetime=end,
            venue_mr='वॉर्ड ३',
            status=STATUS_DRAFT,
            is_published=False,
            created_by=self.operator,
        )
        EventTranslation.objects.create(
            event=self.draft_event,
            language_code=LANGUAGE_MARATHI,
            title='Draft वॉर्ड सभा',
        )

    def test_public_event_list_excludes_draft_events(self):
        url = reverse('events:event_list')
        response = self.client.get(url, {'lang': 'mr'})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        ids = [ev['id'] for ev in data['results']]
        self.assertIn(str(self.published_event.id), ids)
        self.assertNotIn(str(self.draft_event.id), ids)

    def test_public_event_detail_published_event(self):
        url = reverse('events:event_detail', args=[self.published_event.id])
        response = self.client.get(url, {'lang': 'en'})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data['title'], 'Annual Gram Sabha')
        self.assertEqual(data['venue'], 'Gram Panchayat Hall')
        self.assertTrue(data['requires_registration'])

    def test_anonymous_citizen_gets_404_for_draft_event(self):
        url = reverse('events:event_detail', args=[self.draft_event.id])
        response = self.client.get(url)
        # Unapproved events must strictly return 404 to anonymous citizens
        self.assertEqual(response.status_code, 404)

    def test_authenticated_staff_can_preview_draft_event(self):
        self.client.force_login(self.operator)
        url = reverse('events:event_detail', args=[self.draft_event.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Draft वॉर्ड सभा')


class EventAdminTests(EventBaseTestCase):
    """
    Tests for Django Admin access control, creation, and separation of duties actions.
    """

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.event_admin = PanchayatEventAdmin(PanchayatEvent, self.site)

        start = timezone.now() + timedelta(days=2)
        end = start + timedelta(hours=2)
        self.event = PanchayatEvent.objects.create(
            event_type=EVENT_GRAM_SABHA,
            start_datetime=start,
            end_datetime=end,
            venue_mr='सभागृह',
            created_by=self.super_admin,  # Created by Super Admin
            status=STATUS_PENDING_APPROVAL,
        )
        EventTranslation.objects.create(
            event=self.event,
            language_code=LANGUAGE_MARATHI,
            title='सभा',
        )

    def test_operator_cannot_delete_event(self):
        request = self.factory.get('/admin/')
        request.user = self.operator
        self.assertFalse(self.event_admin.has_delete_permission(request, self.event))

    def test_admin_approve_and_publish_action_anti_self_approval(self):
        url = reverse('admin:events_panchayatevent_changelist')

        # Admin action must refuse self-approval when requested by the author
        self.client.force_login(self.super_admin)
        response = self.client.post(
            url,
            {
                'action': 'approve_and_publish_action',
                '_selected_action': [str(self.event.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, STATUS_PENDING_APPROVAL)
        self.assertFalse(self.event.is_published)

        # Distinct Super Admin can approve
        self.client.force_login(self.second_admin)
        response = self.client.post(
            url,
            {
                'action': 'approve_and_publish_action',
                '_selected_action': [str(self.event.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, STATUS_PUBLISHED)
        self.assertTrue(self.event.is_published)

    def test_admin_action_forms_validation(self):
        # Reject form min 10 chars
        f_invalid = RejectEventActionForm(data={'rejection_reason': 'Short'})
        self.assertFalse(f_invalid.is_valid())
        self.assertIn('rejection_reason', f_invalid.errors)

        f_valid = RejectEventActionForm(data={'rejection_reason': 'Agenda is missing quorum info.'})
        self.assertTrue(f_valid.is_valid())

        # Cancel form min 10 chars
        c_invalid = CancelEventActionForm(data={'cancellation_reason': 'Bad'})
        self.assertFalse(c_invalid.is_valid())
        self.assertIn('cancellation_reason', c_invalid.errors)

        c_valid = CancelEventActionForm(data={'cancellation_reason': 'Cancelled due to statutory election code.'})
        self.assertTrue(c_valid.is_valid())

        # Withdraw form min 10 chars
        w_invalid = WithdrawEventActionForm(data={'justification': 'Bad'})
        self.assertFalse(w_invalid.is_valid())
        self.assertIn('justification', w_invalid.errors)

        w_valid = WithdrawEventActionForm(data={'justification': 'Withdrawn due to administrative scheduling conflict.'})
        self.assertTrue(w_valid.is_valid())

    def test_admin_withdraw_action(self):
        url = reverse('admin:events_panchayatevent_changelist')
        self.client.force_login(self.second_admin)

        # First approve the event
        self.client.post(
            url,
            {
                'action': 'approve_and_publish_action',
                '_selected_action': [str(self.event.id)],
            },
            follow=True,
        )
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_published)

        # Execute withdraw action
        response = self.client.post(
            url,
            {
                'action': 'withdraw_event_action',
                'apply': 'yes',
                'justification': 'Withdrawn due to administrative rescheduling by Sarpanch.',
                '_selected_action': [str(self.event.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_published)


class EventFilterAndArchivalTests(EventBaseTestCase):
    """
    Tests for upcoming vs past filters, strict language filters, and archival visibility.
    """

    def setUp(self):
        super().setUp()
        now = timezone.now()

        # Upcoming event
        self.upcoming_event = PanchayatEvent.objects.create(
            event_type=EVENT_GRAM_SABHA,
            start_datetime=now + timedelta(days=5),
            end_datetime=now + timedelta(days=5, hours=3),
            venue_mr='सभागृह १',
            status=STATUS_PUBLISHED,
            is_published=True,
            created_by=self.operator,
        )
        EventTranslation.objects.create(
            event=self.upcoming_event,
            language_code=LANGUAGE_MARATHI,
            title='आगामी ग्रामसभा',
        )
        EventTranslation.objects.create(
            event=self.upcoming_event,
            language_code=LANGUAGE_ENGLISH,
            title='Upcoming Gram Sabha',
        )

        # Past event
        self.past_event = PanchayatEvent.objects.create(
            event_type=EVENT_WARD_MEETING,
            start_datetime=now - timedelta(days=5),
            end_datetime=now - timedelta(days=5, hours=-2),
            venue_mr='सभागृह २',
            status=STATUS_COMPLETED,
            is_published=True,
            created_by=self.operator,
        )
        EventTranslation.objects.create(
            event=self.past_event,
            language_code=LANGUAGE_MARATHI,
            title='मागील वॉर्ड सभा',
        )

    def test_upcoming_and_past_filters(self):
        url = reverse('events:event_list')

        # Upcoming filter
        resp_up = self.client.get(url, {'filter': 'upcoming', 'lang': 'mr'})
        self.assertEqual(resp_up.status_code, 200)
        up_ids = [ev['id'] for ev in resp_up.json()['results']]
        self.assertIn(str(self.upcoming_event.id), up_ids)
        self.assertNotIn(str(self.past_event.id), up_ids)

        # Past filter
        resp_past = self.client.get(url, {'filter': 'past', 'lang': 'mr'})
        self.assertEqual(resp_past.status_code, 200)
        past_ids = [ev['id'] for ev in resp_past.json()['results']]
        self.assertIn(str(self.past_event.id), past_ids)
        self.assertNotIn(str(self.upcoming_event.id), past_ids)

    def test_strict_language_filtering(self):
        url = reverse('events:event_list')
        # Past event only has Marathi translation
        resp_en = self.client.get(url, {'filter': 'past', 'lang': 'en'})
        self.assertEqual(resp_en.status_code, 200)
        self.assertEqual(resp_en.json()['count'], 0)

    def test_archival_visibility_logic(self):
        ev = self.upcoming_event
        ev.status = STATUS_ARCHIVED
        ev.save()

        self.assertFalse(ev.is_publicly_visible(allow_archived=False))
        self.assertTrue(ev.is_publicly_visible(allow_archived=True))
