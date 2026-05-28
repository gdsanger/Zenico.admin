import uuid
import secrets
from django.db import models
from django.core.exceptions import ValidationError
from customers.models import Customer, Subscription, SLUG_VALIDATOR


class InstanceManager(models.Manager):
    """Custom manager for Instance model."""

    def create_master(self, customer, subscription, display_name, **kwargs):
        """
        Create a master instance for a customer.
        The slug is automatically set to match the customer's slug.
        """
        return self.create(
            customer=customer,
            subscription=subscription,
            slug=customer.slug,
            display_name=display_name,
            is_master=True,
            **kwargs
        )

    def create_sub_instance(self, customer, subscription, slug, display_name, **kwargs):
        """
        Create a sub-instance for a customer.
        The slug must be different from the customer's slug.
        """
        if slug == customer.slug:
            raise ValidationError(
                "Sub-instance slug cannot be the same as the customer slug. "
                "Use create_master() for master instances."
            )
        return self.create(
            customer=customer,
            subscription=subscription,
            slug=slug,
            display_name=display_name,
            is_master=False,
            **kwargs
        )


class Instance(models.Model):
    """
    Instance model representing a Zenico deployment.
    Each customer can have one master instance and multiple sub-instances.
    """

    STATUS_CHOICES = [
        ('provisioning', 'Provisioning'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('deprovisioned', 'Deprovisioned'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='instances',
        verbose_name='customer'
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name='instances',
        verbose_name='subscription'
    )
    slug = models.CharField(
        max_length=10,
        validators=[SLUG_VALIDATOR],
        verbose_name='slug',
        help_text='2-10 lowercase alphanumeric characters. For master instances, must match customer slug.'
    )
    display_name = models.CharField(max_length=200, verbose_name='display name')
    is_master = models.BooleanField(default=False, verbose_name='is master')
    server_host = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='server host',
        help_text='Hostname of the server where this instance is deployed'
    )
    db_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='database name'
    )
    db_user = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='database user'
    )
    api_key = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        verbose_name='API key',
        help_text='Auto-generated API key for instance authentication'
    )
    django_secret_key = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Django secret key'
    )
    version = models.CharField(
        max_length=30,
        blank=True,
        verbose_name='version',
        help_text='Zenico version running on this instance'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='provisioning',
        verbose_name='status'
    )
    user_seats = models.PositiveIntegerField(
        default=1,
        verbose_name='user seats',
        help_text='Number of user seats allocated to this instance'
    )
    ai_addon_active = models.BooleanField(
        default=False,
        verbose_name='AI addon active'
    )
    provisioned_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='provisioned at'
    )
    last_health_check = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='last health check'
    )
    health_check_ok = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='health check OK'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    objects = InstanceManager()

    class Meta:
        verbose_name = 'Instance'
        verbose_name_plural = 'Instances'
        ordering = ['customer', '-is_master', 'slug']
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'slug'],
                name='unique_slug_per_customer',
                violation_error_message='This slug is already used by another instance for this customer.'
            ),
            models.UniqueConstraint(
                fields=['customer', 'is_master'],
                condition=models.Q(is_master=True),
                name='unique_master_per_customer',
                violation_error_message='Each customer can have only one master instance.'
            ),
        ]

    def __str__(self):
        master_indicator = " [Master]" if self.is_master else ""
        return f"{self.customer.company_name} - {self.display_name}{master_indicator} ({self.slug})"

    def save(self, *args, **kwargs):
        """
        Override save to auto-generate api_key on first save.
        """
        if not self.api_key:
            # Generate a 48-character URL-safe token
            self.api_key = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def clean(self):
        """
        Validate instance before saving.
        - Master instances must have slug matching customer slug
        - Check user seats budget against subscription
        """
        super().clean()

        # Validate master slug matches customer slug
        if self.is_master and self.slug != self.customer.slug:
            raise ValidationError({
                'slug': f'Master instance slug must match customer slug "{self.customer.slug}".'
            })

        # Validate user seats budget when changing user_seats
        if self.customer_id and self.subscription_id:
            # Calculate total user seats used by other instances
            other_instances = Instance.objects.filter(
                customer=self.customer,
                status__in=['provisioning', 'active']
            ).exclude(pk=self.pk)

            other_seats = sum(inst.user_seats for inst in other_instances)
            total_seats = other_seats + self.user_seats

            available_seats = self.subscription.user_seats_total

            if total_seats > available_seats:
                raise ValidationError({
                    'user_seats': (
                        f'Not enough user seats available. '
                        f'Requested: {self.user_seats}, '
                        f'Already used: {other_seats}, '
                        f'Total available: {available_seats}'
                    )
                })

    @property
    def fqdn(self):
        """
        Returns the fully qualified domain name for this instance.
        Master: {customer.slug}.zenico.app
        Sub-instance: {instance.slug}.{customer.slug}.zenico.app
        """
        if self.is_master:
            return f"{self.customer.slug}.zenico.app"
        else:
            return f"{self.slug}.{self.customer.slug}.zenico.app"

    @property
    def is_active(self):
        """
        Returns True if the instance status is 'active'.
        """
        return self.status == 'active'

    def regenerate_api_key(self):
        """
        Regenerate the API key for this instance.
        Returns the new API key.
        """
        self.api_key = secrets.token_urlsafe(48)
        self.save(update_fields=['api_key', 'updated_at'])
        return self.api_key


class UserLicense(models.Model):
    """
    UserLicense model tracking which Azure users are licensed on which instance.
    Used as the basis for the license check API endpoint.
    """

    ROLE_CHOICES = [
        ('project_manager', 'Project Manager'),
        ('team_lead', 'Team Lead'),
        ('contributor', 'Contributor'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(
        Instance,
        on_delete=models.CASCADE,
        related_name='user_licenses',
        verbose_name='instance'
    )
    azure_oid = models.CharField(
        max_length=100,
        verbose_name='Azure AD Object ID',
        help_text='Azure AD Object ID of the user'
    )
    email = models.EmailField(verbose_name='email')
    display_name = models.CharField(max_length=150, verbose_name='display name')
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='contributor',
        verbose_name='role'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='active',
        help_text='Whether this license is currently active'
    )
    activated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='activated at'
    )
    deactivated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='deactivated at'
    )

    class Meta:
        verbose_name = 'User License'
        verbose_name_plural = 'User Licenses'
        ordering = ['instance', 'email']
        constraints = [
            models.UniqueConstraint(
                fields=['instance', 'azure_oid'],
                name='unique_azure_oid_per_instance',
                violation_error_message='This Azure user is already licensed on this instance.'
            ),
        ]

    def __str__(self):
        active_indicator = " [Active]" if self.is_active else " [Inactive]"
        return f"{self.display_name} ({self.email}) - {self.instance.display_name}{active_indicator}"

    def clean(self):
        """
        Validate user license before saving.
        - Check that activating this license doesn't exceed instance user_seats limit
        """
        super().clean()

        # Only validate when activating (is_active=True)
        if self.is_active and self.instance_id:
            # Count currently active licenses on this instance
            active_licenses = UserLicense.objects.filter(
                instance=self.instance,
                is_active=True
            ).exclude(pk=self.pk).count()

            # Check against instance's user_seats allocation
            if active_licenses >= self.instance.user_seats:
                raise ValidationError({
                    'is_active': (
                        f'Cannot activate license: instance has {self.instance.user_seats} user seats, '
                        f'and {active_licenses} are already in use.'
                    )
                })
