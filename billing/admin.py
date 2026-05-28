from django.contrib import admin
from .models import StripeEvent


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
