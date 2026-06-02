"""
URL configuration for AI proxy API endpoints.
"""

from django.urls import path
from ai.api import AICompleteView

app_name = 'ai_api'

urlpatterns = [
    path('complete/', AICompleteView.as_view(), name='complete'),
]
