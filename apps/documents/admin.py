"""
Django Admin configuration and secure governance workflows for apps.documents.

Enforces least-privilege role authorization, separation of duties, document version immutability,
statutory retention hold protections, and ADR 0004 disclosure approvals.
"""

import mimetypes
from django import forms
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
    submit_document_version_for_disclosure,
    approve_document_disclosure,
    reject_document_disclosure,
    withdraw_document_translation,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    CATEGORY_CHOICES,
    STATUS_DRAFT,
    STATUS_PENDING_APPROVAL,
    STATUS_DISCLOSED,
    STATUS_WITHDRAWN,
    STATUS_ARCHIVED,
    DISCLOSURE_DRAFT,
    DISCLOSURE_PENDING_APPROVAL,
    DISCLOSURE_APPROVED,
    DISCLOSURE_REJECTED,
    DISCLOSURE_WITHDRAWN,
)
from apps.documents.storage import (
    save_private_document,
    sanitize_filename,
    MAX_FILE_SIZE_BYTES,
)


class DocumentTranslationInline(admin.TabularInline):
    model = DocumentTranslation
    extra = 0
    fields = ('language_code', 'title', 'status_badge', 'current_version', 'is_disclosed_display', 'updated_at')
    readonly_fields = ('status_badge', 'current_version', 'is_disclosed_display', 'updated_at')

    @admin.display(description="Status / स्थिती")
    def status_badge(self, obj):
        if not obj.pk:
            return "-"
        colors = {
            STATUS_DISCLOSED: '#006b52',
            STATUS_PENDING_APPROVAL: '#e67e22',
            STATUS_DRAFT: '#6c757d',
            STATUS_WITHDRAWN: '#ba2121',
            STATUS_ARCHIVED: '#7f8c8d',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:3px; font-size:12px; font-weight:bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Public / सार्वजनिक?")
    def is_disclosed_display(self, obj):
        if not obj.pk:
            return "-"
        if obj.is_publicly_disclosed():
            return format_html('<span style="color:#006b52; font-weight:bold;">✓ Public</span>')
        return format_html('<span style="color:#ba2121;">✗ Private</span>')


class DocumentVersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    fields = ('version_number', 'original_filename', 'file_size_display', 'mime_type', 'disclosure_badge', 'uploaded_by', 'uploaded_at')
    readonly_fields = ('version_number', 'original_filename', 'file_size_display', 'mime_type', 'disclosure_badge', 'uploaded_by', 'uploaded_at')
    can_delete = False

    @admin.display(description="File Size")
    def file_size_display(self, obj):
        kb = obj.file_size_bytes / 1024
        if kb > 1024:
            return f"{kb / 1024:.2f} MB"
        return f"{kb:.1f} KB"

    @admin.display(description="Disclosure Status")
    def disclosure_badge(self, obj):
        colors = {
            DISCLOSURE_APPROVED: '#006b52',
            DISCLOSURE_PENDING_APPROVAL: '#e67e22',
            DISCLOSURE_DRAFT: '#6c757d',
            DISCLOSURE_REJECTED: '#ba2121',
            DISCLOSURE_WITHDRAWN: '#7f8c8d',
        }
        color = colors.get(obj.disclosure_status, '#333')
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 6px; border-radius:3px; font-size:11px;">{}</span>',
            color,
            obj.get_disclosure_status_display(),
        )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'reference_number_display',
        'category',
        'issuing_department',
        'issue_date',
        'confidential_badge',
        'retention_hold_badge',
        'translation_completeness',
        'created_at',
    )
    list_filter = ('category', 'is_confidential', 'retention_hold', 'issue_date')
    search_fields = ('reference_number', 'issuing_department', 'translations__title')
    inlines = [DocumentTranslationInline]

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and obj.retention_hold:
            return False
        if obj and obj.translations.filter(status=STATUS_DISCLOSED).exists():
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        ro = ['created_at', 'updated_at']
        if not is_super_admin(request.user):
            ro.extend(['retention_hold', 'is_confidential'])
        return ro

    @admin.display(description="Reference No. / संदर्भ क्रमांक")
    def reference_number_display(self, obj):
        return obj.reference_number or "(No Ref)"

    @admin.display(description="Confidential? / गोपनीय?")
    def confidential_badge(self, obj):
        if obj.is_confidential:
            return format_html(
                '<span style="background:#ba2121; color:#fff; padding:2px 6px; border-radius:3px; font-size:11px; font-weight:bold;">'
                '🔒 Confidential</span>'
            )
        return format_html('<span style="color:#6c757d; font-size:11px;">Public / खुला</span>')

    @admin.display(description="Retention Hold / धारणा बंधन")
    def retention_hold_badge(self, obj):
        if obj.retention_hold:
            return format_html(
                '<span style="background:#856404; color:#fff; padding:2px 6px; border-radius:3px; font-size:11px; font-weight:bold;">'
                '🛡️ HOLD Active</span>'
            )
        return format_html('<span style="color:#6c757d; font-size:11px;">None</span>')

    @admin.display(description="Translation Completeness / भाषांतर पूर्णता")
    def translation_completeness(self, obj):
        translations = {t.language_code: t for t in obj.translations.all()}
        badges = []
        for lang, label in [('mr', 'Marathi'), ('hi', 'Hindi'), ('en', 'English')]:
            t = translations.get(lang)
            if t:
                color = '#006b52' if t.is_publicly_disclosed() else '#6c757d'
                badges.append(
                    f'<span style="background:{color}; color:#fff; padding:2px 6px; border-radius:3px; font-size:11px;">'
                    f'{lang}: {t.get_status_display()}</span>'
                )
            else:
                badges.append(
                    f'<span style="background:#f0f0f0; color:#ba2121; border:1px solid #ba2121; padding:2px 6px; border-radius:3px; font-size:11px;">'
                    f'{lang}: Missing</span>'
                )
        return format_html(" ".join(badges))


