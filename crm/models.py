import uuid
from django.db import models
from django.conf import settings


class Contact(models.Model):
    """
    Incoming contact requests from zenico.web and manually captured leads.
    """

    SOURCE_CHOICES = [
        ('web_contact', 'Web Contact'),
        ('manual', 'Manual'),
    ]

    STATUS_CHOICES = [
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('converted', 'Converted'),
        ('closed', 'Closed'),
    ]

    SALUTATION_CHOICES = [
        ('Herr', 'Herr'),
        ('Frau', 'Frau'),
        ('Divers', 'Divers'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, verbose_name='source')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name='status')
    salutation = models.CharField(max_length=10, choices=SALUTATION_CHOICES, blank=True, verbose_name='salutation')
    first_name = models.CharField(max_length=100, verbose_name='first name')
    last_name = models.CharField(max_length=100, verbose_name='last name')
    email = models.EmailField(verbose_name='email')
    phone = models.CharField(max_length=30, blank=True, verbose_name='phone')
    company = models.CharField(max_length=200, blank=True, verbose_name='company')
    message = models.TextField(blank=True, verbose_name='message', help_text='Original message from contact form')
    notes = models.TextField(blank=True, verbose_name='internal notes')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_contacts',
        verbose_name='assigned to'
    )
    converted_to = models.ForeignKey(
        'customers.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_from_contacts',
        verbose_name='converted to'
    )
    newsletter_consent = models.BooleanField(
        default=False,
        verbose_name='newsletter consent',
        help_text='Has checked newsletter consent on contact form'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP address',
        help_text='For GDPR traceability'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Contact'
        verbose_name_plural = 'Contacts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    @property
    def full_name(self):
        """Returns the full name of the contact."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_converted(self):
        """Returns True if the contact has been converted to a customer."""
        return self.converted_to is not None


class ContactNote(models.Model):
    """
    Chronological note/activity log per contact.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='contact_notes',
        verbose_name='contact'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contact_notes',
        verbose_name='author'
    )
    note = models.TextField(verbose_name='note')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')

    class Meta:
        verbose_name = 'Contact Note'
        verbose_name_plural = 'Contact Notes'
        ordering = ['-created_at']

    def __str__(self):
        return f"Note on {self.contact.full_name} at {self.created_at}"


class EducationRequest(models.Model):
    """
    Education discount requests from zenico.web.
    Institutions can apply for 50% discount on subscriptions.
    """

    INSTITUTION_TYPE_CHOICES = [
        ('university', 'University'),
        ('school', 'School'),
        ('nonprofit', 'Non-Profit'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_name = models.CharField(
        max_length=200,
        verbose_name='institution name',
        help_text='Name of the educational institution'
    )
    email = models.EmailField(
        verbose_name='email',
        help_text='Contact email address'
    )
    institution_type = models.CharField(
        max_length=50,
        choices=INSTITUTION_TYPE_CHOICES,
        default='other',
        verbose_name='institution type'
    )
    website = models.URLField(
        blank=True,
        verbose_name='website',
        help_text='Institution website'
    )
    description = models.TextField(
        blank=True,
        verbose_name='description',
        help_text='How the institution plans to use Zenico'
    )
    user_count = models.PositiveIntegerField(
        verbose_name='estimated user count',
        help_text='Estimated number of users'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP address',
        help_text='For GDPR traceability'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='status'
    )
    coupon = models.ForeignKey(
        'billing.Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='education_requests',
        verbose_name='coupon',
        help_text='Auto-created coupon when approved'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='internal notes',
        help_text='Internal notes for review'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_education_requests',
        verbose_name='reviewed by'
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='reviewed at'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='updated at')

    class Meta:
        verbose_name = 'Education Request'
        verbose_name_plural = 'Education Requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.institution_name} ({self.status})"

    @property
    def status_badge(self):
        """Get status badge class for UI display."""
        if self.status == 'pending':
            return 'warning'
        elif self.status == 'approved':
            return 'success'
        else:  # rejected
            return 'danger'

    @property
    def status_text(self):
        """Get localized status text."""
        status_map = {
            'pending': 'Offen',
            'approved': 'Genehmigt',
            'rejected': 'Abgelehnt',
        }
        return status_map.get(self.status, self.status)
