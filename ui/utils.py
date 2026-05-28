from decimal import Decimal
from customers.models import Subscription


def calculate_mrr():
    """
    Calculate Monthly Recurring Revenue (MRR) from all active subscriptions.
    Returns the total MRR as a Decimal.
    """
    mrr = Decimal('0.00')

    active_subscriptions = Subscription.objects.filter(
        stripe_status__in=['active', 'trialing']
    ).select_related('plan')

    for subscription in active_subscriptions:
        # Calculate MRR for this subscription
        user_mrr = subscription.user_seats_total * subscription.plan.price_per_user
        instance_mrr = subscription.instance_seats_total * subscription.plan.price_per_instance
        ai_mrr = subscription.plan.price_ai_addon if subscription.ai_addon_active else Decimal('0.00')

        mrr += user_mrr + instance_mrr + ai_mrr

    return mrr


def calculate_mrr_for_customer(customer):
    """
    Calculate MRR for a specific customer.
    Returns the MRR as a Decimal.
    """
    subscription = customer.active_subscription
    if not subscription:
        return Decimal('0.00')

    user_mrr = subscription.user_seats_total * subscription.plan.price_per_user
    instance_mrr = subscription.instance_seats_total * subscription.plan.price_per_instance
    ai_mrr = subscription.plan.price_ai_addon if subscription.ai_addon_active else Decimal('0.00')

    return user_mrr + instance_mrr + ai_mrr


def calculate_customer_growth(timeframe_days=30):
    """
    Calculate customer growth for the given timeframe.
    Returns the number of new customers.
    """
    from django.utils import timezone
    from datetime import timedelta
    from customers.models import Customer

    cutoff_date = timezone.now() - timedelta(days=timeframe_days)
    new_customers = Customer.objects.filter(
        created_at__gte=cutoff_date,
        status='active'
    ).count()

    return new_customers
