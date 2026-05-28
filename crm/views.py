"""
CRM views for managing contacts and notes.
"""

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone

from crm.models import Contact, ContactNote
from customers.models import Customer
from ui.decorators import role_required
from core.services.audit import AuditService, AuditAction


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class ContactListView(ListView):
    """
    Contact list view with search and filters.
    """
    model = Contact
    template_name = 'ui/crm/list.html'
    context_object_name = 'contacts'
    paginate_by = 25

    def get_queryset(self):
        queryset = Contact.objects.select_related('assigned_to', 'converted_to').order_by('-created_at')

        # Search
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(company__icontains=search)
            )

        # Filter by status
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['current_status'] = self.request.GET.get('status', '')

        # Count by status for filter tabs
        context['status_counts'] = {
            'all': Contact.objects.count(),
            'new': Contact.objects.filter(status='new').count(),
            'in_progress': Contact.objects.filter(status='in_progress').count(),
            'converted': Contact.objects.filter(status='converted').count(),
            'closed': Contact.objects.filter(status='closed').count(),
        }

        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class ContactDetailView(DetailView):
    """
    Contact detail view with notes.
    """
    model = Contact
    template_name = 'ui/crm/detail.html'
    context_object_name = 'contact'
    pk_url_kwarg = 'contact_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contact = self.object

        # Get notes
        context['notes'] = contact.contact_notes.select_related('author').order_by('-created_at')

        return context


@login_required
@role_required('superadmin', 'support')
@require_POST
def add_contact_note(request, contact_id):
    """
    Add a note to a contact via HTMX.
    """
    contact = get_object_or_404(Contact, id=contact_id)

    note_text = request.POST.get('note', '').strip()

    if not note_text:
        return JsonResponse({'error': 'Note text is required'}, status=400)

    # Create note
    note = ContactNote.objects.create(
        contact=contact,
        author=request.user,
        note=note_text
    )

    # Log audit
    AuditService.log(
        action=AuditAction.CONTACT_NOTE_ADDED,
        resource_type='ContactNote',
        resource_id=str(note.id),
        actor_email=request.user.email,
        after={
            'contact': contact.email,
            'note': note_text[:100],
        },
        note=f'Note added to contact {contact.email}'
    )

    # Return rendered note HTML
    return render(request, 'ui/crm/partials/note_item.html', {'note': note})


@login_required
@role_required('superadmin', 'support')
@require_POST
def update_contact_status(request, contact_id):
    """
    Update contact status via HTMX.
    """
    contact = get_object_or_404(Contact, id=contact_id)

    new_status = request.POST.get('status', '').strip()

    if new_status not in ['new', 'in_progress', 'converted', 'closed']:
        return JsonResponse({'error': 'Invalid status'}, status=400)

    old_status = contact.status
    contact.status = new_status
    contact.save()

    # Log audit
    AuditService.log(
        action=AuditAction.CONTACT_UPDATED,
        resource_type='Contact',
        resource_id=str(contact.id),
        actor_email=request.user.email,
        before={'status': old_status},
        after={'status': new_status},
        note=f'Contact status changed from {old_status} to {new_status}'
    )

    # Return rendered status badge
    return render(request, 'ui/crm/partials/status_badge.html', {'contact': contact})


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class ConvertToCustomerView(CreateView):
    """
    Convert a contact to a customer.
    Pre-fills form with contact data.
    """
    model = Customer
    template_name = 'ui/crm/convert_to_customer.html'
    fields = [
        'slug', 'company_name', 'contact_name', 'contact_email',
        'contact_phone', 'billing_email', 'billing_address',
        'billing_city', 'billing_postal_code', 'billing_country', 'vat_id'
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contact_id = self.kwargs.get('contact_id')
        context['contact'] = get_object_or_404(Contact, id=contact_id)
        return context

    def get_initial(self):
        """Pre-fill form with contact data."""
        contact_id = self.kwargs.get('contact_id')
        contact = get_object_or_404(Contact, id=contact_id)

        return {
            'company_name': contact.company,
            'contact_name': contact.full_name,
            'contact_email': contact.email,
            'contact_phone': contact.phone,
            'billing_email': contact.email,
        }

    def form_valid(self, form):
        # Create customer
        customer = form.save()

        # Update contact
        contact_id = self.kwargs.get('contact_id')
        contact = get_object_or_404(Contact, id=contact_id)
        contact.status = 'converted'
        contact.converted_to = customer
        contact.save()

        # Log audit
        AuditService.log(
            action=AuditAction.CONTACT_CONVERTED,
            resource_type='Contact',
            resource_id=str(contact.id),
            actor_email=self.request.user.email,
            after={
                'customer_slug': customer.slug,
                'customer_name': customer.company_name,
            },
            note=f'Contact {contact.email} converted to customer {customer.slug}'
        )

        messages.success(
            self.request,
            f'Kontakt erfolgreich in Kunde {customer.company_name} konvertiert.'
        )

        return redirect('ui:customer-detail', slug=customer.slug)

