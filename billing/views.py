"""
Views for billing app.

Handles Stripe webhook endpoint.
"""

import logging
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.services.webhook import StripeWebhookHandler

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Stripe webhook endpoint.

    Receives, verifies, and processes Stripe webhook events.
    Returns 200 OK in all cases to prevent Stripe retries on non-signature errors.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    if not sig_header:
        logger.error('Missing Stripe signature header')
        return HttpResponse(status=400)

    try:
        # Process webhook
        StripeWebhookHandler.handle(payload, sig_header)
        return HttpResponse(status=200)

    except ValueError as e:
        # Invalid payload or signature
        logger.error(f'Invalid webhook request: {e}')
        return HttpResponse(status=400)

    except Exception as e:
        # Other errors - still return 200 to prevent Stripe retries
        logger.exception(f'Unexpected error processing webhook: {e}')
        return HttpResponse(status=200)

