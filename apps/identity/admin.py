"""
Django Admin configuration for apps.identity.

Restricts identity and role management strictly to Super Administrators.
"""

from django.contrib import admin
from django.utils.html import format_html
from apps.identity.models import User, RoleAssignment, InvitationToken, OperatorUrgentAuthorization
from apps.identity.permissions import is_super_admin


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'phone_number', 'role_badge', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser')
    search_fields = ('email', 'full_name', 'phone_number')
    readonly_fields = ('id', 'date_joined', 'last_login')
    ordering = ('-date_joined',)

    def has_add_permission(self, request):
        return is_super_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_super_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_super_admin(request.user)

    @admin.display(description="Role / भूमिका")
    def role_badge(self, obj):
        if hasattr(obj, 'role_assignment'):
            role = obj.role_assignment.role
            color = '#006b52' if role == 'super_admin' else '#007791'
            return format_html(
                '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:3px; font-size:11px; font-weight:bold;">{}</span>',
                color,
                obj.role_assignment.get_role_display(),
            )
        return format_html('<span style="color:#888;">(No Role)</span>')


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'assigned_by', 'assigned_at')
    list_filter = ('role',)
    search_fields = ('user__email', 'user__full_name')
    readonly_fields = ('assigned_at',)

    def has_add_permission(self, request):
        return is_super_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_super_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_super_admin(request.user)

    def save_model(self, request, obj, form, change):
        if not change or not obj.assigned_by:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(InvitationToken)
class InvitationTokenAdmin(admin.ModelAdmin):
    list_display = ('email', 'target_role', 'invited_by', 'created_at', 'expires_at', 'is_valid_display')
    list_filter = ('target_role', 'is_revoked')
    search_fields = ('email',)
    readonly_fields = ('id', 'token_hash', 'created_at', 'used_at')

    def has_add_permission(self, request):
        return is_super_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_super_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_super_admin(request.user)

    @admin.display(description="Status / स्थिती")
    def is_valid_display(self, obj):
        if obj.is_valid:
            return format_html('<span style="color:#006b52; font-weight:bold;">Active / वैध</span>')
        return format_html('<span style="color:#ba2121;">Expired/Used/Revoked</span>')


@admin.register(OperatorUrgentAuthorization)
class OperatorUrgentAuthorizationAdmin(admin.ModelAdmin):
    list_display = ('operator', 'allowed_category', 'authorized_by', 'valid_from', 'valid_to', 'is_revoked', 'is_valid')
    list_filter = ('allowed_category', 'is_revoked')
    search_fields = ('operator__email', 'authorized_by__email')
    readonly_fields = ('created_at',)

    def has_add_permission(self, request):
        return is_super_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_super_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_super_admin(request.user)
