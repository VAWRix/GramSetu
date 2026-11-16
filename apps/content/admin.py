"""
Django Admin configuration and secure governance workflows for apps.content.

Enforces least-privilege role authorization, separation of duties, content immutability,
and integration with governance workflow services (ADRs 0001, 0002, 0003, and 0006).
"""

from datetime import datetime
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse

from apps.identity.permissions import (
    is_super_admin,
    is_operator,
    can_edit_content,
    can_approve_content,
    can_publish_content,
)
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_ROLLBACK,
)
from apps.governance.services import (
    submit_page_revision,
    approve_page_revision,
    reject_page_revision,
    publish_page_translation,
    withdraw_page_translation,
)
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    EDITORIAL_DRAFT,
    EDITORIAL_SUBMITTED,
    EDITORIAL_APPROVED,
    EDITORIAL_REJECTED,
    STATUS_DRAFT,
    STATUS_SUBMITTED,
    STATUS_APPROVED,
    STATUS_SCHEDULED,
    STATUS_PUBLISHED,
    STATUS_WITHDRAWN,
    STATUS_ARCHIVED,
)


class PageTranslationInline(admin.TabularInline):
    model = PageTranslation
    extra = 0
    fields = ('language_code', 'localized_slug', 'status_badge', 'current_approved_revision', 'updated_at')
    readonly_fields = ('status_badge', 'current_approved_revision', 'updated_at')

    @admin.display(description="Status / स्थिती")
    def status_badge(self, obj):
        if not obj.pk:
            return "-"
        colors = {
            STATUS_PUBLISHED: '#006b52',
            STATUS_SCHEDULED: '#007791',
            STATUS_DRAFT: '#6c757d',
            STATUS_SUBMITTED: '#e67e22',
            STATUS_WITHDRAWN: '#ba2121',
            STATUS_ARCHIVED: '#7f8c8d',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:3px; font-size:12px; font-weight:bold;">{}</span>',
            color,
            obj.get_status_display(),
        )


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('slug', 'is_system_page', 'display_order', 'translation_completeness', 'created_at')
    list_filter = ('is_system_page',)
    search_fields = ('slug',)
    inlines = [PageTranslationInline]

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and obj.is_system_page:
            return False
        return True

    @admin.display(description="Translation Completeness / भाषांतर पूर्णता")
    def translation_completeness(self, obj):
        translations = {t.language_code: t for t in obj.translations.all()}
        badges = []

        # Marathi (Statutory Primary)
        t_mr = translations.get('mr')
        if t_mr:
            badges.append(
                f'<span style="background:#006b52; color:#fff; padding:3px 8px; border-radius:3px; font-size:11px; font-weight:bold;">'
                f'mr: {t_mr.get_status_display()}</span>'
            )
        else:
            badges.append(
                '<span style="background:#f0f0f0; color:#ba2121; padding:3px 8px; border:1px solid #ba2121; border-radius:3px; font-size:11px; font-weight:bold;">'
                'mr: अनुपलब्ध (Missing)</span>'
            )

        # Hindi
        t_hi = translations.get('hi')
        if t_hi:
            badges.append(
                f'<span style="background:#007791; color:#fff; padding:3px 8px; border-radius:3px; font-size:11px; font-weight:bold;">'
                f'hi: {t_hi.get_status_display()}</span>'
            )
        else:
            badges.append(
                '<span style="background:#f0f0f0; color:#666; padding:3px 8px; border:1px solid #ccc; border-radius:3px; font-size:11px;">'
                'hi: अनुपलब्ध (Missing)</span>'
            )

        # English
        t_en = translations.get('en')
        if t_en:
            badges.append(
                f'<span style="background:#3b5998; color:#fff; padding:3px 8px; border-radius:3px; font-size:11px; font-weight:bold;">'
                f'en: {t_en.get_status_display()}</span>'
            )
        else:
            badges.append(
                '<span style="background:#f0f0f0; color:#666; padding:3px 8px; border:1px solid #ccc; border-radius:3px; font-size:11px;">'
                'en: Missing</span>'
            )

        return format_html('&nbsp; '.join(badges))


