"""
Public REST API URLs for Zenico Admin.

All API endpoints are public (no authentication required) except for
instance and AI endpoints which require API key authentication.
Rate limiting and CORS are applied.
"""

from django.urls import path, include
from crm.api import ContactCreateAPIView, EducationDiscountAPIView
from newsletter.api import SubscribeAPIView, ConfirmAPIView, UnsubscribeAPIView

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

    # AI Proxy API (requires API key authentication)
    path('ai/', include('ai.urls')),
]
