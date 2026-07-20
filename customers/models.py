import uuid
from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


# Slug validator for customer slugs (reusable by instances)
SLUG_VALIDATOR = RegexValidator(
    regex=r'^[a-z0-9]{2,10}$',
    message='Slug must be 2-10 lowercase alphanumeric characters (a-z, 0-9)',
    code='invalid_slug'
)


class Plan(models.Model):
    """
    Subscription plan model with pricing and Stripe references.
    Existing subscriptions remain unaffected when plans are modified.
    """

    PLAN_CHOICES = [
        ('standard', 'Standard'),
        ('enterprise', 'Enterprise'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        unique=True,
        verbose_name='plan name'
    )
    display_name = models.CharField(max_length=100, verbose_name='display name')
    description = models.TextField(blank=True, verbose_name='description')
    max_users_per_instance = models.PositiveIntegerField(
        default=0,
        verbose_name='max users per instance',
        help_text='0 = unlimited'
    )
    max_instances = models.PositiveIntegerField(
        default=0,
        verbose_name='max instances',
        help_text='0 = unlimited'
    )
    price_per_user = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='price per user',
        help_text='€/User/Month'
    )
    # Deprecated: the business model no longer bills per instance (user-seat +
    # optional AI addon only). Kept for schema/data continuity, not read anywhere.
    price_per_instance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='price per instance',
        help_text='€/Instance/Month'
    )
    price_ai_addon = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='price AI addon',
        help_text='€/AI-Addon/Month'
    )
    ai_addon_available = models.BooleanField(
        default=False,
        verbose_name='AI addon available'
    )
    # Single-set, not a test/live pair: Stripe products/prices are separate
    # objects per mode (StripeConfig.mode), so a given ID here is only valid
    # for whichever mode it was wired under. Switching StripeConfig.mode
    # test<->live does NOT repoint these — re-check/re-wire via the
    # Plan-Verdrahtung screen after every mode switch (see #912).
    stripe_product_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Stripe product ID'
    )
    stripe_price_id_user = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Stripe price ID (user)'
    )
    stripe_price_id_instance = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Stripe price ID (instance)'
    )
    stripe_price_id_ai = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Stripe price ID (AI)'
    )
    # Yearly counterparts of the two prices above (Stripe treats recurring
    # prices as interval-specific objects, so a yearly plan needs its own
    # price ID rather than reusing the monthly one — see #921). Left blank,
    # a plan simply isn't offered with yearly billing.
    stripe_price_id_user_yearly = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Stripe price ID (user, yearly)'
    )
    stripe_price_id_ai_yearly = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Stripe price ID (AI, yearly)'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='active',
        help_text='Inactive plans cannot be booked for new subscriptions'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Plan'
        verbose_name_plural = 'Plans'
        ordering = ['name']

    def __str__(self):
        return self.display_name

    def stripe_price_id_user_for_interval(self, billing_interval: str) -> str:
        """Return the wired user-license price ID for 'monthly' or 'yearly'."""
        if billing_interval == 'yearly':
            return self.stripe_price_id_user_yearly
        return self.stripe_price_id_user

    def stripe_price_id_ai_for_interval(self, billing_interval: str) -> str:
        """Return the wired AI-addon price ID for 'monthly' or 'yearly'."""
        if billing_interval == 'yearly':
            return self.stripe_price_id_ai_yearly
        return self.stripe_price_id_ai