@admin.register(PageTranslation)
class PageTranslationAdmin(admin.ModelAdmin):
    list_display = (
        'page',
        'language_code',
        'localized_slug',
        'status_badge',
        'current_approved_revision_display',
        'current_publication_event_display',
        'updated_at',
    )
    list_filter = ('language_code', 'status')
    search_fields = ('page__slug', 'localized_slug')
    readonly_fields = (
        'status',
        'current_approved_revision',
        'current_publication_event',
        'created_at',
        'updated_at',
    )
    actions = [
        'publish_translations_action',
        'schedule_translations_action',
        'withdraw_translations_action',
        'create_next_revision_action',
    ]

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and obj.status not in (STATUS_DRAFT, STATUS_WITHDRAWN):
            return False
        return True

    def save_model(self, request, obj, form, change):
        if change:
            # Server-side guard: Prevent altering pointers or lifecycle status via direct POST
            orig = PageTranslation.objects.get(pk=obj.pk)
            obj.status = orig.status
            obj.current_approved_revision = orig.current_approved_revision
            obj.current_publication_event = orig.current_publication_event
        else:
            obj.status = STATUS_DRAFT
            obj.current_approved_revision = None
            obj.current_publication_event = None
        super().save_model(request, obj, form, change)

    @admin.display(description="Status / स्थिती")
    def status_badge(self, obj):
        colors = {
            STATUS_PUBLISHED: '#006b52',
            STATUS_SCHEDULED: '#007791',
            STATUS_DRAFT: '#6c757d',
            STATUS_SUBMITTED: '#e67e22',
            STATUS_WITHDRAWN: '#ba2121',
            STATUS_ARCHIVED: '#7f8c8d',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="background:{}; color:#fff; padding:3px 8px; border-radius:3px; font-size:12px; font-weight:bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Active Approved Revision / सक्रिय मंजूर आवृत्ती")
    def current_approved_revision_display(self, obj):
        if not obj.current_approved_revision:
            return "-"
        return f"Rev #{obj.current_approved_revision.revision_number} ({obj.current_approved_revision.title[:30]})"

    @admin.display(description="Active Publication Event / सक्रिय प्रकाशन घटना")
    def current_publication_event_display(self, obj):
        if not obj.current_publication_event:
            return "-"
        ev = obj.current_publication_event
        return f"{ev.get_event_type_display()} ({ev.effective_from.strftime('%Y-%m-%d %H:%M')})"

    @admin.action(description="Publish selected translations (Immediate) / तत्काळ प्रकाशित करा")
    def publish_translations_action(self, request, queryset):
        if not can_publish_content(request.user):
            raise PermissionDenied("Only Super Administrators can publish content.")

        published_count = 0
        for trans in queryset:
            # Find candidate approved revision
            rev = trans.current_approved_revision
            if not rev:
                rev = trans.revisions.filter(editorial_status=EDITORIAL_APPROVED).order_by('-revision_number').first()

            if not rev:
                messages.error(
                    request,
                    f"Cannot publish '{trans}': no approved revision exists. A revision must be approved before publishing.",
                )
                continue

            try:
                publish_page_translation(trans.id, rev.id, request.user)
                published_count += 1
            except ValidationError as e:
                messages.error(request, f"Failed publishing '{trans}': {e}")

        if published_count:
            messages.success(request, f"Successfully published {published_count} page translation(s).")

    @admin.action(description="Schedule publication for future date / भविष्यातील तारखेसाठी नियोजित करा")
    def schedule_translations_action(self, request, queryset):
        if not can_publish_content(request.user):
            raise PermissionDenied("Only Super Administrators can schedule content publication.")

        if 'apply' in request.POST:
            effective_str = request.POST.get('effective_from', '').strip()
            try:
                # Parse datetime-local string (e.g. '2026-10-25T14:30')
                eff_dt = datetime.fromisoformat(effective_str)
                if timezone.is_naive(eff_dt):
                    eff_dt = timezone.make_aware(eff_dt)
                if eff_dt <= timezone.now():
                    raise ValidationError("Scheduled effective time must be in the future.")
            except (ValueError, ValidationError) as e:
                messages.error(request, f"Invalid scheduled time: {e}")
                return render(
                    request,
                    'admin/governance/action_intermediate.html',
                    {
                        'title': 'Schedule Publication / प्रकाशन नियोजित करा',
                        'description': 'Specify a future timestamp when the approved content will automatically become accessible to citizens.',
                        'items': queryset,
                        'field_type': 'datetime',
                        'input_name': 'effective_from',
                        'input_label': 'Effective Publication Timestamp / प्रभावी प्रकाशन वेळ (YYYY-MM-DD HH:MM):',
                        'help_text': 'Content will automatically become live to citizens the instant this timestamp passes.',
                        'submit_label': 'Confirm Scheduling / वेळापत्रक निश्चित करा',
                        'action_name': 'schedule_translations_action',
                        'cancel_url': reverse('admin:content_pagetranslation_changelist'),
                    },
                )

            scheduled_count = 0
            for trans in queryset:
                rev = trans.current_approved_revision or trans.revisions.filter(editorial_status=EDITORIAL_APPROVED).order_by('-revision_number').first()
                if not rev:
                    messages.error(request, f"Cannot schedule '{trans}': no approved revision exists.")
                    continue
                try:
                    publish_page_translation(trans.id, rev.id, request.user, effective_from=eff_dt)
                    scheduled_count += 1
                except ValidationError as e:
                    messages.error(request, f"Failed scheduling '{trans}': {e}")

            if scheduled_count:
                messages.success(request, f"Successfully scheduled {scheduled_count} translation(s) for {eff_dt.strftime('%Y-%m-%d %H:%M')}.")
            return None

        return render(
            request,
            'admin/governance/action_intermediate.html',
            {
                'title': 'Schedule Publication / प्रकाशन नियोजित करा',
                'description': 'Specify a future timestamp when the approved content will automatically become accessible to citizens.',
                'items': queryset,
                'field_type': 'datetime',
                'input_name': 'effective_from',
                'input_label': 'Effective Publication Timestamp / प्रभावी प्रकाशन वेळ (YYYY-MM-DD HH:MM):',
                'help_text': 'Content will automatically become live to citizens the instant this timestamp passes.',
                'submit_label': 'Confirm Scheduling / वेळापत्रक निश्चित करा',
                'action_name': 'schedule_translations_action',
                'cancel_url': reverse('admin:content_pagetranslation_changelist'),
            },
        )

    @admin.action(description="Withdraw from public view / सार्वजनिक दर्शनातून मागे घ्या")
    def withdraw_translations_action(self, request, queryset):
        if not can_publish_content(request.user):
            raise PermissionDenied("Only Super Administrators can withdraw content.")

        if 'apply' in request.POST:
            justification = request.POST.get('justification', '').strip()
            if len(justification) < 10:
                messages.error(request, "Withdrawal justification must be at least 10 non-whitespace characters.")
                return render(
                    request,
                    'admin/governance/action_intermediate.html',
                    {
                        'title': 'Withdraw Page Translations / माहिती मागे घ्या',
                        'description': 'Withdrawing immediately severs citizen access (returns 404) and records an immutable administrative event.',
                        'items': queryset,
                        'field_type': 'textarea',
                        'input_name': 'justification',
                        'input_label': 'Mandatory Administrative Justification / कारण (किमान १० अक्षरे):',
                        'placeholder': 'Explain the statutory reason for withdrawing this public information...',
                        'help_text': 'This justification is recorded permanently in the append-only governance ledger.',
                        'submit_label': 'Execute Withdrawal / माहिती मागे घ्या',
                        'action_name': 'withdraw_translations_action',
                        'cancel_url': reverse('admin:content_pagetranslation_changelist'),
                    },
                )

            withdrawn_count = 0
            for trans in queryset:
                try:
                    withdraw_page_translation(trans.id, request.user, justification=justification)
                    withdrawn_count += 1
                except ValidationError as e:
                    messages.error(request, f"Failed withdrawing '{trans}': {e}")

            if withdrawn_count:
                messages.success(request, f"Successfully withdrawn {withdrawn_count} page translation(s).")
            return None

        return render(
            request,
            'admin/governance/action_intermediate.html',
            {
                'title': 'Withdraw Page Translations / माहिती मागे घ्या',
                'description': 'Withdrawing immediately severs citizen access (returns 404) and records an immutable administrative event.',
                'items': queryset,
                'field_type': 'textarea',
                'input_name': 'justification',
                'input_label': 'Mandatory Administrative Justification / कारण (किमान १० अक्षरे):',
                'placeholder': 'Explain the statutory reason for withdrawing this public information...',
                'help_text': 'This justification is recorded permanently in the append-only governance ledger.',
                'submit_label': 'Execute Withdrawal / माहिती मागे घ्या',
                'action_name': 'withdraw_translations_action',
                'cancel_url': reverse('admin:content_pagetranslation_changelist'),
            },
        )

    @admin.action(description="Branch new draft revision / नवीन मसुदा आवृत्ती तयार करा")
    def create_next_revision_action(self, request, queryset):
        if not can_edit_content(request.user):
            raise PermissionDenied("Only authorized editors can create content revisions.")

        created_count = 0
        for trans in queryset:
            new_rev = trans.create_next_revision(author=request.user)
            created_count += 1
            messages.success(request, f"Created new draft Revision #{new_rev.revision_number} for '{trans}'.")


