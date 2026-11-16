"""
Django Admin configuration and secure governance workflows for apps.schemes.

Enforces least-privilege role authorization, separation of duties, content immutability,
and integration with governance workflow services (ADRs 0001, 0002, 0003, and 0006).
"""

from datetime import datetime
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import format_html

from apps.identity.permissions import (
    is_super_admin,
    can_edit_content,
    can_approve_content,
    can_publish_content,
)
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
    EVENT_UPDATE_PUBLISH,
    EVENT_SCHEDULED_PUBLISH,
    EVENT_ROLLBACK,
    EVENT_WITHDRAWAL,
)
from apps.governance.services import (
    submit_scheme_revision,
    approve_scheme_revision,
    reject_scheme_revision,
    publish_scheme_translation,
    withdraw_scheme_translation,
    rollback_scheme_translation,
)
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    SchemeRevision,
    LANGUAGE_MARATHI,
    LANGUAGE_HINDI,
    LANGUAGE_ENGLISH,
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


class RejectSchemeActionForm(forms.Form):
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 60}),
        label="Reason for Rejection (नकाराचे कारण)",
        help_text="Mandatory rationale explaining why the scheme revision was rejected (minimum 10 characters).",
        min_length=10,
        required=True,
    )


class WithdrawSchemeActionForm(forms.Form):
    justification = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 60}),
        label="Reason for Administrative Withdrawal (मागे घेण्याचे कारण)",
        help_text="Mandatory rationale for withdrawing this scheme translation from public view (minimum 10 characters).",
        min_length=10,
        required=True,
    )


class ScheduleSchemeActionForm(forms.Form):
    effective_from = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        label="Publication Effective Timestamp (प्रकाशन प्रभावी दिनांक व वेळ)",
        help_text="The date and time when the scheme translation will automatically become publicly accessible (must be in the future).",
        required=True,
    )

    def clean_effective_from(self):
        eff = self.cleaned_data['effective_from']
        if eff <= timezone.now():
            raise forms.ValidationError("Scheduled publication time must be in the future.")
        return eff


class SchemeTranslationInline(admin.TabularInline):
    model = SchemeTranslation
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


@admin.register(WelfareScheme)
class WelfareSchemeAdmin(admin.ModelAdmin):
    list_display = (
        'slug',
        'marathi_name_display',
        'scheme_level',
        'target_beneficiary',
        'is_active',
        'translation_completeness',
        'display_order',
        'created_at',
    )
    list_filter = ('scheme_level', 'target_beneficiary', 'is_active')
    search_fields = ('slug', 'translations__revisions__scheme_name')
    filter_horizontal = ('supporting_documents',)
    inlines = [SchemeTranslationInline]

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and obj.translations.filter(status=STATUS_PUBLISHED).exists():
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        ro = ['created_by', 'created_at', 'updated_at']
        return ro

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Marathi Scheme Name / योजनेचे नाव (मराठी)")
    def marathi_name_display(self, obj):
        return obj.get_name(LANGUAGE_MARATHI) or "-"

    @admin.display(description="Translation Completeness / भाषांतर पूर्णता")
    def translation_completeness(self, obj):
        trans_langs = set(obj.translations.values_list('language_code', flat=True))
        badges = []
        for code, label in [('mr', 'MR'), ('hi', 'HI'), ('en', 'EN')]:
            if code in trans_langs:
                badges.append(f'<span style="color:green; font-weight:bold;">✓ {label}</span>')
            else:
                badges.append(f'<span style="color:#aaa;">✗ {label}</span>')
        return format_html(" | ".join(badges))


