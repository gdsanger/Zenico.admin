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


def pending_education_count(request):
    """
    Context processor to add pending education request count to all templates.
    """
    if request.user.is_authenticated and request.user.role in ['superadmin', 'support']:
        from crm.models import EducationRequest
        count = EducationRequest.objects.filter(status='pending').count()
    else:
        count = 0

    return {'pending_education_count': count}


def stripe_active_mode(request):
    """
    Context processor exposing the active Stripe mode (test/live) sitewide, so
    "I thought I was in test mode" can't happen silently (see #912).
    """
    if request.user.is_authenticated and request.user.role in ['superadmin', 'billing']:
        from billing.models import StripeConfig
        mode = StripeConfig.get().mode
    else:
        mode = None

    return {'stripe_active_mode': mode}
