"""
Django Admin for AI Models
"""

from django.contrib import admin
from django.utils.html import format_html
from ai.models import (
    AIProvider,
    AIModel,
    AIAgent,
    AIJobsHistory,
    AITokenBudget,
)


@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
    """Admin interface for AIProvider."""

    list_display = ('name', 'provider_type', 'active', 'created_at')
    list_filter = ('provider_type', 'active')
    search_fields = ('name',)
    readonly_fields = ('id', 'created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('name', 'provider_type', 'active')
        }),
        ('API Configuration', {
            'fields': ('organization_id',),
            'description': 'API key is encrypted and managed separately.'
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        """Handle API key encryption on save."""
        # Note: API key should be set via set_api_key() method
        # This admin just provides basic CRUD
        super().save_model(request, obj, form, change)


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    """Admin interface for AIModel."""

    list_display = (
        'name',
        'provider',
        'model_id',
        'input_price_display',
        'output_price_display',
        'is_default',
        'active'
    )
    list_filter = ('provider__provider_type', 'active', 'is_default')
    search_fields = ('name', 'model_id')
    readonly_fields = ('id', 'created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('provider', 'name', 'model_id', 'active', 'is_default')
        }),
        ('Pricing (USD per 1M tokens)', {
            'fields': ('input_price_per_1m_tokens', 'output_price_per_1m_tokens')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def input_price_display(self, obj):
        """Display input price."""
        if obj.input_price_per_1m_tokens:
            return f'${obj.input_price_per_1m_tokens}/1M'
        return '-'

    input_price_display.short_description = 'Input Price'

    def output_price_display(self, obj):
        """Display output price."""
        if obj.output_price_per_1m_tokens:
            return f'${obj.output_price_per_1m_tokens}/1M'
        return '-'

    output_price_display.short_description = 'Output Price'


@admin.register(AIAgent)
class AIAgentAdmin(admin.ModelAdmin):
    """Admin interface for AIAgent."""

    list_display = (
        'name',
        'provider',
        'model',
        'cache_enabled',
        'active',
        'updated_at'
    )
    list_filter = ('active', 'cache_enabled', 'provider__provider_type')
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'active')
        }),
        ('Provider & Model', {
            'fields': ('provider', 'model')
        }),
        ('Prompts', {
            'fields': ('role', 'task'),
            'description': 'Role is the system prompt, Task is the user prompt template.'
        }),
        ('Generation Settings', {
            'fields': ('temperature', 'max_tokens')
        }),
        ('Cache Configuration', {
            'fields': ('cache_enabled', 'cache_ttl_seconds', 'cache_version')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AIJobsHistory)
class AIJobsHistoryAdmin(admin.ModelAdmin):
    """Admin interface for AIJobsHistory."""

    list_display = (
        'agent',
        'instance_link',
        'provider',
        'model',
        'status_badge',
        'tokens_display',
        'costs_display',
        'duration_display',
        'timestamp'
    )
    list_filter = ('status', 'provider__provider_type', 'from_cache', 'timestamp')
    search_fields = ('agent', 'instance__display_name', 'error_message')
    readonly_fields = (
        'id',
        'agent',
        'instance',
        'provider',
        'model',
        'status',
        'input_tokens',
        'output_tokens',
        'costs',
        'duration_ms',
        'error_message',
        'timestamp',
        'from_cache'
    )
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        """Job history is read-only."""
        return False

    def has_change_permission(self, request, obj=None):
        """Job history is read-only."""
        return False

    def instance_link(self, obj):
        """Display instance as link."""
        if obj.instance:
            return format_html(
                '<a href="/admin/instances/instance/{}/change/">{}</a>',
                obj.instance.id,
                obj.instance.display_name
            )
        return '-'

    instance_link.short_description = 'Instance'

    def status_badge(self, obj):
        """Display status with color."""
        colors = {
            'Completed': 'green',
            'Error': 'red',
            'Pending': 'orange',
            'Cached': 'blue',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.status
        )

    status_badge.short_description = 'Status'

    def tokens_display(self, obj):
        """Display token usage."""
        if obj.input_tokens or obj.output_tokens:
            return f'{obj.input_tokens or 0} in / {obj.output_tokens or 0} out'
        return '-'

    tokens_display.short_description = 'Tokens'

    def costs_display(self, obj):
        """Display costs."""
        if obj.costs:
            return f'${obj.costs:.6f}'
        return '-'

    costs_display.short_description = 'Costs (USD)'

    def duration_display(self, obj):
        """Display duration."""
        if obj.duration_ms:
            return f'{obj.duration_ms} ms'
        return '-'

    duration_display.short_description = 'Duration'


@admin.register(AITokenBudget)
class AITokenBudgetAdmin(admin.ModelAdmin):
    """Admin interface for AITokenBudget."""

    list_display = (
        'instance_link',
        'weekly_limit',
        'tokens_used_week',
        'tokens_remaining_display',
        'usage_percentage',
        'week_start',
        'updated_at'
    )
    list_filter = ('week_start',)
    search_fields = ('instance__display_name', 'instance__slug')
    readonly_fields = (
        'id',
        'instance',
        'tokens_used_week',
        'week_start',
        'updated_at',
        'tokens_remaining_display',
        'usage_percentage'
    )

    fields = (
        'instance',
        'weekly_limit',
        'tokens_used_week',
        'tokens_remaining_display',
        'usage_percentage',
        'week_start',
        'updated_at'
    )

    def has_add_permission(self, request):
        """Budgets are created automatically."""
        return False

    def instance_link(self, obj):
        """Display instance as link."""
        return format_html(
            '<a href="/admin/instances/instance/{}/change/">{}</a>',
            obj.instance.id,
            obj.instance.display_name
        )

    instance_link.short_description = 'Instance'

    def tokens_remaining_display(self, obj):
        """Display remaining tokens."""
        remaining = obj.tokens_remaining
        if remaining <= 0:
            return format_html('<span style="color: red; font-weight: bold;">0 (EXHAUSTED)</span>')
        return f'{remaining:,}'

    tokens_remaining_display.short_description = 'Tokens Remaining'

    def usage_percentage(self, obj):
        """Display usage as percentage."""
        if obj.weekly_limit == 0:
            return '0%'
        percentage = (obj.tokens_used_week / obj.weekly_limit) * 100
        color = 'green'
        if percentage >= 90:
            color = 'red'
        elif percentage >= 70:
            color = 'orange'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            percentage
        )

    usage_percentage.short_description = 'Usage %'