@admin.register(SchemeTranslation)
class SchemeTranslationAdmin(admin.ModelAdmin):
    list_display = (
        'scheme',
        'language_code',
        'localized_slug',
        'status_badge',
        'current_approved_revision_display',
        'current_publication_event_display',
        'updated_at',
    )
    list_filter = ('language_code', 'status')
    search_fields = ('scheme__slug', 'localized_slug')
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
            orig = SchemeTranslation.objects.get(pk=obj.pk)
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
        return f"Rev #{obj.current_approved_revision.revision_number} ({obj.current_approved_revision.scheme_name[:30]})"

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
                publish_scheme_translation(trans.id, rev.id, request.user)
                published_count += 1
            except ValidationError as e:
                messages.error(request, f"Failed to publish '{trans}': {e.message}")

        if published_count:
            messages.success(request, f"Successfully published {published_count} scheme translation(s).")

    @admin.action(description="Schedule selected translations / नियोजित प्रकाशन करा")
    def schedule_translations_action(self, request, queryset):
        if not can_publish_content(request.user):
            raise PermissionDenied("Only Super Administrators can schedule publications.")

        if 'apply' in request.POST:
            form = ScheduleSchemeActionForm(request.POST)
            if form.is_valid():
                eff_from = form.cleaned_data['effective_from']
                scheduled_count = 0
                for trans in queryset:
                    rev = trans.current_approved_revision
                    if not rev:
                        rev = trans.revisions.filter(editorial_status=EDITORIAL_APPROVED).order_by('-revision_number').first()

                    if not rev:
                        messages.error(request, f"Cannot schedule '{trans}': no approved revision exists.")
                        continue

                    try:
                        publish_scheme_translation(trans.id, rev.id, request.user, effective_from=eff_from)
                        scheduled_count += 1
                    except ValidationError as e:
                        messages.error(request, f"Failed to schedule '{trans}': {e.message}")

                if scheduled_count:
                    messages.success(request, f"Successfully scheduled {scheduled_count} scheme translation(s) for {eff_from}.")
                return None
        else:
            form = ScheduleSchemeActionForm()

        return render(
            request,
            'governance/schedule_action.html',
            {
                'title': 'Schedule Publication / नियोजित प्रकाशन',
                'queryset': queryset,
                'form': form,
                'action_name': 'schedule_translations_action',
            },
        )

    @admin.action(description="Withdraw selected translations / मागे घ्या (अप्रकाशित करा)")
    def withdraw_translations_action(self, request, queryset):
        if not can_publish_content(request.user):
            raise PermissionDenied("Only Super Administrators can withdraw content.")

        if 'apply' in request.POST:
            form = WithdrawSchemeActionForm(request.POST)
            if form.is_valid():
                justification = form.cleaned_data['justification']
                withdrawn_count = 0
                for trans in queryset:
                    try:
                        withdraw_scheme_translation(trans.id, request.user, justification)
                        withdrawn_count += 1
                    except ValidationError as e:
                        messages.error(request, f"Failed to withdraw '{trans}': {e.message}")

                if withdrawn_count:
                    messages.warning(request, f"Successfully withdrawn {withdrawn_count} scheme translation(s) from public view.")
                return None
        else:
            form = WithdrawSchemeActionForm()

        return render(
            request,
            'governance/withdraw_action.html',
            {
                'title': 'Withdraw Publication / प्रकाशन मागे घ्या',
                'queryset': queryset,
                'form': form,
                'action_name': 'withdraw_translations_action',
            },
        )

    @admin.action(description="Create next draft revision / पुढील मसुदा आवृत्ती तयार करा")
    def create_next_revision_action(self, request, queryset):
        if not can_edit_content(request.user):
            raise PermissionDenied("Only content editors can branch new revisions.")

        branched_count = 0
        for trans in queryset:
            rev = trans.create_next_revision(author=request.user)
            branched_count += 1
        messages.success(request, f"Branched {branched_count} new draft revision(s).")


