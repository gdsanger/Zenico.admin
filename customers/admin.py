from django.contrib import admin
from .models import Plan, Customer, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """Admin interface for Plan model."""

    list_display = [
        'display_name',
        'name',
        'price_per_user',
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
                'price_ai_addon',
                'ai_addon_available',
            ]
        }),
        ('Stripe Integration', {
            'fields': [
                'stripe_product_id',
                'stripe_price_id_user',
                'stripe_price_id_user_yearly',
                'stripe_price_id_instance',
                'stripe_price_id_ai',
                'stripe_price_id_ai_yearly',
            ],
            'classes': ['collapse'],
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """Admin interface for Customer model."""

    list_display = [
        'company_name',
        'slug',
        'status',
        'contact_email',
        'billing_country',
        'created_at',
    ]
    list_filter = ['status', 'billing_country', 'created_at']
    search_fields = ['company_name', 'slug', 'contact_email', 'billing_email', 'vat_id']
    readonly_fields = ['id', 'created_at', 'updated_at']

    fieldsets = [
        ('Basic Information', {
            'fields': ['id', 'slug', 'company_name', 'status', 'notes']
        }),
        ('Contact Information', {
            'fields': ['contact_name', 'contact_email', 'contact_phone']
        }),
        ('Billing Information', {
            'fields': [
                'billing_email',
                'billing_address',
                'billing_city',
                'billing_postal_code',
                'billing_country',
                'vat_id',
            ]
        }),
        ('Stripe Integration', {
            'fields': ['stripe_customer_id'],
            'classes': ['collapse'],
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]

    def get_readonly_fields(self, request, obj=None):
        """
        Make slug readonly after initial creation to prevent accidental changes.
        """
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:  # Editing existing object
            readonly.append('slug')
        return readonly


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin interface for Subscription model."""

    list_display = [
        'customer',
        'plan',
        'stripe_status',
        'user_seats_total',
        'instance_seats_total',
        'ai_addon_active',
        'current_period_end',
        'created_at',
    ]
    list_filter = ['stripe_status', 'ai_addon_active', 'created_at']
    search_fields = [
        'customer__company_name',
        'customer__slug',
        'stripe_subscription_id',
        'plan__display_name'
    ]
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
    ]

    fieldsets = [
        ('Basic Information', {
            'fields': ['id', 'customer', 'plan', 'stripe_subscription_id', 'stripe_status']
        }),
        ('Seat Allocation', {
            'fields': [
                'user_seats_total',
                'instance_seats_total',
                'ai_addon_active',
            ]
        }),
        ('Billing Period', {
            'fields': [
                'current_period_start',
                'current_period_end',
                'trial_end',
                'cancelled_at',
            ]
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]
