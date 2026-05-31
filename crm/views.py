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

from crm.models import Contact, ContactNote, EducationRequest
from crm.education_service import EducationRequestService
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
        q = self.request.GET.get('q', '')
        if q:
            queryset = queryset.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(email__icontains=q) |
                Q(company__icontains=q)
            )

        # Filter by status
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
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

    def render_to_response(self, context, **response_kwargs):
        # If HTMX request, return only the rows partial
        if self.request.headers.get('HX-Request'):
            return render(self.request, 'ui/crm/partials/contact_rows.html', context)
        return super().render_to_response(context, **response_kwargs)


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

        # Get available admins for assignment
        from accounts.models import AdminUser
        context['admins'] = AdminUser.objects.filter(role__in=['superadmin', 'support']).order_by('email')

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


@login_required
@role_required('superadmin', 'support')
@require_POST
def create_contact(request):
    """
    Create a contact manually via HTMX.
    """
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    company = request.POST.get('company', '').strip()
    message = request.POST.get('message', '').strip()
    salutation = request.POST.get('salutation', '').strip()
    newsletter_consent = request.POST.get('newsletter_consent') == 'on'

    if not first_name or not last_name or not email:
        return JsonResponse({'error': 'First name, last name, and email are required'}, status=400)

    # Create contact
    contact = Contact.objects.create(
        source='manual',
        status='new',
        salutation=salutation,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        company=company,
        message=message,
        newsletter_consent=newsletter_consent,
        assigned_to=request.user,
    )

    # Create system note
    ContactNote.objects.create(
        contact=contact,
        author=None,  # System note
        note='Kontakt manuell erstellt.'
    )

    # Log audit
    AuditService.log(
        action=AuditAction.CONTACT_CREATED,
        resource_type='Contact',
        resource_id=str(contact.id),
        actor_email=request.user.email,
        after={
            'email': contact.email,
            'name': contact.full_name,
            'source': 'manual',
        },
        note=f'Contact {contact.email} manually created'
    )

    # Return rendered row HTML
    return render(request, 'ui/crm/partials/contact_rows.html', {'contacts': [contact]})


@login_required
@role_required('superadmin', 'support')
@require_POST
def assign_contact(request, contact_id):
    """
    Assign contact to admin user via HTMX.
    """
    contact = get_object_or_404(Contact, id=contact_id)

    admin_id = request.POST.get('admin_id', '').strip()

    if admin_id:
        from accounts.models import AdminUser
        admin = get_object_or_404(AdminUser, id=admin_id)
        contact.assigned_to = admin
    else:
        contact.assigned_to = None

    contact.save()

    # Log audit
    AuditService.log(
        action=AuditAction.CONTACT_UPDATED,
        resource_type='Contact',
        resource_id=str(contact.id),
        actor_email=request.user.email,
        after={'assigned_to': admin.email if admin_id else None},
        note=f'Contact assigned to {admin.email if admin_id else "nobody"}'
    )

    return JsonResponse({'success': True, 'assigned_to': admin.email if admin_id else None})


@login_required
@role_required('superadmin', 'support')
def get_note_form(request, contact_id):
    """
    Return note form partial via HTMX.
    """
    contact = get_object_or_404(Contact, id=contact_id)
    return render(request, 'ui/crm/partials/note_form.html', {'contact': contact})


# ============================================================================
# Education Request Views
# ============================================================================

@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class EducationRequestListView(ListView):
    """
    Education request list view with status filters.
    """
    model = EducationRequest
    template_name = 'ui/crm/education/list.html'
    context_object_name = 'requests'
    paginate_by = 25

    def get_queryset(self):
        queryset = EducationRequest.objects.select_related('coupon', 'reviewed_by').order_by('-created_at')

        # Filter by status
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)

        # Search
        q = self.request.GET.get('q', '')
        if q:
            queryset = queryset.filter(
                Q(institution_name__icontains=q) |
                Q(email__icontains=q)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        context['current_status'] = self.request.GET.get('status', '')

        # Count by status for filter tabs
        context['status_counts'] = {
            'all': EducationRequest.objects.count(),
            'pending': EducationRequest.objects.filter(status='pending').count(),
            'approved': EducationRequest.objects.filter(status='approved').count(),
            'rejected': EducationRequest.objects.filter(status='rejected').count(),
        }

        return context

    def render_to_response(self, context, **response_kwargs):
        # If HTMX request, return only the rows partial
        if self.request.headers.get('HX-Request'):
            return render(self.request, 'ui/crm/education/partials/request_rows.html', context)
        return super().render_to_response(context, **response_kwargs)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class EducationRequestDetailView(DetailView):
    """
    Education request detail view with approve/reject actions.
    """
    model = EducationRequest
    template_name = 'ui/crm/education/detail.html'
    context_object_name = 'education_request'
    pk_url_kwarg = 'request_id'


@login_required
@role_required('superadmin', 'support')
@require_POST
def approve_education_request(request, request_id):
    """
    Approve education request and create coupon.
    """
    education_request = get_object_or_404(EducationRequest, id=request_id)

    # Check if already processed
    if education_request.status != 'pending':
        messages.error(request, 'Diese Anfrage wurde bereits bearbeitet.')
        return redirect('ui:education_request_detail', request_id=request_id)

    try:
        # Approve request (creates coupon + sends email)
        coupon = EducationRequestService.approve(education_request, request.user)

        messages.success(
            request,
            f'Anfrage genehmigt! Coupon {coupon.code} wurde erstellt und an {education_request.email} gesendet.'
        )
    except Exception as e:
        messages.error(request, f'Fehler beim Genehmigen: {str(e)}')

    return redirect('ui:education_request_detail', request_id=request_id)


@login_required
@role_required('superadmin', 'support')
@require_POST
def reject_education_request(request, request_id):
    """
    Reject education request with optional reason.
    """
    education_request = get_object_or_404(EducationRequest, id=request_id)

    # Check if already processed
    if education_request.status != 'pending':
        messages.error(request, 'Diese Anfrage wurde bereits bearbeitet.')
        return redirect('ui:education_request_detail', request_id=request_id)

    # Get rejection reason from form
    reason = request.POST.get('reason', '').strip()

    try:
        # Reject request (sends email)
        EducationRequestService.reject(education_request, request.user, reason)

        messages.success(
            request,
            f'Anfrage abgelehnt. Eine Benachrichtigung wurde an {education_request.email} gesendet.'
        )
    except Exception as e:
        messages.error(request, f'Fehler beim Ablehnen: {str(e)}')

    return redirect('ui:education_request_detail', request_id=request_id)

