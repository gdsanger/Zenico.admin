"""
URL configuration for billing app.
"""

from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
]
