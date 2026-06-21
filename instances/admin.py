from django.contrib import admin
from .models import Instance, UserLicense, AITokenUsage, InstanceHeartbeat


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
    """Admin interface for Instance model."""

    list_display = [
        'display_name',
        'customer',
        'slug',
        'is_master',
        'status',
        'claimed_at',
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
        'claimed_at',
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
                'image_tag',
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
                'claimed_at',
                'provisioning_error',
                'last_health_check',
                'health_check_ok',
                'last_heartbeat',
                'reported_url',
                'reported_version',
                'reported_active_users',
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


@admin.register(UserLicense)
class UserLicenseAdmin(admin.ModelAdmin):
    """Admin interface for UserLicense model."""

    list_display = [
        'display_name',
        'email',
        'instance',
        'role',
        'is_active',
        'activated_at',
    ]
    list_filter = ['role', 'is_active', 'activated_at', 'instance__customer']
    search_fields = [
        'display_name',
        'email',
        'azure_oid',
        'instance__display_name',
        'instance__customer__company_name',
    ]
    readonly_fields = [
        'id',
        'activated_at',
    ]

    fieldsets = [
        ('User Information', {
            'fields': [
                'id',
                'azure_oid',
                'email',
                'display_name',
            ]
        }),
        ('License Details', {
            'fields': [
                'instance',
                'role',
                'is_active',
            ]
        }),
        ('Timestamps', {
            'fields': [
                'activated_at',
                'deactivated_at',
            ],
        }),
    ]

    def get_readonly_fields(self, request, obj=None):
        """
        Make instance and azure_oid readonly after initial creation.
        """
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:  # Editing existing object
            readonly.extend(['instance', 'azure_oid'])
        return readonly


@admin.register(AITokenUsage)
class AITokenUsageAdmin(admin.ModelAdmin):
    """Admin interface for AITokenUsage model."""

    list_display = [
        'instance',
        'model',
        'tokens_in',
        'tokens_out',
        'total_tokens',
        'week_start',
        'month',
        'requested_at',
    ]
    list_filter = ['model', 'week_start', 'month', 'instance__customer']
    search_fields = [
        'instance__display_name',
        'instance__customer__company_name',
        'model',
    ]
    readonly_fields = [
        'id',
        'instance',
        'model',
        'tokens_in',
        'tokens_out',
        'total_tokens',
        'week_start',
        'month',
        'requested_at',
    ]
    date_hierarchy = 'requested_at'
    ordering = ['-requested_at']

    def has_add_permission(self, request):
        """Prevent manual creation of token usage records."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent editing of token usage records."""
        return False

    def total_tokens(self, obj):
        """Display total tokens (in + out) in the admin."""
        return obj.tokens_in + obj.tokens_out
    total_tokens.short_description = 'Total Tokens'


@admin.register(InstanceHeartbeat)
class InstanceHeartbeatAdmin(admin.ModelAdmin):
    """Admin interface for InstanceHeartbeat model."""

    list_display = [
        'instance',
        'version',
        'active_users',
        'url',
        'ip_address',
        'received_at',
    ]
    list_filter = ['version', 'instance__customer', 'received_at']
    search_fields = [
        'instance__display_name',
        'instance__customer__company_name',
        'url',
        'version',
        'ip_address',
    ]
    readonly_fields = [
        'id',
        'instance',
        'url',
        'version',
        'active_users',
        'ip_address',
        'received_at',
    ]
    date_hierarchy = 'received_at'
    ordering = ['-received_at']

    def has_add_permission(self, request):
        """Prevent manual creation of heartbeat records."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent editing of heartbeat records."""
        return False

