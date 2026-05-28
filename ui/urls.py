from django.urls import path
from ui.views import (
    # Auth
    LoginView,
    logout_view,
    # Dashboard
    DashboardView,
    dashboard_kpis,
    dashboard_activity,
    # Customers
    CustomerListView,
    CustomerDetailView,
    CustomerCreateView,
    customer_check_slug,
    customer_suspend,
    customer_reactivate,
    # Instances
    InstanceListView,
    InstanceDetailView,
    instance_api_key_reveal,
    instance_api_key_regenerate,
    # Billing
    SubscriptionListView,
    InvoiceListView,
    StripeEventListView,
    # Audit
    AuditLogListView,
    audit_export_csv,
)

urlpatterns = [
    # Auth
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', logout_view, name='logout'),

    # Dashboard
    path('', DashboardView.as_view(), name='dashboard'),
    path('dashboard/kpis/', dashboard_kpis, name='dashboard_kpis'),
    path('dashboard/activity/', dashboard_activity, name='dashboard_activity'),

    # Customers
    path('customers/', CustomerListView.as_view(), name='customer_list'),
    path('customers/new/', CustomerCreateView.as_view(), name='customer_create'),
    path('customers/check-slug/', customer_check_slug, name='customer_check_slug'),
    path('customers/<slug:slug>/', CustomerDetailView.as_view(), name='customer_detail'),
    path('customers/<slug:slug>/suspend/', customer_suspend, name='customer_suspend'),
    path('customers/<slug:slug>/reactivate/', customer_reactivate, name='customer_reactivate'),

    # Instances
    path('instances/', InstanceListView.as_view(), name='instance_list'),
    path('instances/<uuid:pk>/', InstanceDetailView.as_view(), name='instance_detail'),
    path('instances/<uuid:pk>/api-key/', instance_api_key_reveal, name='instance_api_key_reveal'),
    path('instances/<uuid:pk>/regenerate-key/', instance_api_key_regenerate, name='instance_api_key_regenerate'),

    # Billing
    path('billing/subscriptions/', SubscriptionListView.as_view(), name='subscription_list'),
    path('billing/invoices/', InvoiceListView.as_view(), name='invoice_list'),
    path('billing/stripe-events/', StripeEventListView.as_view(), name='stripe_event_list'),

    # Audit
    path('audit/', AuditLogListView.as_view(), name='audit_log_list'),
    path('audit/export/', audit_export_csv, name='audit_export_csv'),
]
