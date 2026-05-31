import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
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


class Coupon(models.Model):
    """
    Coupon model for discount management.
    Supports percentage and fixed discounts with flexible duration rules.
    """

    TYPE_CHOICES = [
        ('percent', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]

    DURATION_CHOICES = [
        ('repeating', 'Repeating'),  # For N months
        ('forever', 'Forever'),       # Permanent discount
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='code',
        help_text='Unique coupon code (e.g., RESELLER2026)'
    )
    name = models.CharField(
        max_length=200,
        verbose_name='name',
        help_text='Internal name for identification'
    )
    type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        verbose_name='discount type'
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal('0.01')),
            MaxValueValidator(Decimal('100.00'))
        ],
        verbose_name='discount percentage',
        help_text='Percentage discount (0.01 - 100.00)'
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='discount amount',
        help_text='Fixed discount amount in EUR'
    )
    duration = models.CharField(
        max_length=10,
        choices=DURATION_CHOICES,
        verbose_name='duration'
    )
    duration_in_months = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='duration in months',
        help_text='Number of months for repeating discount'
    )
    max_redemptions = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='maximum redemptions',
        help_text='Maximum number of times this code can be redeemed (null = unlimited)'
    )
    redemptions_count = models.PositiveIntegerField(
        default=0,
        verbose_name='redemptions count',
        help_text='Current number of redemptions'
    )
    valid_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='valid from',
        help_text='Start date for validity (null = immediately valid)'
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='valid until',
        help_text='End date for validity (null = no expiration)'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='active',
        help_text='Whether this coupon can be used'
    )
    stripe_coupon_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Stripe coupon ID',
        help_text='Stripe coupon ID (co_...)'
    )
    stripe_promotion_code_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Stripe promotion code ID',
        help_text='Stripe promotion code ID (promo_...)'
    )
    created_by = models.ForeignKey(
        'accounts.AdminUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_coupons',
        verbose_name='created by'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Coupon'
        verbose_name_plural = 'Coupons'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code'], name='billing_coupon_code'),
            models.Index(fields=['is_active', 'valid_until'], name='billing_coupon_validity'),
        ]

    def __str__(self):
        if self.type == 'percent':
            discount_str = f"{self.discount_percent}%"
        else:
            discount_str = f"{self.discount_amount}€"
        return f"{self.code} - {discount_str}"

    def clean(self):
        """
        Validate coupon fields based on type and duration.
        """
        super().clean()

        # Validate discount type
        if self.type == 'percent':
            if not self.discount_percent:
                raise ValidationError({
                    'discount_percent': 'Percentage discount requires discount_percent.'
                })
            if self.discount_amount:
                raise ValidationError({
                    'discount_amount': 'Percentage discount should not have discount_amount.'
                })
        elif self.type == 'fixed':
            if not self.discount_amount:
                raise ValidationError({
                    'discount_amount': 'Fixed discount requires discount_amount.'
                })
            if self.discount_percent:
                raise ValidationError({
                    'discount_percent': 'Fixed discount should not have discount_percent.'
                })

        # Validate duration
        if self.duration == 'repeating':
            if not self.duration_in_months:
                raise ValidationError({
                    'duration_in_months': 'Repeating discount requires duration_in_months.'
                })
        elif self.duration == 'forever':
            if self.duration_in_months:
                raise ValidationError({
                    'duration_in_months': 'Forever discount should not have duration_in_months.'
                })

        # Validate date range
        if self.valid_from and self.valid_until:
            if self.valid_from >= self.valid_until:
                raise ValidationError({
                    'valid_until': 'Valid until must be after valid from.'
                })

    @property
    def is_valid(self):
        """
        Check if the coupon is currently valid and can be used.

        Returns:
            bool: True if coupon is valid and can be redeemed
        """
        now = timezone.now()

        # Check if active
        if not self.is_active:
            return False

        # Check valid_from date
        if self.valid_from and now < self.valid_from:
            return False

        # Check valid_until date
        if self.valid_until and now > self.valid_until:
            return False

        # Check max redemptions
        if self.max_redemptions is not None and self.redemptions_count >= self.max_redemptions:
            return False

        return True

    @property
    def discount_display(self):
        """
        Format discount for display in UI.

        Returns:
            str: Formatted discount string
        """
        if self.type == 'percent':
            return f"{self.discount_percent}%"
        else:
            return f"{self.discount_amount} €"

    @property
    def duration_display(self):
        """
        Format duration for display in UI.

        Returns:
            str: Formatted duration string
        """
        if self.duration == 'forever':
            return 'Dauerhaft'
        else:
            months = self.duration_in_months or 0
            return f'{months} {"Monat" if months == 1 else "Monate"}'

    @property
    def redemptions_display(self):
        """
        Format redemptions count for display in UI.

        Returns:
            str: Formatted redemptions string
        """
        if self.max_redemptions is None:
            return f'{self.redemptions_count} / ∞'
        else:
            return f'{self.redemptions_count} / {self.max_redemptions}'

    @property
    def status_badge(self):
        """
        Get status badge class for UI display.

        Returns:
            str: Bootstrap badge class
        """
        if not self.is_active:
            return 'secondary'
        if not self.is_valid:
            return 'danger'
        return 'success'

    @property
    def status_text(self):
        """
        Get status text for display.

        Returns:
            str: Status text
        """
        if not self.is_active:
            return 'Inaktiv'

        now = timezone.now()

        if self.valid_from and now < self.valid_from:
            return 'Noch nicht gültig'

        if self.valid_until and now > self.valid_until:
            return 'Abgelaufen'

        if self.max_redemptions is not None and self.redemptions_count >= self.max_redemptions:
            return 'Erschöpft'

        return 'Aktiv'


class CouponRedemption(models.Model):
    """
    Tracks coupon redemptions by customers.
    Ensures a customer can only redeem a specific coupon once.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        related_name='redemptions',
        verbose_name='coupon'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='coupon_redemptions',
        verbose_name='customer'
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coupon_redemptions',
        verbose_name='subscription'
    )
    redeemed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='redeemed at'
    )
    stripe_discount_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Stripe discount ID',
        help_text='Stripe discount ID on the subscription'
    )

    class Meta:
        verbose_name = 'Coupon Redemption'
        verbose_name_plural = 'Coupon Redemptions'
        ordering = ['-redeemed_at']
        constraints = [
            models.UniqueConstraint(
                fields=['coupon', 'customer'],
                name='unique_coupon_customer'
            )
        ]
        indexes = [
            models.Index(fields=['coupon', 'redeemed_at'], name='billing_redemption_coupon'),
            models.Index(fields=['customer', 'redeemed_at'], name='billing_redemption_customer'),
        ]

    def __str__(self):
        return f"{self.coupon.code} - {self.customer.company_name} ({self.redeemed_at.strftime('%d.%m.%Y')})"

