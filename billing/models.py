import uuid
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from customers.models import Customer, Subscription


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


class Invoice(models.Model):
    """
    Invoice model mirroring Stripe invoices locally.
    Enables display in admin and customer self-service without live Stripe API calls.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('open', 'Open'),
        ('paid', 'Paid'),
        ('void', 'Void'),
        ('uncollectible', 'Uncollectible'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='invoices',
        verbose_name='customer',
        help_text='Customer who owns this invoice'
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices',
        verbose_name='subscription',
        help_text='Associated subscription (if any)'
    )
    stripe_invoice_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Stripe invoice ID',
        help_text='Unique Stripe invoice identifier (e.g., in_xxx)'
    )
    stripe_hosted_url = models.URLField(
        blank=True,
        verbose_name='Stripe hosted URL',
        help_text='URL to view invoice on Stripe'
    )
    stripe_pdf_url = models.URLField(
        blank=True,
        verbose_name='Stripe PDF URL',
        help_text='URL to download invoice PDF'
    )
    amount_due = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='amount due',
        help_text='Total amount due on this invoice'
    )
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='amount paid',
        help_text='Total amount paid on this invoice'
    )
    currency = models.CharField(
        max_length=3,
        default='EUR',
        verbose_name='currency',
        help_text='ISO 4217 currency code'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        verbose_name='status',
        help_text='Current status of the invoice'
    )
    period_start = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='period start',
        help_text='Start of the billing period'
    )
    period_end = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='period end',
        help_text='End of the billing period'
    )
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='due date',
        help_text='Date the invoice is due'
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='paid at',
        help_text='Date the invoice was paid'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'status'], name='billing_inv_cust_stat'),
        ]

    def __str__(self):
        return f"{self.stripe_invoice_id} - {self.customer.company_name} ({self.status})"
