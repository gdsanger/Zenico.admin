import uuid
from django.db import models

from customers.models import SLUG_VALIDATOR


class Order(models.Model):
    """
    Bestellung von der Homepage (Zenico.web).

    Puffer zwischen Bestellung und Zahlungseingang: Ein Order-Objekt wird beim
    Absenden des Bestellformulars angelegt (`pending_payment`) und eine
    Stripe-Checkout-Session erstellt. Kunde und Instanz entstehen erst NACH
    erfolgreicher Zahlung durch den Stripe-Webhook (separates Issue) — hier
    wird nichts davon angelegt.
    """

    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment'),
        ('paid', 'Paid'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
    ]

    BILLING_INTERVAL_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]

    # Status, die eine gewünschte Slug noch belegen (Race-Schutz gegen
    # Doppelbestellungen auf denselben Slug).
    OPEN_STATUSES = ['pending_payment', 'paid']

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Bestelldetails
    plan = models.ForeignKey(
        'customers.Plan',
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name='plan',
    )
    user_seats = models.PositiveIntegerField(verbose_name='user seats')
    ai_addon = models.BooleanField(default=False, verbose_name='AI addon')
    billing_interval = models.CharField(
        max_length=10,
        choices=BILLING_INTERVAL_CHOICES,
        default='monthly',
        verbose_name='billing interval',
        help_text='Determines which Stripe price (monthly/yearly) is used at checkout',
    )
    slug = models.SlugField(
        max_length=10,
        validators=[SLUG_VALIDATOR],
        verbose_name='desired slug',
        help_text='2-10 lowercase alphanumeric characters. Wird bei Zahlung zum Customer-Slug.',
    )

    # Firmen-/Kontaktdaten (analog Customer)
    company_name = models.CharField(max_length=200, verbose_name='company name')
    contact_name = models.CharField(max_length=200, verbose_name='contact name')
    contact_email = models.EmailField(verbose_name='contact email')
    contact_phone = models.CharField(max_length=30, blank=True, verbose_name='contact phone')

    # Rechnungsdaten (analog Customer)
    billing_email = models.EmailField(verbose_name='billing email')
    billing_address = models.CharField(max_length=255, blank=True, verbose_name='billing address')
    billing_city = models.CharField(max_length=100, blank=True, verbose_name='billing city')
    billing_postal_code = models.CharField(max_length=20, blank=True, verbose_name='billing postal code')
    billing_country = models.CharField(
        max_length=2,
        default='DE',
        verbose_name='billing country',
        help_text='ISO 3166-1 alpha-2 country code',
    )
    vat_id = models.CharField(max_length=30, blank=True, verbose_name='VAT ID')

    terms_accepted = models.BooleanField(default=False, verbose_name='terms accepted')

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending_payment',
        verbose_name='status',
    )
    stripe_checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Stripe checkout session ID',
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug', 'status']),
            models.Index(fields=['stripe_checkout_session_id']),
        ]

    def __str__(self):
        return f"{self.company_name} ({self.slug}) — {self.status}"
