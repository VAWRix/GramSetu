"""
Django Admin configuration and secure governance workflows for apps.events.

Enforces least-privilege role authorization, separation of duties in event publication,
statutory Marathi primary translation validation, cancellation tracking, and event immutability.
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.utils.html import format_html

from apps.identity.permissions import (
    is_super_admin,
    can_edit_content,
)
from apps.governance.services import (
    submit_event_for_approval,
    approve_and_publish_event,
    reject_event,
    cancel_event,
    withdraw_event,
    archive_event,
)
from apps.events.models import (
    PanchayatEvent,
    EventTranslation,
    STATUS_DRAFT,
    STATUS_PENDING_APPROVAL,
    STATUS_APPROVED,
    STATUS_PUBLISHED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_ARCHIVED,
    LANGUAGE_MARATHI,
)


class EventTranslationInline(admin.StackedInline):
    model = EventTranslation
    extra = 0
    fields = ('language_code', 'title', 'venue_override', 'agenda', 'description')


class RejectEventActionForm(forms.Form):
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 60}),
        label="Reason for Rejection (नकाराचे कारण)",
        help_text="Mandatory rationale explaining why event approval was rejected (minimum 10 characters).",
        min_length=10,
        required=True,
    )


class CancelEventActionForm(forms.Form):
    cancellation_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 60}),
        label="Statutory Reason for Event Cancellation (कार्यक्रम रद्द करण्याचे कारण)",
        help_text="Mandatory explanation for citizens (e.g. administrative postponement, extreme weather) (minimum 10 characters).",
        min_length=10,
        required=True,
    )


class WithdrawEventActionForm(forms.Form):
    justification = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 60}),
        label="Reason for Administrative Withdrawal (मागे घेण्याचे कारण)",
        help_text="Mandatory rationale for withdrawing event from public view (minimum 10 characters).",
        min_length=10,
        required=True,
    )


@admin.register(PanchayatEvent)
class PanchayatEventAdmin(admin.ModelAdmin):
    list_display = (
        'title_display',
        'event_type',
        'status_badge',
        'start_datetime',
        'end_datetime',
        'venue_display',
        'translation_completeness',
        'is_published',
        'created_by',
    )
    list_filter = ('event_type', 'status', 'is_published', 'start_datetime')
    search_fields = ('venue_mr', 'venue_en', 'venue_hi', 'translations__title', 'translations__agenda')
    inlines = [EventTranslationInline]
    actions = [
        'submit_for_approval_action',
        'approve_and_publish_action',
        'reject_event_action',
        'cancel_event_action',
        'withdraw_event_action',
        'archive_event_action',
    ]

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and (obj.is_published or obj.status in (STATUS_PUBLISHED, STATUS_COMPLETED)):
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        ro = ['created_by', 'created_at', 'updated_at']
        if obj and obj.status in (STATUS_PUBLISHED, STATUS_COMPLETED, STATUS_CANCELLED):
            ro.extend(['is_published'])
        return ro

    def save_model(self, request, obj, form, change):
        if not change or not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Event Title / कार्यक्रम शीर्षक")
    def title_display(self, obj):
        title = obj.get_title(LANGUAGE_MARATHI)
        return title or f"[{obj.get_event_type_display()}]"

    @admin.display(description="Venue / ठिकाण")
    def venue_display(self, obj):
        return obj.venue_mr

    @admin.display(description="Status / स्थिती")
    def status_badge(self, obj):
        colors = {
            STATUS_PUBLISHED: '#006b52',
            STATUS_PENDING_APPROVAL: '#e67e22',
            STATUS_DRAFT: '#6c757d',
            STATUS_APPROVED: '#007791',
            STATUS_CANCELLED: '#ba2121',
            STATUS_COMPLETED: '#27ae60',
            STATUS_ARCHIVED: '#7f8c8d',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:3px; font-size:12px; font-weight:bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Translation Completeness / भाषांतर पूर्णता")
    def translation_completeness(self, obj):
        translations = {t.language_code: t for t in obj.translations.all()}
        badges = []
        for lang in ['mr', 'hi', 'en']:
            t = translations.get(lang)
            if t:
                badges.append(
                    f'<span style="background:#006b52; color:#fff; padding:2px 6px; border-radius:3px; font-size:11px;">{lang}: ✓</span>'
                )
            else:
                color = '#ba2121' if lang == 'mr' else '#6c757d'
                label = 'Missing (Primary)' if lang == 'mr' else 'Missing'
                badges.append(
                    f'<span style="background:#f0f0f0; color:{color}; border:1px solid {color}; padding:2px 6px; border-radius:3px; font-size:11px;">{lang}: {label}</span>'
                )
        return format_html(" ".join(badges))

    @admin.action(description="Submit selected event(s) for publication review")
    def submit_for_approval_action(self, request, queryset):
        count = 0
        for event in queryset:
            if event.status == STATUS_DRAFT:
                try:
                    submit_event_for_approval(event.id, request.user)
                    count += 1
                except Exception as e:
                    self.message_user(request, f"Error submitting event #{event.id}: {e}", level=messages.ERROR)
            else:
                self.message_user(
                    request,
                    f"Event #{event.id} is already in '{event.status}' status.",
                    level=messages.WARNING,
                )
        if count:
            self.message_user(request, f"Submitted {count} event(s) for publication review.", level=messages.SUCCESS)

    @admin.action(description="Approve and publish selected event(s) (मंजूर आणि प्रकाशित करा)")
    def approve_and_publish_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can approve and publish events.", level=messages.ERROR)
            return

        count = 0
        for event in queryset:
            if event.status not in (STATUS_DRAFT, STATUS_PENDING_APPROVAL):
                self.message_user(
                    request,
                    f"Event #{event.id} cannot be published from '{event.status}' status.",
                    level=messages.WARNING,
                )
                continue

            # Separation of duties anti-self-approval enforcement
            if event.created_by_id == request.user.pk:
                self.message_user(
                    request,
                    f"Separation of duties violation: you created this event and cannot approve your own event for publication.",
                    level=messages.ERROR,
                )
                continue

            try:
                approve_and_publish_event(
                    event.id,
                    request.user,
                    notes=f"Approved in Django Admin by {request.user.email}",
                )
                count += 1
            except Exception as e:
                self.message_user(request, f"Error approving event #{event.id}: {e}", level=messages.ERROR)

        if count:
            self.message_user(request, f"Approved and published {count} event(s) to public portal.", level=messages.SUCCESS)

    @admin.action(description="Reject selected event(s) (नाकारा)")
    def reject_event_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can reject events.", level=messages.ERROR)
            return

        if 'apply' in request.POST:
            form = RejectEventActionForm(request.POST)
            if form.is_valid():
                reason = form.cleaned_data['rejection_reason']
                count = 0
                for event in queryset:
                    if event.status == STATUS_PENDING_APPROVAL:
                        try:
                            reject_event(event.id, request.user, reason)
                            count += 1
                        except Exception as e:
                            self.message_user(request, f"Error rejecting event #{event.id}: {e}", level=messages.ERROR)
                    else:
                        self.message_user(
                            request,
                            f"Event #{event.id} is not pending approval.",
                            level=messages.WARNING,
                        )
                if count:
                    self.message_user(request, f"Rejected {count} event(s).", level=messages.SUCCESS)
                return None
        else:
            form = RejectEventActionForm()

        return render(
            request,
            'governance/reject_confirmation.html',
            {
                'title': "Confirm Rejection of Event / कार्यक्रम नकार पुष्टी",
                'queryset': queryset,
                'form': form,
                'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            },
        )

    @admin.action(description="Cancel selected event(s) (कार्यक्रम रद्द करा)")
    def cancel_event_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can cancel public events.", level=messages.ERROR)
            return

        if 'apply' in request.POST:
            form = CancelEventActionForm(request.POST)
            if form.is_valid():
                reason = form.cleaned_data['cancellation_reason']
                count = 0
                for event in queryset:
                    if event.status != STATUS_CANCELLED:
                        try:
                            cancel_event(event.id, request.user, reason)
                            count += 1
                        except Exception as e:
                            self.message_user(request, f"Error cancelling event #{event.id}: {e}", level=messages.ERROR)
                if count:
                    self.message_user(request, f"Cancelled {count} event(s).", level=messages.SUCCESS)
                return None
        else:
            form = CancelEventActionForm()

        return render(
            request,
            'governance/withdraw_confirmation.html',
            {
                'title': "Confirm Statutory Cancellation of Event / कार्यक्रम रद्द करण्याची पुष्टी",
                'queryset': queryset,
                'form': form,
                'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            },
        )

    @admin.action(description="Withdraw selected event(s) from public view (मागे घ्या)")
    def withdraw_event_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can withdraw public events.", level=messages.ERROR)
            return

        if 'apply' in request.POST:
            form = WithdrawEventActionForm(request.POST)
            if form.is_valid():
                justification = form.cleaned_data['justification']
                count = 0
                for event in queryset:
                    if event.is_published:
                        try:
                            withdraw_event(event.id, request.user, justification)
                            count += 1
                        except Exception as e:
                            self.message_user(request, f"Error withdrawing event #{event.id}: {e}", level=messages.ERROR)
                if count:
                    self.message_user(request, f"Successfully withdrawn {count} event(s) from public portal.", level=messages.SUCCESS)
                return None
        else:
            form = WithdrawEventActionForm()

        return render(
            request,
            'governance/withdraw_confirmation.html',
            {
                'title': "Confirm Administrative Withdrawal of Event / कार्यक्रम मागे घेण्याची पुष्टी",
                'queryset': queryset,
                'form': form,
                'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            },
        )

    @admin.action(description="Archive selected event(s) (संग्रहित करा)")
    def archive_event_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can archive events.", level=messages.ERROR)
            return

        count = 0
        for event in queryset:
            try:
                archive_event(event.id, request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f"Error archiving event #{event.id}: {e}", level=messages.ERROR)

        if count:
            self.message_user(request, f"Archived {count} event(s).", level=messages.SUCCESS)