@admin.register(SchemeRevision)
class SchemeRevisionAdmin(admin.ModelAdmin):
    list_display = (
        'translation',
        'revision_number',
        'scheme_name',
        'editorial_status_badge',
        'content_hash_short',
        'created_by',
        'created_at',
    )
    list_filter = ('editorial_status', 'translation__language_code')
    search_fields = ('scheme_name', 'short_summary', 'translation__scheme__slug')
    readonly_fields = ('content_hash', 'created_by', 'created_at', 'submitted_at')
    actions = [
        'submit_for_review_action',
        'approve_revisions_action',
        'reject_revisions_action',
    ]

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        if not can_edit_content(request.user):
            return False
        if obj and obj.editorial_status != EDITORIAL_DRAFT:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and obj.editorial_status != EDITORIAL_DRAFT:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if obj and obj.editorial_status != EDITORIAL_DRAFT:
            ro.extend([
                'translation',
                'revision_number',
                'scheme_name',
                'short_summary',
                'eligibility_criteria',
                'benefits',
                'required_documents',
                'application_process',
                'editorial_status',
            ])
        return ro

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Status / स्थिती")
    def editorial_status_badge(self, obj):
        colors = {
            EDITORIAL_APPROVED: '#006b52',
            EDITORIAL_SUBMITTED: '#e67e22',
            EDITORIAL_DRAFT: '#6c757d',
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
        return f"{obj.content_hash[:10]}…"

    @admin.action(description="Submit selected revisions for review / पुनरावलोकनासाठी सादर करा")
    def submit_for_review_action(self, request, queryset):
        if not can_edit_content(request.user):
            raise PermissionDenied("Only content editors can submit revisions.")

        submitted_count = 0
        for rev in queryset:
            if rev.editorial_status != EDITORIAL_DRAFT:
                messages.warning(request, f"Revision #{rev.revision_number} of '{rev.translation}' is already '{rev.editorial_status}'.")
                continue
            try:
                submit_scheme_revision(rev.id, request.user)
                submitted_count += 1
            except ValidationError as e:
                messages.error(request, f"Cannot submit revision #{rev.revision_number}: {e.message}")

        if submitted_count:
            messages.success(request, f"Successfully submitted {submitted_count} revision(s) for review.")

    @admin.action(description="Approve selected revisions (Super Admin) / मसुदा मंजूर करा")
    def approve_revisions_action(self, request, queryset):
        if not can_approve_content(request.user):
            raise PermissionDenied("Only Super Administrators can approve content revisions.")

        approved_count = 0
        for rev in queryset:
            if rev.editorial_status != EDITORIAL_SUBMITTED:
                messages.warning(request, f"Cannot approve revision #{rev.revision_number}: status is '{rev.editorial_status}'. Must be 'submitted'.")
                continue

            # Separation of duties: authors cannot approve their own revisions
            if rev.created_by_id == request.user.pk:
                messages.error(
                    request,
                    f"Separation of duties violation: you created revision #{rev.revision_number} of '{rev.translation}' and cannot approve it.",
                )
                continue

            try:
                approve_scheme_revision(rev.id, request.user, notes="Approved via Django Admin bulk action.")
                approved_count += 1
            except ValidationError as e:
                messages.error(request, f"Approval failed for revision #{rev.revision_number}: {e.message}")

        if approved_count:
            messages.success(request, f"Successfully approved {approved_count} revision(s).")

    @admin.action(description="Reject selected revisions (with reason) / मसुदा नाकारा")
    def reject_revisions_action(self, request, queryset):
        if not can_approve_content(request.user):
            raise PermissionDenied("Only Super Administrators can reject content revisions.")

        if 'apply' in request.POST:
            form = RejectSchemeActionForm(request.POST)
            if form.is_valid():
                reason = form.cleaned_data['rejection_reason']
                rejected_count = 0
                for rev in queryset:
                    if rev.editorial_status != EDITORIAL_SUBMITTED:
                        messages.warning(request, f"Cannot reject revision #{rev.revision_number}: not in 'submitted' status.")
                        continue
                    try:
                        reject_scheme_revision(rev.id, request.user, reason)
                        rejected_count += 1
                    except ValidationError as e:
                        messages.error(request, f"Rejection failed for revision #{rev.revision_number}: {e.message}")

                if rejected_count:
                    messages.warning(request, f"Rejected {rejected_count} revision(s). Authors must address feedback and submit new revisions.")
                return None
        else:
            form = RejectSchemeActionForm()

        return render(
            request,
            'governance/reject_action.html',
            {
                'title': 'Reject Revision / मसुदा नाकारा',
                'queryset': queryset,
                'form': form,
                'action_name': 'reject_revisions_action',
            },
        )
