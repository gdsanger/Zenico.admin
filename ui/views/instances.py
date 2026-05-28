from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages

from instances.models import Instance
from ui.decorators import role_required


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class InstanceListView(ListView):
    """
    Instance list view with filters.
    """
    model = Instance
    template_name = 'ui/instances/list.html'
    context_object_name = 'instances'
    paginate_by = 25

    def get_queryset(self):
        queryset = Instance.objects.select_related('customer', 'subscription').order_by('-created_at')

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
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class InstanceDetailView(DetailView):
    """
    Instance detail view.
    """
    model = Instance
    template_name = 'ui/instances/detail.html'
    context_object_name = 'instance'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = self.object

        # Get user licenses
        context['user_licenses'] = instance.user_licenses.order_by('-is_active', 'email')

        # Get audit logs for this instance
        from audit.models import AuditLog
        context['audit_logs'] = AuditLog.objects.filter(
            instance_id=instance.id
        ).order_by('-created_at')[:10]

        return context


@login_required
@role_required('superadmin', 'support')
def instance_api_key_reveal(request, pk):
    """
    HTMX endpoint to reveal the API key.
    """
    instance = get_object_or_404(Instance, pk=pk)

    return JsonResponse({
        'api_key': instance.api_key
    })


@login_required
@role_required('superadmin', 'support')
@require_POST
def instance_api_key_regenerate(request, pk):
    """
    Regenerate the API key for an instance.
    """
    instance = get_object_or_404(Instance, pk=pk)
    old_key = instance.api_key[:10] + '...'
    new_key = instance.regenerate_api_key()

    # Log the action
    from audit.models import AuditLog
    AuditLog.objects.create(
        customer=instance.customer,
        instance_id=instance.id,
        actor_email=request.user.email,
        action='instance.api_key_regenerated',
        resource_type='Instance',
        resource_id=str(instance.id),
        note=f'API key regenerated for {instance.fqdn}'
    )

    messages.success(request, f'API Key für {instance.fqdn} wurde neu generiert.')
    return JsonResponse({
        'success': True,
        'new_key': new_key
    })
