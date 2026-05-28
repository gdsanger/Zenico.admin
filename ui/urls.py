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
from crm.views import (
    ContactListView,
    ContactDetailView,
    add_contact_note,
    update_contact_status,
    ConvertToCustomerView,
    create_contact,
    assign_contact,
    get_note_form,
)
from newsletter.views import (
    SubscriberListView,
    CampaignListView,
    CampaignEditView,
    AutomationListView,
    create_subscriber,
    deactivate_subscriber,
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

    # CRM
    path('crm/contacts/', ContactListView.as_view(), name='contact_list'),
    path('crm/contacts/create/', create_contact, name='contact_create'),
    path('crm/contacts/<uuid:contact_id>/', ContactDetailView.as_view(), name='contact_detail'),
    path('crm/contacts/<uuid:contact_id>/add-note/', add_contact_note, name='contact_add_note'),
    path('crm/contacts/<uuid:contact_id>/update-status/', update_contact_status, name='contact_update_status'),
    path('crm/contacts/<uuid:contact_id>/assign/', assign_contact, name='contact_assign'),
    path('crm/contacts/<uuid:contact_id>/note-form/', get_note_form, name='contact_note_form'),
    path('crm/contacts/<uuid:contact_id>/convert/', ConvertToCustomerView.as_view(), name='contact_convert'),

    # Newsletter
    path('newsletter/subscribers/', SubscriberListView.as_view(), name='subscriber_list'),
    path('newsletter/subscribers/create/', create_subscriber, name='subscriber_create'),
    path('newsletter/subscribers/<uuid:subscriber_id>/deactivate/', deactivate_subscriber, name='subscriber_deactivate'),
    path('newsletter/campaigns/', CampaignListView.as_view(), name='campaign_list'),
    path('newsletter/campaigns/<uuid:campaign_id>/edit/', CampaignEditView.as_view(), name='campaign_edit'),
    path('newsletter/automations/', AutomationListView.as_view(), name='automation_list'),
]
