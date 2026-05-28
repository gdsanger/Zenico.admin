import uuid
import secrets
from django.db import models
from django.conf import settings


class Subscriber(models.Model):
    """
    Newsletter subscribers. Each email address exists exactly once.
    The unsubscribe_token is the only key for the public unsubscribe link - no login needed.
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('unsubscribed', 'Unsubscribed'),
        ('bounced', 'Bounced'),
        ('complained', 'Complained'),
    ]

    SOURCE_CHOICES = [
        ('web_form', 'Web Form'),
        ('contact_form', 'Contact Form'),
        ('manual', 'Manual'),
        ('api', 'API'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, verbose_name='email')
    first_name = models.CharField(max_length=100, blank=True, verbose_name='first name')
    last_name = models.CharField(max_length=100, blank=True, verbose_name='last name')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name='status')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, verbose_name='source')
    unsubscribe_token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        verbose_name='unsubscribe token',
        help_text='Auto-generated via secrets.token_urlsafe'
    )
    subscribed_at = models.DateTimeField(auto_now_add=True, verbose_name='subscribed at')
    unsubscribed_at = models.DateTimeField(null=True, blank=True, verbose_name='unsubscribed at')
    contact = models.ForeignKey(
        'crm.Contact',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscribers',
        verbose_name='contact',
        help_text='Link if known'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP address',
        help_text='Subscription IP for GDPR'
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='confirmed at',
        help_text='For Double-Opt-In'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Subscriber'
        verbose_name_plural = 'Subscribers'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.status})"

    def save(self, *args, **kwargs):
        """Auto-generate unsubscribe_token if not set."""
        if not self.unsubscribe_token:
            self.unsubscribe_token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """Returns True if subscriber is active and confirmed."""
        return self.status == 'active' and self.confirmed_at is not None

    @property
    def full_name(self):
        """Returns the full name of the subscriber."""
        return f"{self.first_name} {self.last_name}".strip()


class Campaign(models.Model):
    """
    A newsletter campaign - one-time send to all active subscribers (or segment).
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('cancelled', 'Cancelled'),
    ]

    SEGMENT_CHOICES = [
        ('all', 'All'),
        ('leads', 'Leads'),
        ('customers', 'Customers'),
        ('manual', 'Manual'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name='name', help_text='Internal name')
    subject = models.CharField(max_length=300, verbose_name='subject', help_text='Email subject')
    preview_text = models.CharField(max_length=200, blank=True, verbose_name='preview text', help_text='Preview text in email client')
    html_body = models.TextField(verbose_name='HTML body', help_text='HTML content')
    text_body = models.TextField(blank=True, verbose_name='text body', help_text='Plaintext fallback')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='status')
    segment = models.CharField(
        max_length=20,
        choices=SEGMENT_CHOICES,
        default='all',
        verbose_name='segment',
        help_text='all: all active subscribers | leads: subscribers with linked Contact (not converted) | customers: subscribers who are also Customer (via email match) | manual: manually selected subscribers'
    )
    scheduled_at = models.DateTimeField(null=True, blank=True, verbose_name='scheduled at', help_text='Planned send time')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='sent at')
    recipient_count = models.PositiveIntegerField(default=0, verbose_name='recipient count', help_text='Filled on send')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaigns',
        verbose_name='created by'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Campaign'
        verbose_name_plural = 'Campaigns'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.status})"

    @property
    def is_editable(self):
        """Returns True if campaign can be edited (only draft)."""
        return self.status == 'draft'


class CampaignMail(models.Model):
    """
    Individual send of a campaign to a subscriber. Tracking at mail level.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('bounced', 'Bounced'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='campaign_mails',
        verbose_name='campaign'
    )
    subscriber = models.ForeignKey(
        Subscriber,
        on_delete=models.CASCADE,
        related_name='campaign_mails',
        verbose_name='subscriber'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='status')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='sent at')
    error_message = models.TextField(blank=True, verbose_name='error message')

    class Meta:
        verbose_name = 'Campaign Mail'
        verbose_name_plural = 'Campaign Mails'
        constraints = [
            models.UniqueConstraint(fields=['campaign', 'subscriber'], name='unique_campaign_subscriber')
        ]

    def __str__(self):
        return f"{self.campaign.name} → {self.subscriber.email} ({self.status})"


class AutomationSequence(models.Model):
    """
    An automation sequence - e.g., onboarding series after newsletter signup.
    """

    TRIGGER_CHOICES = [
        ('subscriber_confirmed', 'Subscriber Confirmed'),
        ('customer_created', 'Customer Created'),
        ('manual', 'Manual'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name='name')
    trigger = models.CharField(max_length=30, choices=TRIGGER_CHOICES, verbose_name='trigger')
    is_active = models.BooleanField(default=False, verbose_name='active')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Automation Sequence'
        verbose_name_plural = 'Automation Sequences'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"


class SequenceStep(models.Model):
    """
    A single step within a sequence.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sequence = models.ForeignKey(
        AutomationSequence,
        on_delete=models.CASCADE,
        related_name='steps',
        verbose_name='sequence'
    )
    order = models.PositiveIntegerField(verbose_name='order', help_text='Order within sequence')
    delay_days = models.PositiveIntegerField(default=0, verbose_name='delay days', help_text='Offset to previous step')
    subject = models.CharField(max_length=300, verbose_name='subject')
    preview_text = models.CharField(max_length=200, blank=True, verbose_name='preview text')
    html_body = models.TextField(verbose_name='HTML body')
    text_body = models.TextField(blank=True, verbose_name='text body')

    class Meta:
        verbose_name = 'Sequence Step'
        verbose_name_plural = 'Sequence Steps'
        ordering = ['sequence', 'order']
        constraints = [
            models.UniqueConstraint(fields=['sequence', 'order'], name='unique_sequence_order')
        ]

    def __str__(self):
        return f"{self.sequence.name} - Step {self.order}"


class SequenceEnrollment(models.Model):
    """
    Tracks where a subscriber is in a sequence.
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sequence = models.ForeignKey(
        AutomationSequence,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name='sequence'
    )
    subscriber = models.ForeignKey(
        Subscriber,
        on_delete=models.CASCADE,
        related_name='sequence_enrollments',
        verbose_name='subscriber'
    )
    current_step = models.PositiveIntegerField(default=0, verbose_name='current step')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name='status')
    enrolled_at = models.DateTimeField(auto_now_add=True, verbose_name='enrolled at')
    next_send_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='next send at',
        help_text='When the next step will be sent'
    )
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='completed at')

    class Meta:
        verbose_name = 'Sequence Enrollment'
        verbose_name_plural = 'Sequence Enrollments'
        ordering = ['-enrolled_at']
        constraints = [
            models.UniqueConstraint(fields=['sequence', 'subscriber'], name='unique_sequence_subscriber')
        ]

    def __str__(self):
        return f"{self.subscriber.email} → {self.sequence.name} ({self.status})"

    @property
    def is_active(self):
        """Returns True if enrollment is active."""
        return self.status == 'active'
