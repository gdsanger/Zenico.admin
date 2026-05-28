import uuid
from django.db import models
from customers.models import Customer


class AuditLog(models.Model):
    """
    Append-only audit log for all relevant system actions.
    Records are never updated or deleted. Attempts to update will raise ValueError.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name='customer',
        help_text='Associated customer (if applicable)'
    )
    instance_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name='instance ID',
        help_text='Instance UUID (no FK to avoid circular imports)'
    )
    actor_email = models.EmailField(
        verbose_name='actor email',
        help_text='Email of the actor performing the action, or "system" for automated actions'
    )
    actor_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='actor IP',
        help_text='IP address of the actor'
    )
    action = models.CharField(
        max_length=100,
        verbose_name='action',
        help_text='Action performed (e.g., customer.created, instance.provisioned)'
    )
    resource_type = models.CharField(
        max_length=50,
        verbose_name='resource type',
        help_text='Type of resource affected (e.g., Customer, Instance)'
    )
    resource_id = models.CharField(
        max_length=100,
        verbose_name='resource ID',
        help_text='ID of the resource affected'
    )
    before = models.JSONField(
        null=True,
        blank=True,
        verbose_name='before',
        help_text='State before the action (if applicable)'
    )
    after = models.JSONField(
        null=True,
        blank=True,
        verbose_name='after',
        help_text='State after the action (if applicable)'
    )
    note = models.TextField(
        blank=True,
        verbose_name='note',
        help_text='Additional notes or context'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='created at'
    )

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'created_at'], name='audit_cust_created'),
            models.Index(fields=['action'], name='audit_action'),
            models.Index(fields=['resource_type', 'resource_id'], name='audit_resource'),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor_email} at {self.created_at}"

    def save(self, *args, **kwargs):
        """
        Override save to prevent updates on existing records.
        AuditLog is append-only - updates are not allowed.
        """
        if self.pk is not None:
            # Check if this object already exists in the database
            try:
                AuditLog.objects.get(pk=self.pk)
                # If we get here, the object exists and this is an update attempt
                raise ValueError("AuditLog records are append-only and cannot be updated.")
            except AuditLog.DoesNotExist:
                # Object doesn't exist yet, proceed with save
                pass
        super().save(*args, **kwargs)
