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
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['current_status'] = self.request.GET.get('status', '')
        return context


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
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
@method_decorator(role_required('superadmin', 'support'), name='dispatch')
class CampaignEditView(UpdateView):
    """
    Campaign edit view.
    """
    model = Campaign
    template_name = 'ui/newsletter/campaign_edit.html'
    fields = ['name', 'subject', 'preview_text', 'html_body', 'text_body', 'segment']
    pk_url_kwarg = 'campaign_id'

    def get_success_url(self):
        return f'/newsletter/campaigns/'


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

