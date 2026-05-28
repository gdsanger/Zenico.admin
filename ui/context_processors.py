from customers.models import Customer


def alert_count(request):
    """
    Context processor to add alert count (past_due + suspended customers) to all templates.
    """
    if request.user.is_authenticated:
        count = Customer.objects.filter(
            status__in=['suspended']
        ).count()

        # Add past_due subscriptions
        from customers.models import Subscription
        past_due_count = Subscription.objects.filter(
            stripe_status='past_due'
        ).values('customer').distinct().count()

        count += past_due_count
    else:
        count = 0

    return {'alert_count': count}
