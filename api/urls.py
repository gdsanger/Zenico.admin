"""
Public REST API URLs for Zenico Admin.

All API endpoints are public (no authentication required) except for
instance and AI endpoints which require API key authentication.
Rate limiting and CORS are applied.
"""

from django.urls import path, include
from crm.api import ContactCreateAPIView, EducationDiscountAPIView
from newsletter.api import SubscribeAPIView, ConfirmAPIView, UnsubscribeAPIView
from instances.provisioning_api import (
    PendingInstancesView,
    ClaimInstanceView,
    CompleteInstanceView,
    FailInstanceView,
)

app_name = 'api'

urlpatterns = [
    # CRM
    path('contacts/', ContactCreateAPIView.as_view(), name='contact-create'),
    path('education-discount/', EducationDiscountAPIView.as_view(), name='education-discount'),

    # Newsletter
    path('newsletter/subscribe/', SubscribeAPIView.as_view(), name='newsletter-subscribe'),
    path('newsletter/confirm/<str:token>/', ConfirmAPIView.as_view(), name='newsletter-confirm'),
    path('newsletter/unsubscribe/<str:token>/', UnsubscribeAPIView.as_view(), name='newsletter-unsubscribe'),

    # Instance API (requires API key authentication)
    path('instance/', include('instances.urls')),

    # Provisioning Agent API (requires PROVISIONING_AGENT_TOKEN bearer token)
    path('instances/pending/', PendingInstancesView.as_view(), name='provisioning-pending'),
    path('instances/<uuid:instance_id>/claim/', ClaimInstanceView.as_view(), name='provisioning-claim'),
    path('instances/<uuid:instance_id>/complete/', CompleteInstanceView.as_view(), name='provisioning-complete'),
    path('instances/<uuid:instance_id>/fail/', FailInstanceView.as_view(), name='provisioning-fail'),

    # AI Proxy API (requires API key authentication)
    path('ai/', include('ai.urls')),
]
