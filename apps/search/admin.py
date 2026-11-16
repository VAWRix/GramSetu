"""
Django Admin configuration for Unified Public Search (apps.search).

Provides read-only inspection of SearchDocumentIndex and administrative reindexing action.
"""

from django.contrib import admin, messages
from apps.identity.permissions import is_super_admin
from apps.search.models import SearchDocumentIndex
from apps.search.services import rebuild_search_index


@admin.register(SearchDocumentIndex)
class SearchDocumentIndexAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'target_content_type',
        'language_code',
        'category_display',
        'published_at',
        'url_path',
        'updated_at',
    )
    list_filter = ('target_content_type', 'language_code', 'category')
    search_fields = ('title', 'summary', 'search_text', 'url_path')
    readonly_fields = (
        'target_content_type',
        'target_id',
        'language_code',
        'title',
        'summary',
        'search_text',
        'search_vector',
        'published_at',
        'url_path',
        'category',
        'category_display',
        'updated_at',
    )
    actions = ['rebuild_index_action']

    def has_module_permission(self, request):
        return is_super_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return is_super_admin(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return is_super_admin(request.user)

    @admin.action(description="Rebuild unified search index from all published content (पुन्हा निर्देशांक तयार करा)")
    def rebuild_index_action(self, request, queryset):
        if not is_super_admin(request.user):
            self.message_user(request, "Only Super Administrators can rebuild the search index.", level=messages.ERROR)
            return

        count = rebuild_search_index()
        self.message_user(
            request,
            f"Successfully rebuilt unified search index with {count} records across all published domains.",
            level=messages.SUCCESS,
        )
