"""
AuditService - Central wrapper for append-only audit logging.

This service is the ONLY way to create AuditLog entries. Never call
AuditLog.objects.create() directly from anywhere else in the codebase.
"""

import uuid
from typing import Optional
from audit.models import AuditLog
from customers.models import Customer


class AuditAction:
    """
    Standard action constants for audit logging.
    Use these constants instead of hardcoding action strings.
    """

    # Customer
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_SUSPENDED = "customer.suspended"
    CUSTOMER_REACTIVATED = "customer.reactivated"
    CUSTOMER_CANCELLED = "customer.cancelled"

    # Instance
    INSTANCE_PROVISIONED = "instance.provisioned"
    INSTANCE_SUSPENDED = "instance.suspended"
    INSTANCE_REACTIVATED = "instance.reactivated"
    INSTANCE_DEPROVISIONED = "instance.deprovisioned"
    INSTANCE_SEATS_CHANGED = "instance.seats_changed"

    # Subscription
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_UPDATED = "subscription.updated"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    SEATS_CHANGED = "subscription.seats_changed"

    # API Key
    API_KEY_REGENERATED = "api_key.regenerated"

    # Instance Heartbeat
    INSTANCE_HEARTBEAT = "instance.heartbeat"
    INSTANCE_VERSION_CHANGED = "instance.version_changed"

    # AI
    AI_REQUEST_SUCCESS = "ai.request_success"
    AI_REQUEST_FAILED = "ai.request_failed"
    AI_ADDON_NOT_ACTIVE = "ai.addon_not_active"
    AI_TOKEN_LIMIT_EXCEEDED = "ai.token_limit_exceeded"

    # User License
    LICENSE_ACTIVATED = "user_license.activated"
    LICENSE_DEACTIVATED = "user_license.deactivated"

    # Mail
    MAIL_SENT = "mail.sent"
    MAIL_FAILED = "mail.failed"

    # Stripe
    STRIPE_WEBHOOK_RECEIVED = "stripe.webhook_received"
    STRIPE_WEBHOOK_PROCESSED = "stripe.webhook_processed"
    STRIPE_WEBHOOK_FAILED = "stripe.webhook_failed"

    # Orders
    ORDER_CREATED = "order.created"

    # CRM
    CONTACT_CREATED = "contact.created"
    CONTACT_UPDATED = "contact.updated"
    CONTACT_CONVERTED = "contact.converted"
    CONTACT_NOTE_ADDED = "contact.note_added"

    # Education Requests
    EDUCATION_REQUEST_CREATED = "education_request.created"
    EDUCATION_REQUEST_APPROVED = "education_request.approved"
    EDUCATION_REQUEST_REJECTED = "education_request.rejected"

    # Newsletter
    SUBSCRIBER_CREATED = "subscriber.created"
    SUBSCRIBER_CONFIRMED = "subscriber.confirmed"
    SUBSCRIBER_UNSUBSCRIBED = "subscriber.unsubscribed"
    CAMPAIGN_CREATED = "campaign.created"
    CAMPAIGN_SENT = "campaign.sent"
    SEQUENCE_ENROLLED = "sequence.enrolled"
    SEQUENCE_COMPLETED = "sequence.completed"



class AuditService:
    """
    Central service for audit logging.

    This is the only interface for creating audit log entries.
    All services that perform relevant actions should call AuditService.log()
    instead of directly creating AuditLog objects.
    """

    @staticmethod
    def log(
        action: str,
        resource_type: str,
        resource_id: str,
        actor_email: str = "system",
        actor_ip: Optional[str] = None,
        customer: Optional[Customer] = None,
        instance_id: Optional[uuid.UUID] = None,
        before: Optional[dict] = None,
        after: Optional[dict] = None,
        note: str = "",
    ) -> AuditLog:
        """
        Create an audit log entry.

        Args:
            action: Action performed (use AuditAction constants)
            resource_type: Type of resource affected (e.g., 'Customer', 'Instance')
            resource_id: ID of the resource affected
            actor_email: Email of the actor (default: 'system')
            actor_ip: IP address of the actor (optional)
            customer: Associated customer (optional)
            instance_id: Associated instance UUID (optional)
            before: State before the action (optional)
            after: State after the action (optional)
            note: Additional notes or context (optional)

        Returns:
            AuditLog: The created audit log entry

        Raises:
            ValidationError: If the audit log entry fails validation
        """
        audit_log = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_email=actor_email,
            actor_ip=actor_ip,
            customer=customer,
            instance_id=instance_id,
            before=before,
            after=after,
            note=note,
        )
        # Note: We don't call full_clean() here because actor_email may be 'system'
        # which is not a valid email but is allowed per model documentation
        audit_log.save()
        return audit_log
