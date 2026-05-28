from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView

from customers.models import Subscription
from billing.models import Invoice, StripeEvent
from ui.decorators import role_required


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'billing'), name='dispatch')
class SubscriptionListView(ListView):
    """
    Subscription list view.
    """
    model = Subscription
    template_name = 'ui/billing/subscriptions.html'
    context_object_name = 'subscriptions'
    paginate_by = 25

    def get_queryset(self):
        return Subscription.objects.select_related('customer', 'plan').order_by('-created_at')


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'billing'), name='dispatch')
class InvoiceListView(ListView):
    """
    Invoice list view with filters.
    """
    model = Invoice
    template_name = 'ui/billing/invoices.html'
    context_object_name = 'invoices'
    paginate_by = 25

    def get_queryset(self):
        queryset = Invoice.objects.select_related('customer', 'subscription').order_by('-created_at')

        # Filter by status
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_status'] = self.request.GET.get('status', '')
        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'billing'), name='dispatch')
class StripeEventListView(ListView):
    """
    Stripe event list view with filters.
    """
    model = StripeEvent
    template_name = 'ui/billing/stripe_events.html'
    context_object_name = 'stripe_events'
    paginate_by = 25

    def get_queryset(self):
        queryset = StripeEvent.objects.select_related('customer').order_by('-received_at')

        # Filter by processed status
        if self.request.GET.get('unprocessed') == '1':
            queryset = queryset.filter(processed=False)
        elif self.request.GET.get('failed') == '1':
            queryset = queryset.filter(processed=True).exclude(error_message='')

        return queryset
