"""
Service functions for the instances app that go beyond simple model logic.
"""

import logging

from django.utils import timezone

from core.services.audit import AuditAction, AuditService
from core.services.mail import MailService

logger = logging.getLogger(__name__)


def send_instance_ready_mail(instance):
    """
    Send the "instance ready" email to the customer's contact address once,
    when an instance first becomes active.

    Idempotent: a no-op if the mail was already sent for this instance.
    Mail failures are logged but never raised — the caller (provisioning
    completion) must succeed regardless of mail delivery.
    """
    if instance.instance_ready_mail_sent_at is not None:
        return

    customer = instance.customer
    instance_url = f'https://{instance.fqdn}'

    try:
        sent = MailService.send_template(
            to=customer.contact_email,
            template='instance_ready',
            context={
                'contact_name': customer.contact_name,
                'instance_name': instance.display_name,
                'instance_url': instance_url,
            },
            subject_override='Ihre Zenico-Instanz ist bereit',
        )
    except Exception:
        logger.exception(
            'Exception while sending instance_ready mail for instance %s', instance.id
        )
        return

    if not sent:
        logger.error('Failed to send instance_ready mail for instance %s', instance.id)
        return

    instance.instance_ready_mail_sent_at = timezone.now()
    instance.save(update_fields=['instance_ready_mail_sent_at', 'updated_at'])

    AuditService.log(
        action=AuditAction.INSTANCE_READY_MAIL_SENT,
        resource_type='Instance',
        resource_id=str(instance.id),
        customer=customer,
        instance_id=instance.id,
        after={'to': customer.contact_email, 'instance_url': instance_url},
        note=f'Instance ready mail sent to {customer.contact_email}',
    )
