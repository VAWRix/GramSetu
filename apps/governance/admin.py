"""
Django Admin configuration for apps.governance.

Provides read-only audit inspection of approvals, rejections, and publication events.
Disallows in-place alteration or deletion to preserve audit integrity.
"""

from django.contrib import admin
from apps.governance.models import ApprovalRecord, RejectionRecord, PublicationEvent


@admin.register(ApprovalRecord)
class ApprovalRecordAdmin(admin.ModelAdmin):
    list_display = (
        'target_content_type',
        'target_id',
        'revision_id',
        'approved_by',
        'is_self_approval',
        'approved_at',
    )
    list_filter = ('target_content_type', 'is_self_approval')
    search_fields = ('revision_hash', 'notes')
    readonly_fields = (
        'id',
        'target_content_type',
        'target_id',
        'revision_id',
        'revision_hash',
        'approved_by',
        'approved_at',
        'notes',
        'is_self_approval',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RejectionRecord)
class RejectionRecordAdmin(admin.ModelAdmin):
    list_display = (
        'target_content_type',
        'target_id',
        'revision_id',
        'rejected_by',
        'rejected_at',
    )
    list_filter = ('target_content_type',)
    search_fields = ('rejection_reason',)
    readonly_fields = (
        'id',
        'target_content_type',
        'target_id',
        'revision_id',
        'rejected_by',
        'rejected_at',
        'rejection_reason',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PublicationEvent)
class PublicationEventAdmin(admin.ModelAdmin):
    list_display = (
        'event_type',
        'target_content_type',
        'target_id',
        'actor',
        'effective_from',
        'effective_until',
        'created_at',
    )
    list_filter = ('event_type', 'target_content_type')
    search_fields = ('justification',)
    readonly_fields = (
        'id',
        'target_content_type',
        'target_id',
        'revision_id',
        'event_type',
        'scheduled_for',
        'effective_from',
        'effective_until',
        'actor',
        'justification',
        'superseded_event',
        'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
