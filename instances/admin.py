from django.contrib import admin
from .models import Instance


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
    """Admin interface for Instance model."""

    list_display = [
        'display_name',
        'customer',
        'slug',
        'is_master',
        'status',
        'user_seats',
        'ai_addon_active',
        'version',
        'created_at',
    ]
    list_filter = ['status', 'is_master', 'ai_addon_active', 'created_at']
    search_fields = [
        'display_name',
        'slug',
        'customer__company_name',
        'customer__slug',
        'api_key',
        'server_host',
    ]
    readonly_fields = [
        'id',
        'api_key',
        'created_at',
        'updated_at',
        'fqdn',
    ]

    fieldsets = [
        ('Basic Information', {
            'fields': [
                'id',
                'customer',
                'subscription',
                'slug',
                'display_name',
                'is_master',
                'status',
                'fqdn',
            ]
        }),
        ('Resource Allocation', {
            'fields': [
                'user_seats',
                'ai_addon_active',
            ]
        }),
        ('Deployment Configuration', {
            'fields': [
                'server_host',
                'db_name',
                'db_user',
                'django_secret_key',
                'version',
            ]
        }),
        ('API Access', {
            'fields': [
                'api_key',
            ],
            'classes': ['collapse'],
        }),
        ('Health & Monitoring', {
            'fields': [
                'provisioned_at',
                'last_health_check',
                'health_check_ok',
            ],
            'classes': ['collapse'],
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]

    def get_readonly_fields(self, request, obj=None):
        """
        Make slug and is_master readonly after initial creation to prevent accidental changes.
        """
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:  # Editing existing object
            readonly.extend(['slug', 'is_master', 'customer', 'subscription'])
        return readonly

    def fqdn(self, obj):
        """Display the computed FQDN in the admin."""
        return obj.fqdn
    fqdn.short_description = 'FQDN'
