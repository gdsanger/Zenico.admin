from django.contrib import admin
from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """Admin interface for Plan model."""

    list_display = [
        'display_name',
        'name',
        'price_per_user',
        'price_per_instance',
        'price_ai_addon',
        'ai_addon_available',
        'is_active',
        'created_at',
    ]
    list_filter = ['is_active', 'ai_addon_available', 'name']
    search_fields = ['name', 'display_name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = [
        ('Basic Information', {
            'fields': ['id', 'name', 'display_name', 'description', 'is_active']
        }),
        ('Limits', {
            'fields': ['max_users_per_instance', 'max_instances']
        }),
        ('Pricing', {
            'fields': [
                'price_per_user',
                'price_per_instance',
                'price_ai_addon',
                'ai_addon_available',
            ]
        }),
        ('Stripe Integration', {
            'fields': [
                'stripe_product_id',
                'stripe_price_id_user',
                'stripe_price_id_instance',
                'stripe_price_id_ai',
            ],
            'classes': ['collapse'],
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]
