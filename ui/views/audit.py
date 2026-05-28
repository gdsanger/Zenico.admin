from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.http import HttpResponse
import csv

from audit.models import AuditLog
from ui.decorators import role_required


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class AuditLogListView(ListView):
    """
    Audit log list view with filters.
    """
    model = AuditLog
    template_name = 'ui/audit/log.html'
    context_object_name = 'audit_logs'
    paginate_by = 50

    def get_queryset(self):
        queryset = AuditLog.objects.select_related('customer').order_by('-created_at')

        # Filter by action
        action = self.request.GET.get('action', '')
        if action:
            queryset = queryset.filter(action__icontains=action)

        # Filter by customer
        customer_id = self.request.GET.get('customer', '')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_action'] = self.request.GET.get('action', '')
        context['current_customer'] = self.request.GET.get('customer', '')
        return context


@login_required
@role_required('superadmin', 'support')
def audit_export_csv(request):
    """
    Export audit log as CSV.
    """
    # Get filtered queryset
    queryset = AuditLogListView().get_queryset()

    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="audit_log_export.csv"'

    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'Actor', 'Action', 'Resource Type', 'Resource ID', 'Customer', 'Note'])

    for log in queryset:
        writer.writerow([
            log.created_at.isoformat(),
            log.actor_email,
            log.action,
            log.resource_type,
            log.resource_id,
            log.customer.company_name if log.customer else '',
            log.note
        ])

    return response
