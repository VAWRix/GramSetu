"""
Django Admin configuration and secure governance workflows for apps.gallery.

Enforces least-privilege role authorization, separation of duties in album publication,
statutory Marathi primary translation validation, mandatory accessibility alt-text,
private image binary decoupled storage, and integration with governance services
(ADRs 0001, 0002, 0003, and 0006).
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.identity.permissions import (
    is_super_admin,
    can_edit_content,
    can_publish_content,
)
from apps.governance.services import (
    submit_gallery_album_for_approval,
    approve_and_publish_gallery_album,
    reject_gallery_album,
    withdraw_gallery_album,
    archive_gallery_album,
)
from apps.gallery.models import (
    GalleryAlbum,
    AlbumTranslation,
    GalleryItem,
    STATUS_DRAFT,
    STATUS_PENDING_APPROVAL,
    STATUS_APPROVED,
    STATUS_PUBLISHED,
    STATUS_WITHDRAWN,
    STATUS_ARCHIVED,
    LANGUAGE_MARATHI,
    LANGUAGE_HINDI,
    LANGUAGE_ENGLISH,
    ALBUM_CATEGORY_CHOICES,
)
from apps.gallery.storage import (
    save_gallery_image,
    validate_image_file,
    MAX_IMAGE_SIZE_BYTES,
)


class GalleryItemCreationForm(forms.ModelForm):
    """
    Form for uploading a new photograph binary to private gallery storage.
    Enforces file size, extension, magic byte validation, and mandatory accessibility alt text.
    """
    image_file = forms.FileField(
        required=True,
        label="Photograph Image File / छायाचित्र फाइल",
        help_text="Upload official JPEG, PNG, or WebP photograph. Maximum size 15 MB.",
    )

    class Meta:
        model = GalleryItem
        fields = (
            'album',
            'image_file',
            'display_order',
            'is_cover_image',
            'caption_mr',
            'caption_hi',
            'caption_en',
            'alt_text_mr',
            'alt_text_hi',
            'alt_text_en',
        )

    def clean_image_file(self):
        f = self.cleaned_data.get('image_file')
        if not f:
            raise forms.ValidationError("A photograph image file must be selected.")
        validate_image_file(f, f.name)
        return f

    def clean(self):
        cleaned_data = super().clean()
        alt_mr = cleaned_data.get('alt_text_mr', '').strip()
        if not alt_mr or len(alt_mr) < 3:
            self.add_error('alt_text_mr', "Mandatory Marathi accessibility alt text (alt_text_mr) must be at least 3 characters.")
        return cleaned_data

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data['image_file']

        storage_path, clean_name, file_size_bytes, detected_mime, checksum = save_gallery_image(
            uploaded_file, uploaded_file.name
        )

        instance.storage_path = storage_path
        instance.original_filename = clean_name
        instance.file_size_bytes = file_size_bytes
        instance.mime_type = detected_mime
        instance.checksum_sha256 = checksum

        if user:
            instance.uploaded_by = user

        if commit:
            instance.save()
        return instance


class GalleryItemChangeForm(forms.ModelForm):
    """
    Form for updating metadata of an existing GalleryItem.
    The binary file and storage coordinates are immutable to preserve cryptographic binding.
    """
    class Meta:
        model = GalleryItem
        fields = (
            'album',
            'display_order',
            'is_cover_image',
            'caption_mr',
            'caption_hi',
            'caption_en',
            'alt_text_mr',
            'alt_text_hi',
            'alt_text_en',
        )

    def clean(self):
        cleaned_data = super().clean()
        alt_mr = cleaned_data.get('alt_text_mr', '').strip()
        if not alt_mr or len(alt_mr) < 3:
            self.add_error('alt_text_mr', "Mandatory Marathi accessibility alt text (alt_text_mr) must be at least 3 characters.")
        return cleaned_data


class AlbumTranslationInline(admin.StackedInline):
    model = AlbumTranslation
    extra = 0
    fields = ('language_code', 'title', 'description')


class GalleryItemInline(admin.TabularInline):
    model = GalleryItem
    extra = 0
    fields = (
        'display_order',
        'is_cover_image',
        'original_filename',
        'mime_type',
        'file_size_display',
        'alt_text_mr',
        'approval_status_badge',
    )
    readonly_fields = (
        'original_filename',
        'mime_type',
        'file_size_display',
        'approval_status_badge',
    )

    @admin.display(description="File Size")
    def file_size_display(self, obj):
        if not obj.file_size_bytes:
            return "-"
        if obj.file_size_bytes < 1024 * 1024:
            return f"{obj.file_size_bytes / 1024:.1f} KB"
        return f"{obj.file_size_bytes / (1024 * 1024):.2f} MB"

    @admin.display(description="Approval")
    def approval_status_badge(self, obj):
        if obj.approved_by:
            return format_html('<span style="color:#006b52; font-weight:bold;">✓ Approved</span>')
        return format_html('<span style="color:#e67e22; font-weight:bold;">⏳ Pending Review</span>')


@admin.register(GalleryAlbum)
class GalleryAlbumAdmin(admin.ModelAdmin):
    list_display = (
        'title_display',
        'slug',
        'category_badge',
        'status_badge',
        'event_date',
        'photo_count',
        'translation_completeness',
        'is_published',
        'created_by',
    )
    list_filter = ('category', 'status', 'is_published', 'event_date')
    search_fields = ('slug', 'translations__title', 'translations__description')
    inlines = [AlbumTranslationInline, GalleryItemInline]
    actions = [
        'submit_for_approval_action',
        'approve_and_publish_action',
        'reject_album_action',
        'withdraw_album_action',
        'archive_album_action',
    ]

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and (obj.is_published or obj.status in (STATUS_PUBLISHED, STATUS_APPROVED)):
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        ro = ['created_by', 'created_at', 'updated_at', 'album_hash_display']
        if obj and obj.status in (STATUS_PUBLISHED, STATUS_WITHDRAWN, STATUS_ARCHIVED):
            ro.extend(['is_published', 'status'])
        return ro

    def save_model(self, request, obj, form, change):
        if not change or not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Album Title / अल्बम शीर्षक")
    def title_display(self, obj):
        title = obj.get_title(LANGUAGE_MARATHI)
        return title or f"[{obj.slug}]"

    @admin.display(description="Category / श्रेणी")
    def category_badge(self, obj):
        return obj.get_category_display()

    @admin.display(description="Status / स्थिती")
    def status_badge(self, obj):
        colors = {
            STATUS_PUBLISHED: '#006b52',
            STATUS_PENDING_APPROVAL: '#e67e22',
            STATUS_DRAFT: '#6c757d',
            STATUS_APPROVED: '#007791',
            STATUS_WITHDRAWN: '#ba2121',
            STATUS_ARCHIVED: '#7f8c8d',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:3px; font-size:12px; font-weight:bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Photos / छायाचित्रे")
    def photo_count(self, obj):
        count = obj.items.count()
        return f"{count} photos"

    @admin.display(description="Digest / डिजिटल हॅश")
    def album_hash_display(self, obj):
        if not obj.pk:
            return "-"
        h = obj.calculate_hash()
        return format_html('<code style="font-size:11px; color:#555;">{}</code>', h[:16] + '...')

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

    @admin.action(description="Submit selected album(s) for publication review")
    def submit_for_approval_action(self, request, queryset):
        count = 0
        for album in queryset:
            if album.status == STATUS_DRAFT:
                try:
                    submit_gallery_album_for_approval(album.id, request.user)
                    count += 1
                except Exception as e:
                    self.message_user(request, f"Error submitting album '{album.slug}': {e}", level=messages.ERROR)
            else:
                self.message_user(
                    request,
                    f"Album '{album.slug}' is already in '{album.status}' status.",
                    level=messages.WARNING,
                )
        if count:
            self.message_user(request, f"Submitted {count} gallery album(s) for publication review.", level=messages.SUCCESS)

    @admin.action(description="Approve and publish selected album(s) (मंजूर आणि प्रकाशित करा)")
    def approve_and_publish_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can approve and publish gallery albums.", level=messages.ERROR)
            return

        count = 0
        for album in queryset:
            if album.status not in (STATUS_DRAFT, STATUS_PENDING_APPROVAL):
                self.message_user(
                    request,
                    f"Album '{album.slug}' cannot be published from '{album.status}' status.",
                    level=messages.WARNING,
                )
                continue

            # Separation of duties anti-self-approval enforcement
            if album.created_by_id == request.user.pk:
                self.message_user(
                    request,
                    f"Separation of duties violation: you created album '{album.slug}' and cannot approve your own album.",
                    level=messages.ERROR,
                )
                continue

            try:
                approve_and_publish_gallery_album(
                    album.id,
                    request.user,
                    notes=f"Approved in Django Admin by {request.user.email}",
                )
                count += 1
            except Exception as e:
                self.message_user(request, f"Error approving album '{album.slug}': {e}", level=messages.ERROR)

        if count:
            self.message_user(request, f"Approved and published {count} gallery album(s) to public portal.", level=messages.SUCCESS)

    @admin.action(description="Reject selected album(s) (नाकारा)")
    def reject_album_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can reject gallery albums.", level=messages.ERROR)
            return

        if request.POST.get('post') == 'yes':
            reason = request.POST.get('rejection_reason', '').strip()
            if len(reason) < 10:
                self.message_user(request, "Rejection reason must be at least 10 non-whitespace characters.", level=messages.ERROR)
                return None

            count = 0
            for album in queryset:
                if album.status == STATUS_PENDING_APPROVAL:
                    try:
                        reject_gallery_album(album.id, request.user, reason)
                        count += 1
                    except Exception as e:
                        self.message_user(request, f"Error rejecting album '{album.slug}': {e}", level=messages.ERROR)
                else:
                    self.message_user(
                        request,
                        f"Album '{album.slug}' is not pending approval.",
                        level=messages.WARNING,
                    )
            if count:
                self.message_user(request, f"Rejected {count} gallery album(s).", level=messages.SUCCESS)
            return None

        return render(
            request,
            'admin/governance/action_intermediate.html',
            {
                'title': 'Reject Gallery Album / अल्बम मंजुरी नाकारा',
                'description': 'Rejecting an album resets its status to draft and records an immutable rejection rationale in the governance audit ledger.',
                'items': queryset,
                'field_type': 'textarea',
                'input_name': 'rejection_reason',
                'input_label': 'Mandatory Rejection Rationale / नकाराचे कारण (किमान १० अक्षरे):',
                'placeholder': 'Explain why this album or photograph does not meet Panchayat publication standards...',
                'help_text': 'This rationale is recorded permanently in the governance audit ledger.',
                'submit_label': 'Confirm Rejection / नकार नोंदवा',
                'action_name': 'reject_album_action',
                'cancel_url': reverse('admin:gallery_galleryalbum_changelist'),
            },
        )

    @admin.action(description="Withdraw selected album(s) from public view (मागे घ्या)")
    def withdraw_album_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can withdraw public gallery albums.", level=messages.ERROR)
            return

        if request.POST.get('post') == 'yes':
            justification = request.POST.get('justification', '').strip()
            if len(justification) < 10:
                self.message_user(request, "Withdrawal justification must be at least 10 non-whitespace characters.", level=messages.ERROR)
                return None

            count = 0
            for album in queryset:
                if album.is_published:
                    try:
                        withdraw_gallery_album(album.id, request.user, justification)
                        count += 1
                    except Exception as e:
                        self.message_user(request, f"Error withdrawing album '{album.slug}': {e}", level=messages.ERROR)
                else:
                    self.message_user(
                        request,
                        f"Album '{album.slug}' is not currently published.",
                        level=messages.WARNING,
                    )
            if count:
                self.message_user(request, f"Successfully withdrawn {count} album(s) from public citizen view.", level=messages.WARNING)
            return None

        return render(
            request,
            'admin/governance/action_intermediate.html',
            {
                'title': 'Withdraw Gallery Album / अल्बम मागे घ्या',
                'description': 'Withdrawing immediately severs citizen access (returns 404 for anonymous users) and records an immutable administrative event.',
                'items': queryset,
                'field_type': 'textarea',
                'input_name': 'justification',
                'input_label': 'Mandatory Administrative Justification / कारण (किमान १० अक्षरे):',
                'placeholder': 'Explain the statutory reason for withdrawing this photograph collection...',
                'help_text': 'This justification is recorded permanently in the append-only governance ledger.',
                'submit_label': 'Execute Withdrawal / अल्बम मागे घ्या',
                'action_name': 'withdraw_album_action',
                'cancel_url': reverse('admin:gallery_galleryalbum_changelist'),
            },
        )

    @admin.action(description="Archive selected album(s) (संग्रहित करा)")
    def archive_album_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can archive gallery albums.", level=messages.ERROR)
            return

        count = 0
        for album in queryset:
            try:
                archive_gallery_album(album.id, request.user)
                count += 1
            except Exception as e:
                self.message_user(request, f"Error archiving album '{album.slug}': {e}", level=messages.ERROR)

        if count:
            self.message_user(request, f"Archived {count} gallery album(s).", level=messages.SUCCESS)


@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = (
        'id_short',
        'album',
        'original_filename',
        'mime_type',
        'file_size_display',
        'display_order',
        'is_cover_image',
        'alt_text_mr',
        'approval_badge',
        'uploaded_by',
    )
    list_filter = ('album__category', 'mime_type', 'is_cover_image', 'approved_by')
    search_fields = ('original_filename', 'caption_mr', 'alt_text_mr', 'album__slug')
    readonly_fields = (
        'storage_path',
        'original_filename',
        'file_size_bytes',
        'mime_type',
        'checksum_sha256',
        'uploaded_by',
        'uploaded_at',
        'approved_by',
        'approved_at',
        'file_integrity_status',
    )

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_super_admin(request.user):
            return False
        if obj and obj.album and obj.album.is_published:
            return False
        return True

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            return GalleryItemCreationForm
        return GalleryItemChangeForm

    def save_model(self, request, obj, form, change):
        if not change:
            form.save(commit=True, user=request.user)
        else:
            super().save_model(request, obj, form, change)

    @admin.display(description="Photo ID")
    def id_short(self, obj):
        return f"#{str(obj.id)[:8]}"

    @admin.display(description="File Size")
    def file_size_display(self, obj):
        if not obj.file_size_bytes:
            return "-"
        if obj.file_size_bytes < 1024 * 1024:
            return f"{obj.file_size_bytes / 1024:.1f} KB"
        return f"{obj.file_size_bytes / (1024 * 1024):.2f} MB"

    @admin.display(description="Approval")
    def approval_badge(self, obj):
        if obj.approved_by:
            return format_html('<span style="color:#006b52; font-weight:bold;">✓ Approved</span>')
        return format_html('<span style="color:#e67e22; font-weight:bold;">⏳ Pending Review</span>')

    @admin.display(description="Disk Integrity Check")
    def file_integrity_status(self, obj):
        if not obj.pk or not obj.storage_path:
            return "-"
        if obj.verify_integrity():
            return format_html('<span style="color:#006b52; font-weight:bold;">✓ Cryptographically Verified (SHA-256 Valid)</span>')
        return format_html('<span style="color:#ba2121; font-weight:bold;">✗ INTEGRITY FAILURE: File Missing or Tampered</span>')


@admin.register(AlbumTranslation)
class AlbumTranslationAdmin(admin.ModelAdmin):
    list_display = ('album', 'language_code', 'title')
    list_filter = ('language_code',)
    search_fields = ('title', 'description', 'album__slug')

    def has_add_permission(self, request):
        return can_edit_content(request.user)

    def has_change_permission(self, request, obj=None):
        return can_edit_content(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_super_admin(request.user)
