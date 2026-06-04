"""
URL configuration for instance API endpoints.
"""

from django.urls import path
from ai.api import AICompleteView
from instances.api import InstanceRegisterView, InstanceLicenseView, AIAgentListView
from instances.subscription_api import (
    SubscriptionView,
    AddSeatsView,
    RemoveSeatsView,
    AddAIAddonView,
    CancelSubscriptionView,
    BillingPortalView,
)

app_name = 'instance_api'

urlpatterns = [
    path('register/', InstanceRegisterView.as_view(), name='register'),
    path('license/', InstanceLicenseView.as_view(), name='license'),
    path('ai/agents/', AIAgentListView.as_view(), name='ai-agents'),
    path('ai/complete/', AICompleteView.as_view(), name='ai-complete'),

    # Subscription management endpoints
    path('subscription/', SubscriptionView.as_view(), name='subscription'),
    path('subscription/add-seats/', AddSeatsView.as_view(), name='add-seats'),
    path('subscription/remove-seats/', RemoveSeatsView.as_view(), name='remove-seats'),
    path('subscription/add-ai-addon/', AddAIAddonView.as_view(), name='add-ai-addon'),
    path('subscription/cancel/', CancelSubscriptionView.as_view(), name='cancel'),
    path('subscription/portal-url/', BillingPortalView.as_view(), name='portal-url'),
]
