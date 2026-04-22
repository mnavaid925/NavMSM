from django.urls import path
from . import views

app_name = 'tenants'

urlpatterns = [
    # Onboarding wizard
    path('onboarding/', views.OnboardingWizardView.as_view(), name='onboarding'),

    # Plans & subscription
    path('plans/', views.PlansView.as_view(), name='plans'),
    path('subscription/', views.SubscriptionView.as_view(), name='subscription'),
    path('subscription/change/<slug:plan_slug>/', views.SubscriptionChangeView.as_view(), name='subscription_change'),
    path('subscription/cancel/', views.SubscriptionCancelView.as_view(), name='subscription_cancel'),
    path('subscription/resume/', views.SubscriptionResumeView.as_view(), name='subscription_resume'),

    # Invoices
    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<int:pk>/pay/', views.InvoicePayView.as_view(), name='invoice_pay'),

    # Branding
    path('branding/', views.BrandingView.as_view(), name='branding'),
    path('email-templates/', views.EmailTemplateListView.as_view(), name='email_template_list'),
    path('email-templates/<int:pk>/edit/', views.EmailTemplateEditView.as_view(), name='email_template_edit'),

    # Health
    path('health/', views.HealthView.as_view(), name='health'),

    # Audit log
    path('audit/', views.AuditLogView.as_view(), name='audit_log'),
]
