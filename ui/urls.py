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
from ui.views.coupons import (
    CouponListView,
    CouponCreateView,
    CouponDetailView,
    coupon_deactivate,
    coupon_activate,
    coupon_validate,
    coupon_apply,
    coupon_remove,
    coupon_type_fields,
    coupon_duration_fields,
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
    CampaignCreateView,
    CampaignEditView,
    AutomationListView,
    AutomationDetailView,
    AutomationCreateView,
    create_subscriber,
    deactivate_subscriber,
    campaign_preview,
    campaign_test,
    campaign_schedule,
    campaign_send,
    automation_toggle,
    automation_step_create,
    automation_step_edit,
    automation_step_delete,
)

app_name = 'ui'

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

    # Coupons
    path('billing/coupons/', CouponListView.as_view(), name='coupon_list'),
    path('billing/coupons/new/', CouponCreateView.as_view(), name='coupon_create'),
    path('billing/coupons/<uuid:pk>/', CouponDetailView.as_view(), name='coupon_detail'),
    path('billing/coupons/<uuid:pk>/deactivate/', coupon_deactivate, name='coupon_deactivate'),
    path('billing/coupons/<uuid:pk>/activate/', coupon_activate, name='coupon_activate'),
    path('billing/coupons/validate/', coupon_validate, name='coupon_validate'),
    path('billing/coupons/apply/', coupon_apply, name='coupon_apply'),
    path('billing/coupons/remove/<uuid:subscription_id>/', coupon_remove, name='coupon_remove'),
    path('billing/coupons/type-fields/', coupon_type_fields, name='coupon_type_fields'),
    path('billing/coupons/duration-fields/', coupon_duration_fields, name='coupon_duration_fields'),

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
    path('newsletter/campaigns/create/', CampaignCreateView.as_view(), name='campaign_create'),
    path('newsletter/campaigns/<uuid:campaign_id>/edit/', CampaignEditView.as_view(), name='campaign_edit'),
    path('newsletter/campaigns/<uuid:campaign_id>/preview/', campaign_preview, name='campaign_preview'),
    path('newsletter/campaigns/<uuid:campaign_id>/test/', campaign_test, name='campaign_test'),
    path('newsletter/campaigns/<uuid:campaign_id>/schedule/', campaign_schedule, name='campaign_schedule'),
    path('newsletter/campaigns/<uuid:campaign_id>/send/', campaign_send, name='campaign_send'),
    path('newsletter/automations/', AutomationListView.as_view(), name='automation_list'),
    path('newsletter/automations/create/', AutomationCreateView.as_view(), name='automation_create'),
    path('newsletter/automations/<uuid:sequence_id>/', AutomationDetailView.as_view(), name='automation_detail'),
    path('newsletter/automations/<uuid:sequence_id>/toggle/', automation_toggle, name='automation_toggle'),
    path('newsletter/automations/<uuid:sequence_id>/steps/create/', automation_step_create, name='automation_step_create'),
    path('newsletter/automations/<uuid:sequence_id>/steps/<uuid:step_id>/edit/', automation_step_edit, name='automation_step_edit'),
    path('newsletter/automations/<uuid:sequence_id>/steps/<uuid:step_id>/delete/', automation_step_delete, name='automation_step_delete'),
]
