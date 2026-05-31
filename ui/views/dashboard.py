from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.db.models import Count, Q
from django.shortcuts import render

from customers.models import Customer, Subscription, Plan
from instances.models import Instance, UserLicense
from billing.models import StripeConfig
from audit.models import AuditLog
from ui.utils import calculate_mrr, calculate_customer_growth
from ui.decorators import role_required


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support', 'billing'), name='dispatch')
class DashboardView(TemplateView):
    """
    Dashboard view showing KPIs, recent customers, and activity feed.
    """
    template_name = 'ui/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check Stripe configuration completeness (superadmin only)
        if self.request.user.role == 'superadmin':
            config = StripeConfig.get()

            # Count unwired plans
            unwired_plans = Plan.objects.filter(
                Q(stripe_product_id='') |
                Q(stripe_price_id_user='') |
                Q(stripe_price_id_instance='')
            ).count()

            context['stripe_config_incomplete'] = not config.is_configured or unwired_plans > 0
            context['unwired_plans_count'] = unwired_plans

        # KPI calculations
        context['total_customers'] = Customer.objects.filter(status='active').count()
        context['new_customers_this_month'] = calculate_customer_growth(30)

        context['total_instances'] = Instance.objects.filter(status='active').count()
        context['provisioning_instances'] = Instance.objects.filter(status='provisioning').count()

        context['total_licenses'] = UserLicense.objects.filter(is_active=True).count()
        context['total_licenses_booked'] = UserLicense.objects.count()

        context['mrr'] = calculate_mrr()

        # Recent/problem customers (top 10)
        problem_customers = Customer.objects.filter(
            Q(status__in=['suspended']) |
            Q(subscriptions__stripe_status='past_due')
        ).distinct()[:5]

        recent_active_customers = Customer.objects.filter(
            status='active'
        ).exclude(
            id__in=problem_customers.values_list('id', flat=True)
        ).order_by('-created_at')[:5]

        context['dashboard_customers'] = list(problem_customers) + list(recent_active_customers)

        # Activity feed (last 15 audit log entries)
        context['activity_feed'] = AuditLog.objects.select_related(
            'customer'
        ).order_by('-created_at')[:15]

        return context


@login_required
@role_required('superadmin', 'support', 'billing')
def dashboard_kpis(request):
    """
    HTMX endpoint for KPI refresh.
    """
    context = {}
    context['total_customers'] = Customer.objects.filter(status='active').count()
    context['new_customers_this_month'] = calculate_customer_growth(30)
    context['total_instances'] = Instance.objects.filter(status='active').count()
    context['provisioning_instances'] = Instance.objects.filter(status='provisioning').count()
    context['total_licenses'] = UserLicense.objects.filter(is_active=True).count()
    context['total_licenses_booked'] = UserLicense.objects.count()
    context['mrr'] = calculate_mrr()

    return render(request, 'ui/partials/kpis.html', context)


@login_required
@role_required('superadmin', 'support', 'billing')
def dashboard_activity(request):
    """
    HTMX endpoint for activity feed refresh.
    """
    activity_feed = AuditLog.objects.select_related('customer').order_by('-created_at')[:15]
    return render(request, 'ui/partials/activity.html', {'activity_feed': activity_feed})
