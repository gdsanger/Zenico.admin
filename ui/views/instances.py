from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from datetime import date

from instances.models import Instance, AITokenUsage, get_week_start
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

        # AI Token Usage Data
        week_start_date = get_week_start()
        ai_tokens_used_this_week = AITokenUsage.objects.filter(
            instance=instance,
            week_start=week_start_date
        ).aggregate(
            total_in=Sum('tokens_in'),
            total_out=Sum('tokens_out')
        )

        tokens_in = ai_tokens_used_this_week['total_in'] or 0
        tokens_out = ai_tokens_used_this_week['total_out'] or 0
        total_tokens_this_week = tokens_in + tokens_out

        # AI weekly limit (default 200k, should be configurable per plan)
        ai_weekly_limit = 200000 if instance.subscription and instance.subscription.ai_addon_active else 0
        ai_tokens_remaining = max(0, ai_weekly_limit - total_tokens_this_week)

        # Calculate percentage
        if ai_weekly_limit > 0:
            ai_usage_percentage = (total_tokens_this_week / ai_weekly_limit) * 100
        else:
            ai_usage_percentage = 0

        # Calculate next Monday for reset date
        next_monday = week_start_date + timezone.timedelta(days=7)

        context['ai_tokens_used_this_week'] = total_tokens_this_week
        context['ai_weekly_limit'] = ai_weekly_limit
        context['ai_tokens_remaining'] = ai_tokens_remaining
        context['ai_usage_percentage'] = ai_usage_percentage
        context['ai_week_resets'] = next_monday

        # Monthly token usage (last 6 months)
        monthly_usage = []
        today = date.today()
        for i in range(6):
            # Calculate first day of month (going back i months)
            year = today.year
            month = today.month - i
            while month <= 0:
                month += 12
                year -= 1
            month_date = date(year, month, 1)

            usage = AITokenUsage.objects.filter(
                instance=instance,
                month=month_date
            ).aggregate(
                tokens_in_sum=Sum('tokens_in'),
                tokens_out_sum=Sum('tokens_out')
            )

            tokens_in_month = usage['tokens_in_sum'] or 0
            tokens_out_month = usage['tokens_out_sum'] or 0
            total_month = tokens_in_month + tokens_out_month

            if total_month > 0:  # Only include months with usage
                monthly_usage.append({
                    'month': month_date.strftime('%b %Y'),
                    'tokens_in': tokens_in_month,
                    'tokens_out': tokens_out_month,
                    'total': total_month,
                })

        context['ai_monthly_usage'] = monthly_usage

        # Heartbeat status
        if instance.last_heartbeat:
            time_diff = timezone.now() - instance.last_heartbeat
            hours_ago = int(time_diff.total_seconds() / 3600)
            if hours_ago < 1:
                context['heartbeat_status'] = 'vor weniger als 1 Std.'
            elif hours_ago == 1:
                context['heartbeat_status'] = 'vor 1 Std.'
            else:
                context['heartbeat_status'] = f'vor {hours_ago} Std.'
        else:
            context['heartbeat_status'] = 'Nie'

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
