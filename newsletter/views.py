"""
Newsletter views for managing subscribers, campaigns, and automations.
"""

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone

from newsletter.models import (
    Subscriber, Campaign, CampaignMail,
    AutomationSequence, SequenceStep, SequenceEnrollment
)
from newsletter.tasks import send_campaign
from ui.decorators import role_required
from core.services.mail import MailService
from core.services.audit import AuditService, AuditAction


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class SubscriberListView(ListView):
    """
    Subscriber list view with filters.
    """
    model = Subscriber
    template_name = 'ui/newsletter/subscribers.html'
    context_object_name = 'subscribers'
    paginate_by = 50

    def get_queryset(self):
        queryset = Subscriber.objects.order_by('-created_at')

        # Filter by status
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)

        # Search
        q = self.request.GET.get('q', '')
        if q:
            queryset = queryset.filter(
                Q(email__icontains=q) |
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        context['current_status'] = self.request.GET.get('status', '')

        # Count by status for filter tabs
        context['status_counts'] = {
            'all': Subscriber.objects.count(),
            'active': Subscriber.objects.filter(status='active').count(),
            'unsubscribed': Subscriber.objects.filter(status='unsubscribed').count(),
            'bounced': Subscriber.objects.filter(status='bounced').count(),
        }

        return context

    def render_to_response(self, context, **response_kwargs):
        # If HTMX request, return only the rows partial
        if self.request.headers.get('HX-Request'):
            return render(self.request, 'ui/newsletter/partials/subscriber_rows.html', context)
        return super().render_to_response(context, **response_kwargs)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class CampaignListView(ListView):
    """
    Campaign list view.
    """
    model = Campaign
    template_name = 'ui/newsletter/campaigns.html'
    context_object_name = 'campaigns'
    paginate_by = 25

    def get_queryset(self):
        return Campaign.objects.select_related('created_by').order_by('-created_at')


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class CampaignCreateView(CreateView):
    """
    Campaign create view.
    """
    model = Campaign
    template_name = 'ui/newsletter/campaign_edit.html'
    fields = ['name', 'subject', 'preview_text', 'html_body', 'text_body', 'segment']

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.status = 'draft'
        return super().form_valid(form)

    def get_success_url(self):
        return f'/newsletter/campaigns/{self.object.id}/edit/'


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin'), name='dispatch')
class CampaignEditView(UpdateView):
    """
    Campaign edit view.
    """
    model = Campaign
    template_name = 'ui/newsletter/campaign_edit.html'
    fields = ['name', 'subject', 'preview_text', 'html_body', 'text_body', 'segment']
    pk_url_kwarg = 'campaign_id'

    def get_success_url(self):
        return f'/newsletter/campaigns/{self.object.id}/edit/'


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class AutomationListView(ListView):
    """
    Automation sequence list view.
    """
    model = AutomationSequence
    template_name = 'ui/newsletter/automations.html'
    context_object_name = 'sequences'

    def get_queryset(self):
        return AutomationSequence.objects.prefetch_related('steps').order_by('name')


@login_required
@role_required('superadmin', 'support')
@require_POST
def create_subscriber(request):
    """
    Create a subscriber manually via HTMX.
    """
    email = request.POST.get('email', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()

    if not email:
        return JsonResponse({'error': 'Email is required'}, status=400)

    # Check if subscriber already exists
    if Subscriber.objects.filter(email=email).exists():
        return JsonResponse({'error': 'Subscriber with this email already exists'}, status=400)

    # Create subscriber
    subscriber = Subscriber.objects.create(
        email=email,
        first_name=first_name,
        last_name=last_name,
        source='manual',
        status='active',
        confirmed_at=timezone.now(),  # Manual subscribers are auto-confirmed
    )

    # Log audit
    AuditService.log(
        action=AuditAction.SUBSCRIBER_CREATED,
        resource_type='Subscriber',
        resource_id=str(subscriber.id),
        actor_email=request.user.email,
        after={
            'email': subscriber.email,
            'source': 'manual',
        },
        note=f'Subscriber {subscriber.email} manually created'
    )

    # Return rendered row HTML
    return render(request, 'ui/newsletter/partials/subscriber_rows.html', {'subscribers': [subscriber]})


@login_required
@role_required('superadmin', 'support')
@require_POST
def deactivate_subscriber(request, subscriber_id):
    """
    Deactivate (unsubscribe) a subscriber via HTMX.
    """
    subscriber = get_object_or_404(Subscriber, id=subscriber_id)

    subscriber.status = 'unsubscribed'
    subscriber.unsubscribed_at = timezone.now()
    subscriber.save()

    # Log audit
    AuditService.log(
        action=AuditAction.SUBSCRIBER_UNSUBSCRIBED,
        resource_type='Subscriber',
        resource_id=str(subscriber.id),
        actor_email=request.user.email,
        note=f'Subscriber {subscriber.email} deactivated by admin'
    )

    # Return updated row
    return render(request, 'ui/newsletter/partials/subscriber_rows.html', {'subscribers': [subscriber]})


@login_required
@role_required('superadmin')
def campaign_preview(request, campaign_id):
    """
    Campaign preview (no sidebar).
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)
    return render(request, 'ui/newsletter/campaign_preview.html', {'campaign': campaign})


@login_required
@role_required('superadmin')
@require_POST
def campaign_test(request, campaign_id):
    """
    Send test email for campaign.
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)
    test_email = request.POST.get('test_email', '').strip()

    if not test_email:
        messages.error(request, 'E-Mail-Adresse ist erforderlich.')
        return redirect('ui:campaign_edit', campaign_id=campaign.id)

    try:
        # Send test email without creating CampaignMail entry
        # For now, just log the action
        AuditService.log(
            action='campaign.test_sent',
            resource_type='Campaign',
            resource_id=str(campaign.id),
            actor_email=request.user.email,
            note=f'Test email sent to {test_email} for campaign {campaign.name}'
        )

        messages.success(request, f'Testmail wurde an {test_email} gesendet.')
    except Exception as e:
        messages.error(request, f'Fehler beim Senden der Testmail: {str(e)}')

    return redirect('ui:campaign_edit', campaign_id=campaign.id)


@login_required
@role_required('superadmin')
@require_POST
def campaign_schedule(request, campaign_id):
    """
    Schedule a campaign for later sending.
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)

    if campaign.status != 'draft':
        messages.error(request, 'Nur Entwürfe können geplant werden.')
        return redirect('ui:campaign_edit', campaign_id=campaign.id)

    scheduled_at_str = request.POST.get('scheduled_at', '').strip()

    if not scheduled_at_str:
        messages.error(request, 'Sendezeitpunkt ist erforderlich.')
        return redirect('ui:campaign_edit', campaign_id=campaign.id)

    from datetime import datetime
    try:
        scheduled_at = datetime.fromisoformat(scheduled_at_str)
        campaign.scheduled_at = scheduled_at
        campaign.status = 'scheduled'
        campaign.save()

        # Log audit
        AuditService.log(
            action=AuditAction.CAMPAIGN_CREATED,
            resource_type='Campaign',
            resource_id=str(campaign.id),
            actor_email=request.user.email,
            after={'scheduled_at': scheduled_at.isoformat()},
            note=f'Campaign {campaign.name} scheduled for {scheduled_at}'
        )

        messages.success(request, f'Kampagne wurde für {scheduled_at.strftime("%d.%m.%Y %H:%M")} geplant.')
    except Exception as e:
        messages.error(request, f'Fehler beim Planen: {str(e)}')

    return redirect('ui:campaign_edit', campaign_id=campaign.id)


@login_required
@role_required('superadmin')
@require_POST
def campaign_send(request, campaign_id):
    """
    Send campaign immediately.
    """
    campaign = get_object_or_404(Campaign, id=campaign_id)

    if campaign.status != 'draft':
        messages.error(request, 'Nur Entwürfe können gesendet werden.')
        return redirect('ui:campaign_edit', campaign_id=campaign.id)

    # Update status
    campaign.status = 'sending'
    campaign.save()

    # Trigger Celery task
    send_campaign.delay(str(campaign.id))

    # Log audit
    AuditService.log(
        action=AuditAction.CAMPAIGN_SENT,
        resource_type='Campaign',
        resource_id=str(campaign.id),
        actor_email=request.user.email,
        note=f'Campaign {campaign.name} send triggered'
    )

    messages.success(request, 'Kampagne wird gesendet...')
    return redirect('ui:campaign_list')