@admin.register(PageRevision)
class PageRevisionAdmin(admin.ModelAdmin):
    list_display = (
        'translation',
        'revision_number',
        'title',
        'editorial_status_badge',
        'content_hash_short',
        'created_by',
        'created_at',
    )
    list_filter = ('editorial_status', 'translation__language_code')
    search_fields = ('title', 'content_hash', 'translation__page__slug')
    readonly_fields = ('content_hash', 'created_by', 'created_at', 'submitted_at')
    actions = [
        'submit_for_review_action',
        'approve_revisions_action',
        'reject_revisions_action',
        'rollback_to_this_revision_action',
    ]

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        if not can_edit_content(request.user):
            return False
        # Locked if already submitted, approved, or rejected
        if obj and obj.editorial_status != EDITORIAL_DRAFT:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if not can_edit_content(request.user):
            return False
        if obj and obj.editorial_status != EDITORIAL_DRAFT:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.editorial_status != EDITORIAL_DRAFT:
            for f in ('translation', 'revision_number', 'title', 'summary', 'body_markdown', 'editorial_status'):
                if f not in readonly:
                    readonly.append(f)
        else:
            if 'editorial_status' not in readonly:
                readonly.append('editorial_status')
        return readonly

    def save_model(self, request, obj, form, change):
        if not change:
            # Brand new revision created via admin
            obj.created_by = request.user
            obj.editorial_status = EDITORIAL_DRAFT
            if not obj.revision_number or obj.revision_number == 0:
                latest = PageRevision.objects.filter(translation=obj.translation).order_by('-revision_number').first()
                obj.revision_number = (latest.revision_number + 1) if latest else 1
            obj.content_hash = obj.calculate_hash()
        else:
            if obj.editorial_status != EDITORIAL_DRAFT:
                raise ValidationError("Submitted and reviewed revisions are strictly immutable.")
            obj.content_hash = obj.calculate_hash()
        super().save_model(request, obj, form, change)

    @admin.display(description="Editorial Status / मसुदा स्थिती")
    def editorial_status_badge(self, obj):
        colors = {
            EDITORIAL_DRAFT: '#6c757d',
            EDITORIAL_SUBMITTED: '#e67e22',
            EDITORIAL_APPROVED: '#006b52',
            EDITORIAL_REJECTED: '#ba2121',
        }
        color = colors.get(obj.editorial_status, '#333')
        return format_html(
            '<span style="background:{}; color:#fff; padding:3px 8px; border-radius:3px; font-size:12px; font-weight:bold;">{}</span>',
            color,
            obj.get_editorial_status_display(),
        )

    @admin.display(description="Content Hash / हॅश")
    def content_hash_short(self, obj):
        if not obj.content_hash:
            return "-"
        return f"{obj.content_hash[:10]}...{obj.content_hash[-6:]}"

    @admin.action(description="Submit selected revisions for review / पुनरावलोकनासाठी सादर करा")
    def submit_for_review_action(self, request, queryset):
        if not can_edit_content(request.user):
            raise PermissionDenied("Only authorized editors can submit revisions for review.")

        submitted_count = 0
        for rev in queryset:
            if rev.editorial_status != EDITORIAL_DRAFT:
                messages.warning(
                    request,
                    f"Revision #{rev.revision_number} of '{rev.translation}' is already in '{rev.editorial_status}' state. Skipped.",
                )
                continue
            try:
                submit_page_revision(rev.id, request.user)
                submitted_count += 1
            except ValidationError as e:
                messages.error(request, f"Failed submitting Revision #{rev.revision_number}: {e}")

        if submitted_count:
            messages.success(request, f"Successfully submitted {submitted_count} revision(s) for review.")

    @admin.action(description="Approve selected submitted revisions / पुनरावलोकन मंजूर करा")
    def approve_revisions_action(self, request, queryset):
        if not can_approve_content(request.user):
            raise PermissionDenied("Only Super Administrators can approve revisions.")

        approved_count = 0
        for rev in queryset:
            if rev.editorial_status != EDITORIAL_SUBMITTED:
                messages.warning(
                    request,
                    f"Revision #{rev.revision_number} of '{rev.translation}' is not in 'submitted' state (current: '{rev.editorial_status}'). Skipped.",
                )
                continue

            # SEPARATION OF DUTIES ENFORCEMENT
            if rev.created_by_id == request.user.pk:
                messages.error(
                    request,
                    f"Separation of duties violation: You cannot approve Revision #{rev.revision_number} of '{rev.translation}' because you are its author. Another Super Administrator must approve it.",
                )
                continue

            try:
                approve_page_revision(rev.id, request.user, notes="Approved via Django Admin", allow_self_approval=False)
                approved_count += 1
            except ValidationError as e:
                messages.error(request, f"Approval failed for Revision #{rev.revision_number}: {e}")

        if approved_count:
            messages.success(request, f"Successfully approved {approved_count} revision(s).")

    @admin.action(description="Reject selected submitted revisions / पुनरावलोकन नाकारा")
    def reject_revisions_action(self, request, queryset):
        if not can_approve_content(request.user):
            raise PermissionDenied("Only Super Administrators can reject revisions.")

        if 'apply' in request.POST:
            reason = request.POST.get('rejection_reason', '').strip()
            if len(reason) < 10:
                messages.error(request, "Rejection reason must be at least 10 non-whitespace characters.")
                return render(
                    request,
                    'admin/governance/action_intermediate.html',
                    {
                        'title': 'Reject Submitted Revisions / पुनरावलोकन नाकारा',
                        'description': 'Mandatory administrative feedback explaining what corrections are required by the author.',
                        'items': queryset,
                        'field_type': 'textarea',
                        'input_name': 'rejection_reason',
                        'input_label': 'Mandatory Rejection Rationale / नकार कारण (किमान १० अक्षरे):',
                        'placeholder': 'Explain why this revision is rejected and what must be corrected...',
                        'help_text': 'This feedback is stored permanently in the RejectionRecord audit ledger.',
                        'submit_label': 'Confirm Rejection / नकार नोंदवा',
                        'action_name': 'reject_revisions_action',
                        'cancel_url': reverse('admin:content_pagerevision_changelist'),
                    },
                )

            rejected_count = 0
            for rev in queryset:
                if rev.editorial_status != EDITORIAL_SUBMITTED:
                    messages.warning(request, f"Revision #{rev.revision_number} is not submitted (current: '{rev.editorial_status}'). Skipped.")
                    continue
                try:
                    reject_page_revision(rev.id, request.user, reason)
                    rejected_count += 1
                except ValidationError as e:
                    messages.error(request, f"Rejection failed for Revision #{rev.revision_number}: {e}")

            if rejected_count:
                messages.success(request, f"Successfully rejected {rejected_count} revision(s).")
            return None

        return render(
            request,
            'admin/governance/action_intermediate.html',
            {
                'title': 'Reject Submitted Revisions / पुनरावलोकन नाकारा',
                'description': 'Mandatory administrative feedback explaining what corrections are required by the author.',
                'items': queryset,
                'field_type': 'textarea',
                'input_name': 'rejection_reason',
                'input_label': 'Mandatory Rejection Rationale / नकार कारण (किमान १० अक्षरे):',
                'placeholder': 'Explain why this revision is rejected and what must be corrected...',
                'help_text': 'This feedback is stored permanently in the RejectionRecord audit ledger.',
                'submit_label': 'Confirm Rejection / नकार नोंदवा',
                'action_name': 'reject_revisions_action',
                'cancel_url': reverse('admin:content_pagerevision_changelist'),
            },
        )

    @admin.action(description="Rollback translation to this approved revision / या आवृत्तीवर रोलबॅक करा")
    def rollback_to_this_revision_action(self, request, queryset):
        if not can_publish_content(request.user):
            raise PermissionDenied("Only Super Administrators can execute rollbacks.")

        if 'apply' in request.POST:
            justification = request.POST.get('justification', '').strip()
            if len(justification) < 10:
                messages.error(request, "Rollback justification must be at least 10 non-whitespace characters.")
                return render(
                    request,
                    'admin/governance/action_intermediate.html',
                    {
                        'title': 'Rollback Page Translation / आवृत्ती पूर्ववत करा (Rollback)',
                        'description': 'Rolls back the public page translation to the selected approved revision. Creates an append-only rollback event.',
                        'items': queryset,
                        'field_type': 'textarea',
                        'input_name': 'justification',
                        'input_label': 'Mandatory Rollback Justification / रोलबॅकचे कारण (किमान १० अक्षरे):',
                        'placeholder': 'Explain the statutory reason for reinstating this earlier revision...',
                        'help_text': 'This justification is recorded permanently in the PublicationEvent audit ledger.',
                        'submit_label': 'Execute Rollback / रोलबॅक करा',
                        'action_name': 'rollback_to_this_revision_action',
                        'cancel_url': reverse('admin:content_pagerevision_changelist'),
                    },
                )

            rollback_count = 0
            for rev in queryset:
                if rev.editorial_status != EDITORIAL_APPROVED:
                    messages.error(request, f"Revision #{rev.revision_number} cannot be rolled back to because it is not approved.")
                    continue
                try:
                    publish_page_translation(rev.translation_id, rev.id, request.user, justification=justification)
                    rollback_count += 1
                except ValidationError as e:
                    messages.error(request, f"Rollback failed for Revision #{rev.revision_number}: {e}")

            if rollback_count:
                messages.success(request, f"Successfully rolled back {rollback_count} translation(s).")
            return None

        return render(
            request,
            'admin/governance/action_intermediate.html',
            {
                'title': 'Rollback Page Translation / आवृत्ती पूर्ववत करा (Rollback)',
                'description': 'Rolls back the public page translation to the selected approved revision. Creates an append-only rollback event.',
                'items': queryset,
                'field_type': 'textarea',
                'input_name': 'justification',
                'input_label': 'Mandatory Rollback Justification / रोलबॅकचे कारण (किमान १० अक्षरे):',
                'placeholder': 'Explain the statutory reason for reinstating this earlier revision...',
                'help_text': 'This justification is recorded permanently in the PublicationEvent audit ledger.',
                'submit_label': 'Execute Rollback / रोलबॅक करा',
                'action_name': 'rollback_to_this_revision_action',
                'cancel_url': reverse('admin:content_pagerevision_changelist'),
            },
        )
