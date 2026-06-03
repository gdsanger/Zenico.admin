"""
URL configuration for AI administration UI and API endpoints.
"""

from django.urls import path
from ai import views

app_name = 'ai'

urlpatterns = [
    # Dashboard
    path('', views.AIDashboardView.as_view(), name='dashboard'),

    # Provider
    path('providers/', views.AIProviderListView.as_view(), name='provider-list'),
    path('providers/create/', views.AIProviderCreateView.as_view(), name='provider-create'),
    path('providers/<uuid:pk>/', views.AIProviderDetailView.as_view(), name='provider-detail'),
    path('providers/<uuid:pk>/edit/', views.AIProviderEditView.as_view(), name='provider-edit'),
    path('providers/<uuid:pk>/delete/', views.AIProviderDeleteView.as_view(), name='provider-delete'),
    path('providers/<uuid:pk>/fetch-models/', views.FetchModelsView.as_view(), name='fetch-models'),

    # Agenten
    path('agents/', views.AIAgentListView.as_view(), name='agent-list'),
    path('agents/create/', views.AIAgentCreateView.as_view(), name='agent-create'),
    path('agents/<uuid:pk>/', views.AIAgentDetailView.as_view(), name='agent-detail'),
    path('agents/<uuid:pk>/edit/', views.AIAgentEditView.as_view(), name='agent-edit'),
    path('agents/<uuid:pk>/delete/', views.AIAgentDeleteView.as_view(), name='agent-delete'),
    path('agents/<uuid:pk>/test/', views.AIAgentTestView.as_view(), name='agent-test'),

    # HTMX
    path('models-for-provider/', views.ModelsForProviderView.as_view(), name='models-for-provider'),

    # Jobs + Stats
    path('jobs/', views.AIJobListView.as_view(), name='job-list'),
    path('stats/', views.AIStatsView.as_view(), name='stats'),
]
