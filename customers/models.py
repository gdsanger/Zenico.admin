import uuid
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


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
