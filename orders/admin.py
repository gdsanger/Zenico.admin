from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'slug', 'plan', 'user_seats', 'ai_addon', 'status', 'created_at')
    list_filter = ('status', 'ai_addon', 'plan')
    search_fields = ('company_name', 'slug', 'contact_email', 'billing_email', 'stripe_checkout_session_id')
    readonly_fields = ('id', 'stripe_checkout_session_id', 'created_at', 'updated_at')
    ordering = ('-created_at',)