class WithdrawActionForm(forms.Form):
    justification = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 60}),
        label="Reason for Administrative Withdrawal (मागे घेण्याचे कारण)",
        help_text="Mandatory statutory justification for withdrawal (minimum 10 characters).",
        min_length=10,
        required=True,
    )


@admin.register(DocumentTranslation)
class DocumentTranslationAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'document_reference',
        'language_code',
        'status_badge',
        'current_version_display',
        'is_disclosed_badge',
        'updated_at',
    )
    list_filter = ('language_code', 'status', 'document__category', 'document__is_confidential')
    search_fields = ('title', 'description', 'document__reference_number', 'document__issuing_department')
    readonly_fields = ('current_version', 'current_publication_event', 'created_at', 'updated_at')
    inlines = [DocumentVersionInline]
    actions = ['withdraw_selected_translations_action']

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and obj.document.retention_hold:
            return False
        if obj and obj.status == STATUS_DISCLOSED:
            return False
        return True

    @admin.display(description="Document Reference")
    def document_reference(self, obj):
        return obj.document.reference_number or str(obj.document)

    @admin.display(description="Status / स्थिती")
    def status_badge(self, obj):
        colors = {
            STATUS_DISCLOSED: '#006b52',
            STATUS_PENDING_APPROVAL: '#e67e22',
            STATUS_DRAFT: '#6c757d',
            STATUS_WITHDRAWN: '#ba2121',
            STATUS_ARCHIVED: '#7f8c8d',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:3px; font-size:12px; font-weight:bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Active Version")
    def current_version_display(self, obj):
        if obj.current_version:
            return f"v{obj.current_version.version_number} ({obj.current_version.original_filename})"
        return "None"

    @admin.display(description="Citizen Disclosure Gate")
    def is_disclosed_badge(self, obj):
        if obj.is_publicly_disclosed():
            url = reverse('documents:citizen_download', args=[obj.id])
            return format_html(
                '<a href="{}" style="background:#006b52; color:#fff; padding:3px 8px; border-radius:3px; text-decoration:none; font-weight:bold;">'
                '🌐 Disclosed (Download)</a>',
                url,
            )
        return format_html('<span style="color:#ba2121; font-weight:bold;">🔒 Private</span>')

    @admin.action(description="Withdraw selected translations from public access (मागे घ्या)")
    def withdraw_selected_translations_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can withdraw public documents.", level=messages.ERROR)
            return

        if 'apply' in request.POST:
            form = WithdrawActionForm(request.POST)
            if form.is_valid():
                justification = form.cleaned_data['justification']
                count = 0
                for trans in queryset:
                    if trans.status != STATUS_WITHDRAWN:
                        withdraw_document_translation(trans.id, request.user, justification)
                        count += 1
                self.message_user(
                    request,
                    f"Successfully withdrawn {count} document translation(s) from public view.",
                    level=messages.SUCCESS,
                )
                return None
        else:
            form = WithdrawActionForm()

        return render(
            request,
            'governance/withdraw_confirmation.html',
            {
                'title': "Confirm Administrative Withdrawal of Documents / दस्तऐवज मागे घेण्याची पुष्टी",
                'queryset': queryset,
                'form': form,
                'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            },
        )


class DocumentVersionCreationForm(forms.ModelForm):
    file = forms.FileField(
        required=True,
        label="Document Binary File (दस्तऐवज फाइल)",
        help_text="Upload binary file (PDF, Office, Image, Zip). Max 50 MB.",
    )

    class Meta:
        model = DocumentVersion
        fields = ('translation',)

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if not f:
            raise forms.ValidationError("A binary file must be selected.")
        if f.size > MAX_FILE_SIZE_BYTES:
            raise forms.ValidationError(
                f"File size ({f.size} bytes) exceeds maximum permitted limit of 50 MB."
            )
        return f

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data['file']

        # Determine version number: max(version_number) + 1 for translation
        latest_ver = (
            DocumentVersion.objects
            .filter(translation=instance.translation)
            .order_by('-version_number')
            .first()
        )
        instance.version_number = (latest_ver.version_number + 1) if latest_ver else 1

        # Process and save private binary file
        storage_filename, file_size_bytes, checksum_sha256 = save_private_document(uploaded_file)
        instance.storage_path = storage_filename
        instance.original_filename = sanitize_filename(uploaded_file.name)
        instance.file_size_bytes = file_size_bytes
        instance.checksum_sha256 = checksum_sha256

        # Detect mime type
        mime = getattr(uploaded_file, 'content_type', None)
        if not mime or mime == 'application/octet-stream':
            guessed_mime, _ = mimetypes.guess_type(uploaded_file.name)
            mime = guessed_mime or 'application/pdf'
        instance.mime_type = mime

        if user:
            instance.uploaded_by = user
        instance.disclosure_status = DISCLOSURE_DRAFT

        if commit:
            instance.save()
        return instance


class RejectVersionActionForm(forms.Form):
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 60}),
        label="Reason for Rejection (नकाराचे कारण)",
        help_text="Mandatory rationale explaining why document disclosure was rejected (minimum 10 characters).",
        min_length=10,
        required=True,
    )


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        'version_display',
        'translation_link',
        'original_filename',
        'file_size_display',
        'mime_type',
        'disclosure_status_badge',
        'uploaded_by',
        'uploaded_at',
        'download_preview_link',
    )
    list_filter = ('disclosure_status', 'mime_type', 'uploaded_at')
    search_fields = ('original_filename', 'translation__title', 'checksum_sha256')
    actions = [
        'submit_for_disclosure_action',
        'approve_disclosure_action',
        'reject_disclosure_action',
    ]

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            return DocumentVersionCreationForm
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change and isinstance(form, DocumentVersionCreationForm):
            form.save(commit=True, user=request.user)
        else:
            super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            # Editing an existing version: full immutability!
            return [
                'version_number',
                'translation',
                'storage_path',
                'original_filename',
                'file_size_bytes',
                'mime_type',
                'checksum_sha256',
                'uploaded_by',
                'uploaded_at',
                'disclosure_status',
                'approval_record',
            ]
        return []

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and obj.translation.document.retention_hold:
            return False
        if obj and obj.disclosure_status != DISCLOSURE_DRAFT:
            return False
        return True

    @admin.display(description="Version / आवृत्ती")
    def version_display(self, obj):
        return f"v{obj.version_number}"

    @admin.display(description="Translation")
    def translation_link(self, obj):
        url = reverse('admin:documents_documenttranslation_change', args=[obj.translation.id])
        return format_html('<a href="{}">{}</a>', url, obj.translation.title)

    @admin.display(description="File Size")
    def file_size_display(self, obj):
        kb = obj.file_size_bytes / 1024
        if kb > 1024:
            return f"{kb / 1024:.2f} MB"
        return f"{kb:.1f} KB"

    @admin.display(description="Disclosure Status")
    def disclosure_status_badge(self, obj):
        colors = {
            DISCLOSURE_APPROVED: '#006b52',
            DISCLOSURE_PENDING_APPROVAL: '#e67e22',
            DISCLOSURE_DRAFT: '#6c757d',
            DISCLOSURE_REJECTED: '#ba2121',
            DISCLOSURE_WITHDRAWN: '#7f8c8d',
        }
        color = colors.get(obj.disclosure_status, '#333')
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:3px; font-size:12px; font-weight:bold;">{}</span>',
            color,
            obj.get_disclosure_status_display(),
        )

    @admin.display(description="Preview / Audit Download")
    def download_preview_link(self, obj):
        url = reverse('documents:version_download', args=[obj.id])
        return format_html(
            '<a href="{}" style="background:#007791; color:#fff; padding:2px 8px; border-radius:3px; text-decoration:none; font-size:11px;">'
            '⬇️ Download v{}</a>',
            url,
            obj.version_number,
        )

    @admin.action(description="Submit selected version(s) for disclosure review")
    def submit_for_disclosure_action(self, request, queryset):
        count = 0
        for version in queryset:
            if version.disclosure_status == DISCLOSURE_DRAFT:
                try:
                    submit_document_version_for_disclosure(version.id, request.user)
                    count += 1
                except Exception as e:
                    self.message_user(request, f"Error submitting v{version.version_number}: {e}", level=messages.ERROR)
            else:
                self.message_user(
                    request,
                    f"Version v{version.version_number} is already in '{version.disclosure_status}' status.",
                    level=messages.WARNING,
                )
        if count:
            self.message_user(request, f"Submitted {count} document version(s) for disclosure review.", level=messages.SUCCESS)

    @admin.action(description="Approve disclosure for selected version(s) (मंजूर करा)")
    def approve_disclosure_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can approve documents for disclosure.", level=messages.ERROR)
            return

        count = 0
        for version in queryset:
            if version.disclosure_status != DISCLOSURE_PENDING_APPROVAL:
                self.message_user(
                    request,
                    f"Version v{version.version_number} must be in 'pending_approval' status. Current: '{version.disclosure_status}'.",
                    level=messages.WARNING,
                )
                continue

            # Separation of duties anti-self-approval enforcement
            if version.uploaded_by_id == request.user.pk:
                self.message_user(
                    request,
                    f"Separation of duties violation: you uploaded v{version.version_number} and cannot approve your own document for disclosure.",
                    level=messages.ERROR,
                )
                continue

            try:
                approve_document_disclosure(
                    version.id,
                    request.user,
                    notes=f"Approved in Django Admin by {request.user.email}",
                )
                count += 1
            except Exception as e:
                self.message_user(request, f"Error approving v{version.version_number}: {e}", level=messages.ERROR)

        if count:
            self.message_user(request, f"Approved {count} document version(s) for public disclosure.", level=messages.SUCCESS)

    @admin.action(description="Reject disclosure for selected version(s) (नाकारा)")
    def reject_disclosure_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can reject documents.", level=messages.ERROR)
            return

        if 'apply' in request.POST:
            form = RejectVersionActionForm(request.POST)
            if form.is_valid():
                reason = form.cleaned_data['rejection_reason']
                count = 0
                for version in queryset:
                    if version.disclosure_status == DISCLOSURE_PENDING_APPROVAL:
                        try:
                            reject_document_disclosure(version.id, request.user, reason)
                            count += 1
                        except Exception as e:
                            self.message_user(request, f"Error rejecting v{version.version_number}: {e}", level=messages.ERROR)
                    else:
                        self.message_user(
                            request,
                            f"Version v{version.version_number} is not pending approval.",
                            level=messages.WARNING,
                        )
                if count:
                    self.message_user(request, f"Rejected {count} document version(s).", level=messages.SUCCESS)
                return None
        else:
            form = RejectVersionActionForm()

        return render(
            request,
            'governance/reject_confirmation.html',
            {
                'title': "Confirm Rejection of Document Disclosure / दस्तऐवज प्रकटीकरण नकार",
                'queryset': queryset,
                'form': form,
                'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            },
        )
