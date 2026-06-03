"""
URL configuration for instance API endpoints.
"""

from django.urls import path
from instances.api import InstanceRegisterView, InstanceLicenseView, AIAgentListView

app_name = 'instance_api'

urlpatterns = [
    path('register/', InstanceRegisterView.as_view(), name='register'),
    path('license/', InstanceLicenseView.as_view(), name='license'),
    path('ai/agents/', AIAgentListView.as_view(), name='ai-agents'),
]
