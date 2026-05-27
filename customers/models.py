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
        ('starter', 'Starter'),
        ('professional', 'Professional'),
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
        TODO: Implement when instances app is ready.
        """
        return None

    @property
    def active_subscription(self):
        """
        Returns the active subscription for this customer.
        TODO: Implement when billing app is ready.
        """
        return None

    @property
    def is_active(self):
        """
        Returns True if the customer status is 'active'.
        """
        return self.status == 'active'
