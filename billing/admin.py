from django.contrib import admin
from .models import StripeEvent, Invoice


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    """Admin interface for StripeEvent model."""

    list_display = [
        'stripe_event_id',
        'event_type',
        'customer',
        'processed',
        'received_at',
        'processed_at'
    ]
    list_filter = ['processed', 'event_type', 'received_at']
    search_fields = ['stripe_event_id', 'event_type', 'customer__company_name']
    readonly_fields = ['id', 'received_at', 'stripe_event_id', 'event_type', 'payload']

    fieldsets = [
        ('Event Information', {
            'fields': ['id', 'stripe_event_id', 'event_type', 'received_at']
        }),
        ('Processing Status', {
            'fields': ['processed', 'processed_at', 'error_message']
        }),
        ('Related Data', {
            'fields': ['customer']
        }),
        ('Payload', {
            'fields': ['payload'],
            'classes': ['collapse'],
        }),
    ]

    def has_add_permission(self, request):
        """Prevent manual creation of events in admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of events in admin."""
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """Admin interface for Invoice model."""

    list_display = [
        'stripe_invoice_id',
        'customer',
        'subscription',
        'amount_due',
        'amount_paid',
        'currency',
        'status',
        'due_date',
        'created_at'
    ]
    list_filter = ['status', 'currency', 'created_at', 'due_date']
    search_fields = [
        'stripe_invoice_id',
        'customer__company_name',
        'customer__slug'
    ]
    readonly_fields = [
        'id',
        'stripe_invoice_id',
        'created_at',
        'updated_at'
    ]
    date_hierarchy = 'created_at'

    fieldsets = [
        ('Invoice Information', {
            'fields': [
                'id',
                'stripe_invoice_id',
                'status',
                'created_at',
                'updated_at'
            ]
        }),
        ('Related Data', {
            'fields': ['customer', 'subscription']
        }),
        ('Amounts', {
            'fields': [
                'amount_due',
                'amount_paid',
                'currency'
            ]
        }),
        ('Dates', {
            'fields': [
                'period_start',
                'period_end',
                'due_date',
                'paid_at'
            ]
        }),
        ('Stripe URLs', {
            'fields': [
                'stripe_hosted_url',
                'stripe_pdf_url'
            ],
            'classes': ['collapse'],
        }),
    ]

    def has_add_permission(self, request):
        """Prevent manual creation of invoices in admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of invoices in admin."""
        return False
