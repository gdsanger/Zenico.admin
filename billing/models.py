import uuid
from django.db import models
from customers.models import Customer


class StripeEvent(models.Model):
    """
    Stripe webhook event model for idempotent processing.
    Each event is stored immediately upon receipt, then processed asynchronously.
    The stripe_event_id ensures no duplicate processing occurs.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stripe_events',
        verbose_name='customer',
        help_text='Customer may not be known when event is received'
    )
    stripe_event_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Stripe event ID',
        help_text='Unique Stripe event identifier (e.g., evt_xxx)'
    )
    event_type = models.CharField(
        max_length=100,
        verbose_name='event type',
        help_text='Stripe event type (e.g., customer.subscription.created)'
    )
    payload = models.JSONField(
        verbose_name='payload',
        help_text='Complete Stripe event payload'
    )
    processed = models.BooleanField(
        default=False,
        verbose_name='processed',
        help_text='Whether this event has been processed'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='error message',
        help_text='Error message if processing failed'
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='received at'
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='processed at'
    )

    class Meta:
        verbose_name = 'Stripe Event'
        verbose_name_plural = 'Stripe Events'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['processed', 'received_at'], name='billing_stripe_event_queue'),
            models.Index(fields=['event_type'], name='billing_stripe_event_type'),
        ]

    def __str__(self):
        status = "✓" if self.processed else "⏳"
        return f"{status} {self.event_type} ({self.stripe_event_id})"
