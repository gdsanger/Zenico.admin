"""
EducationRequestService - Manages approval and rejection of education discount requests.

Handles coupon generation and email notifications for education requests.
"""

import logging
import random
import string
from typing import Optional
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal

from crm.models import EducationRequest
from billing.models import Coupon
from billing.coupon_service import CouponService
from core.services.mail import MailService
from core.services.audit import AuditService, AuditAction
from django.conf import settings

logger = logging.getLogger(__name__)


class EducationRequestService:
    """
    Service for managing education discount requests.
    Handles approval with coupon generation and rejection with notifications.
    """

    @staticmethod
    def _generate_coupon_code(institution_name: str) -> str:
        """
        Generate unique coupon code in format: EDU-{SLUG}-{RANDOM4}

        Args:
            institution_name: Name of the institution

        Returns:
            str: Generated coupon code (e.g., "EDU-TUMU-X7K2")

        Side effects:
            - Checks for collision with existing coupons
            - Retries up to 10 times if collision occurs
        """
        # Create slug from institution name (max 10 chars)
        slug = slugify(institution_name)[:10].upper()

        # Try up to 10 times to generate a unique code
        for _ in range(10):
            # Generate random 4-character suffix
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            code = f"EDU-{slug}-{random_suffix}"

            # Check if code already exists
            if not Coupon.objects.filter(code=code).exists():
                return code

        # If all attempts failed, add timestamp to ensure uniqueness
        timestamp = str(int(timezone.now().timestamp()))[-4:]
        return f"EDU-{slug}-{timestamp}"

    @staticmethod
    @transaction.atomic
    def approve(request: EducationRequest, reviewed_by) -> Coupon:
        """
        Approve education request and create 50% discount coupon.

        Args:
            request: EducationRequest to approve
            reviewed_by: AdminUser who approved the request

        Returns:
            Coupon: The created coupon

        Side effects:
            - Generates unique coupon code
            - Creates Coupon with 50% discount
            - Creates Stripe coupon + promotion code
            - Updates request status to 'approved'
            - Sends approval email with coupon code
            - Creates audit log entry

        Raises:
            Exception: If coupon creation or email sending fails
        """
        # 1. Generate unique coupon code
        coupon_code = EducationRequestService._generate_coupon_code(request.institution_name)

        # 2. Create local coupon
        coupon = Coupon.objects.create(
            code=coupon_code,
            name=f"Education — {request.institution_name}",
            type='percent',
            discount_percent=Decimal('50.00'),
            duration='forever',
            max_redemptions=1,  # One redemption per institution
            is_active=True,
        )

        # 3. Create Stripe coupon + promotion code
        try:
            CouponService.create_stripe_coupon(coupon)
        except Exception as e:
            logger.error(f'Failed to create Stripe coupon for education request {request.id}: {e}')
            # Delete local coupon if Stripe creation failed
            coupon.delete()
            raise

        # 4. Link coupon to request
        request.coupon = coupon
        request.status = 'approved'
        request.reviewed_by = reviewed_by
        request.reviewed_at = timezone.now()
        request.save()

        # 5. Send approval email to applicant
        email_sent = MailService.send_template(
            to=request.email,
            template='education_request_approved',
            context={
                'institution_name': request.institution_name,
                'coupon_code': coupon_code,
                'discount_percent': '50',
            },
            subject_override=f'🎓 Ihr Bildungsrabatt wurde genehmigt'
        )

        if not email_sent:
            logger.warning(f'Failed to send approval email for education request {request.id}')

        # 6. Log audit action
        AuditService.log(
            action=AuditAction.EDUCATION_REQUEST_APPROVED,
            resource_type='EducationRequest',
            resource_id=str(request.id),
            actor_email=reviewed_by.email,
            after={
                'institution_name': request.institution_name,
                'email': request.email,
                'coupon_code': coupon_code,
                'discount': '50%',
                'email_sent': email_sent,
            },
            note=f'Education request approved for {request.institution_name}. Coupon: {coupon_code}'
        )

        logger.info(f'Approved education request {request.id} for {request.institution_name}. Coupon: {coupon_code}')
        return coupon

    @staticmethod
    @transaction.atomic
    def reject(
        request: EducationRequest,
        reviewed_by,
        reason: str = "",
    ) -> None:
        """
        Reject education request with optional reason.

        Args:
            request: EducationRequest to reject
            reviewed_by: AdminUser who rejected the request
            reason: Optional rejection reason (stored in notes)

        Side effects:
            - Updates request status to 'rejected'
            - Stores rejection reason in notes
            - Sends rejection email to applicant
            - Creates audit log entry
        """
        # 1. Update request status
        request.status = 'rejected'
        request.reviewed_by = reviewed_by
        request.reviewed_at = timezone.now()

        if reason:
            request.notes = reason

        request.save()

        # 2. Send rejection email
        email_sent = MailService.send_template(
            to=request.email,
            template='education_request_rejected',
            context={
                'institution_name': request.institution_name,
                'reason': reason,
            },
            subject_override='Ihre Bewerbung für den Zenico-Bildungsrabatt'
        )

        if not email_sent:
            logger.warning(f'Failed to send rejection email for education request {request.id}')

        # 3. Log audit action
        AuditService.log(
            action=AuditAction.EDUCATION_REQUEST_REJECTED,
            resource_type='EducationRequest',
            resource_id=str(request.id),
            actor_email=reviewed_by.email,
            after={
                'institution_name': request.institution_name,
                'email': request.email,
                'reason': reason,
                'email_sent': email_sent,
            },
            note=f'Education request rejected for {request.institution_name}'
        )

        logger.info(f'Rejected education request {request.id} for {request.institution_name}')
