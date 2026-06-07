"""
Stripe helper functions for billing operations.
"""

from datetime import datetime

from django.conf import settings

from core.services.stripe import get_stripe


def _get_ai_addon_price_id(subscription):
    """Return the Stripe price ID used for the AI addon."""
    price_id = getattr(settings, 'STRIPE_AI_ADDON_PRICE_ID', '') or ''
    if price_id:
        return price_id
    return subscription.plan.stripe_price_id_ai


def _cancel_ai_addon_stripe(instance) -> str:
    """
    Entfernt KI-Addon Subscription Item zum Periodenende.
    Gibt Datum des Periodenendes zurück.
    """
    subscription = instance.customer.active_subscription
    if not subscription or not subscription.stripe_subscription_id:
        raise ValueError('No active subscription found')

    stripe_api = get_stripe()

    sub = stripe_api.Subscription.retrieve(subscription.stripe_subscription_id)
    ai_price_id = _get_ai_addon_price_id(subscription)

    ai_item = next(
        (item for item in sub['items']['data']
         if item['price']['id'] == ai_price_id),
        None
    )

    if not ai_item:
        raise ValueError('KI-Addon nicht in Subscription gefunden.')

    stripe_api.SubscriptionItem.delete(
        ai_item['id'],
        proration_behavior='none',
    )

    return datetime.fromtimestamp(
        sub['current_period_end']
    ).strftime('%Y-%m-%d')
