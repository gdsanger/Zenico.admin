from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import AdminUser


@admin.register(AdminUser)
class AdminUserAdmin(BaseUserAdmin):
    """Admin interface for AdminUser model."""

    # Fields to display in the list view
    list_display = ('email', 'display_name', 'role', 'is_active', 'is_staff', 'created_at')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser', 'created_at')
    search_fields = ('email', 'display_name')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'last_login', 'created_at', 'updated_at')

    # Fields to display in the detail/edit view
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal Info'), {'fields': ('display_name', 'role')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Important Dates'), {'fields': ('last_login', 'created_at', 'updated_at')}),
        (_('System Info'), {'fields': ('id',)}),
    )

    # Fields to display when creating a new user
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'display_name', 'role', 'password1', 'password2', 'is_active', 'is_staff'),
        }),
    )
