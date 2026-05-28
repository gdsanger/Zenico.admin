from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from customers.models import Customer, Subscription
from ui.decorators import role_required


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class CustomerListView(ListView):
    """
    Customer list view with search and filters.
    """
    model = Customer
    template_name = 'ui/customers/list.html'
    context_object_name = 'customers'
    paginate_by = 25

    def get_queryset(self):
        queryset = Customer.objects.select_related().order_by('-created_at')

        # Search
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                company_name__icontains=search
            ) | queryset.filter(
                slug__icontains=search
            ) | queryset.filter(
                contact_email__icontains=search
            )

        # Filter by status
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)

        # Filter for problems
        if self.request.GET.get('filter') == 'problems':
            queryset = queryset.filter(status__in=['suspended', 'past_due'])

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['current_status'] = self.request.GET.get('status', '')
        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class CustomerDetailView(DetailView):
    """
    Customer detail view.
    """
    model = Customer
    template_name = 'ui/customers/detail.html'
    context_object_name = 'customer'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object

        # Get related data
        context['instances'] = customer.instances.all().order_by('-is_master', 'slug')
        context['invoices'] = customer.invoices.order_by('-created_at')[:5]
        context['audit_logs'] = customer.audit_logs.order_by('-created_at')[:10]

        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class CustomerCreateView(CreateView):
    """
    Customer creation view.
    """
    model = Customer
    template_name = 'ui/customers/create.html'
    fields = [
        'slug', 'company_name', 'contact_name', 'contact_email',
        'contact_phone', 'billing_email', 'billing_address',
        'billing_city', 'billing_postal_code', 'billing_country', 'vat_id'
    ]

    def form_valid(self, form):
        messages.success(self.request, f'Kunde {form.instance.company_name} erfolgreich angelegt.')
        return super().form_valid(form)

    def get_success_url(self):
        return f'/customers/{self.object.slug}/'


@login_required
@role_required('superadmin', 'support')
def customer_check_slug(request):
    """
    HTMX endpoint to check slug availability.
    """
    slug = request.GET.get('slug', '')

    if not slug:
        return JsonResponse({'available': False, 'message': 'Slug darf nicht leer sein.'})

    # Check if slug already exists
    exists = Customer.objects.filter(slug=slug).exists()

    if exists:
        return JsonResponse({
            'available': False,
            'message': 'Dieser Slug ist bereits vergeben.'
        })
    else:
        return JsonResponse({
            'available': True,
            'message': 'Slug verfügbar ✓'
        })


@login_required
@role_required('superadmin', 'support')
@require_POST
def customer_suspend(request, slug):
    """
    Suspend a customer.
    """
    customer = get_object_or_404(Customer, slug=slug)
    customer.status = 'suspended'
    customer.save()

    messages.warning(request, f'Kunde {customer.company_name} wurde gesperrt.')
    return redirect('customer_detail', slug=slug)


@login_required
@role_required('superadmin', 'support')
@require_POST
def customer_reactivate(request, slug):
    """
    Reactivate a suspended customer.
    """
    customer = get_object_or_404(Customer, slug=slug)
    customer.status = 'active'
    customer.save()

    messages.success(request, f'Kunde {customer.company_name} wurde reaktiviert.')
    return redirect('customer_detail', slug=slug)