class Customer(models.Model):
    """
    Core model for Zenico customers.
    The slug is immutable after initial creation and forms the basis for all instance FQDNs.
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(
        max_length=10,
        unique=True,
        validators=[SLUG_VALIDATOR],
        verbose_name='slug',
        help_text='2-10 lowercase alphanumeric characters. Immutable after creation.'
    )
    company_name = models.CharField(max_length=200, verbose_name='company name')
    contact_name = models.CharField(max_length=200, verbose_name='contact name')
    contact_email = models.EmailField(verbose_name='contact email')
    contact_phone = models.CharField(max_length=30, blank=True, verbose_name='contact phone')
    billing_email = models.EmailField(verbose_name='billing email')
    billing_address = models.CharField(max_length=255, verbose_name='billing address')
    billing_city = models.CharField(max_length=100, verbose_name='billing city')
    billing_postal_code = models.CharField(max_length=20, verbose_name='billing postal code')
    billing_country = models.CharField(
        max_length=2,
        default='DE',
        verbose_name='billing country',
        help_text='ISO 3166-1 alpha-2 country code'
    )
    vat_id = models.CharField(
        max_length=30,
        blank=True,
        verbose_name='VAT ID',
        help_text='Value Added Tax identification number'
    )
    stripe_customer_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Stripe customer ID'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='status'
    )
    # Coupon information (synced from Stripe)
    coupon_code = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='coupon code',
        help_text='Applied coupon code'
    )
    coupon_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='coupon description',
        help_text='Human-readable coupon description'
    )
    coupon_discount_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='coupon discount %',
        help_text='Discount percentage (if applicable)'
    )
    ai_addon_cancelled_at = models.DateField(
        null=True,
        blank=True,
        verbose_name='AI addon cancelled at',
        help_text='KI-Addon läuft bis zu diesem Datum',
    )
    notes = models.TextField(
        blank=True,
        verbose_name='internal notes',
        help_text='Internal notes, not visible to customer'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        ordering = ['company_name']

    def __str__(self):
        return f"{self.company_name} ({self.slug})"

    def clean(self):
        """
        Validate that the slug cannot be changed after initial save.
        """
        super().clean()
        if self.pk:  # Object exists in database
            try:
                original = Customer.objects.get(pk=self.pk)
                if original.slug != self.slug:
                    raise ValidationError({
                        'slug': 'Slug cannot be changed after creation.'
                    })
            except Customer.DoesNotExist:
                pass

    @property
    def master_instance(self):
        """
        Returns the master instance for this customer.
        """
        return self.instances.filter(is_master=True).first()

    @property
    def active_subscription(self):
        """
        Returns the active subscription for this customer.
        """
        return self.subscriptions.filter(
            stripe_status__in=['active', 'trialing']
        ).first()

    @property
    def is_active(self):
        """
        Returns True if the customer status is 'active'.
        """
        return self.status == 'active'

    @property
    def has_ai_addon(self):
        """
        Returns True if the customer has an active AI addon subscription.
        """
        subscription = self.active_subscription
        return subscription.ai_addon_active if subscription else False


class Subscription(models.Model):
    """
    Subscription model linking Customer and Plan, mirroring Stripe subscription state.
    Tracks seat allocations at the customer level.
    """

    STRIPE_STATUS_CHOICES = [
        ('active', 'Active'),
        ('trialing', 'Trialing'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
        ('unpaid', 'Unpaid'),
        ('incomplete', 'Incomplete'),
        ('incomplete_expired', 'Incomplete Expired'),
        ('paused', 'Paused'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        verbose_name='customer',
        related_name='subscriptions'
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        verbose_name='plan',
        help_text='Plan remains protected even if modified'
    )
    stripe_subscription_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Stripe subscription ID'
    )
    stripe_status = models.CharField(
        max_length=30,
        choices=STRIPE_STATUS_CHOICES,
        verbose_name='Stripe status'
    )
    user_seats_total = models.PositiveIntegerField(
        default=1,
        verbose_name='total user seats'
    )
    instance_seats_total = models.PositiveIntegerField(
        default=1,
        verbose_name='total instance seats'
    )
    ai_addon_active = models.BooleanField(
        default=False,
        verbose_name='AI addon active'
    )
    coupon = models.ForeignKey(
        'billing.Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscriptions',
        verbose_name='coupon',
        help_text='Applied coupon code for discount'
    )
    current_period_start = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='current period start'
    )
    current_period_end = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='current period end'
    )
    trial_end = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='trial end'
    )
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='cancelled at'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer.company_name} - {self.plan.display_name} ({self.stripe_status})"

    @property
    def is_active(self):
        """
        Returns True if subscription status is active or trialing.
        """
        return self.stripe_status in ['active', 'trialing']

    def used_user_seats(self):
        """
        Returns the sum of user_seats from all instances of this customer.
        """
        return self.customer.instances.filter(
            status__in=['provisioning', 'active']
        ).aggregate(total=models.Sum('user_seats'))['total'] or 0

    def available_user_seats(self):
        """
        Returns the number of available user seats.
        """
        return self.user_seats_total - self.used_user_seats()

    def used_instance_seats(self):
        """
        Returns the count of instances with status provisioning or active.
        """
        return self.customer.instances.filter(
            status__in=['provisioning', 'active']
        ).count()

    def available_instance_seats(self):
        """
        Returns the number of available instance seats.
        """
        return self.instance_seats_total - self.used_instance_seats()
