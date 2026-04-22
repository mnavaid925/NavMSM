"""Module 1 views: Onboarding, Plans, Subscription, Invoices, Branding, Health, Audit."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin

from .forms import BrandingForm, EmailTemplateForm, TenantOrgForm
from .models import (
    BrandingSettings, EmailTemplate, HealthAlert, Invoice, Payment,
    Plan, Subscription, TenantAuditLog, TenantHealthSnapshot,
)
from .services.billing import (
    issue_invoice_for_subscription, mark_invoice_paid, start_trial_for_new_tenant,
)


# ----- Onboarding wizard (single page with step param) -----

class OnboardingWizardView(TenantRequiredMixin, View):
    template_name = 'tenants/onboarding_wizard.html'

    def get(self, request):
        tenant = request.tenant
        step = request.GET.get('step', '1')
        context = {
            'step': step,
            'org_form': TenantOrgForm(instance=tenant),
            'plans': Plan.objects.filter(is_active=True),
            'subscription': Subscription.objects.filter(tenant=tenant).select_related('plan').first(),
            'branding': BrandingSettings.objects.filter(tenant=tenant).first(),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        tenant = request.tenant
        step = request.POST.get('step', '1')
        if step == '1':
            form = TenantOrgForm(request.POST, request.FILES, instance=tenant)
            if form.is_valid():
                form.save()
                messages.success(request, 'Organization details saved.')
                return redirect(f'{request.path}?step=2')
            return render(request, self.template_name, {
                'step': '1', 'org_form': form,
                'plans': Plan.objects.filter(is_active=True),
            })
        if step == '2':
            plan_slug = request.POST.get('plan')
            plan = get_object_or_404(Plan, slug=plan_slug, is_active=True)
            sub, _ = Subscription.objects.get_or_create(
                tenant=tenant,
                defaults={
                    'plan': plan,
                    'status': 'trial',
                    'trial_ends_at': timezone.now() + timedelta(days=plan.trial_days),
                    'current_period_start': timezone.now(),
                    'current_period_end': timezone.now() + timedelta(days=30),
                },
            )
            if sub.plan_id != plan.pk:
                sub.plan = plan
                sub.save(update_fields=['plan'])
            messages.success(request, f'Plan selected: {plan.name}.')
            return redirect(f'{request.path}?step=3')
        if step == '3':
            # Admin account step — the registering user IS already the admin.
            return redirect(f'{request.path}?step=4')
        if step == '4':
            messages.success(request, 'Onboarding complete. Welcome!')
            return redirect('dashboard')
        return redirect(request.path)


# ----- Plans & Subscription -----

class PlansView(TenantRequiredMixin, View):
    def get(self, request):
        plans = Plan.objects.filter(is_active=True)
        current = Subscription.objects.filter(tenant=request.tenant).select_related('plan').first()
        return render(request, 'tenants/plans.html', {
            'plans': plans, 'current_subscription': current,
        })


class SubscriptionView(TenantRequiredMixin, View):
    def get(self, request):
        sub = Subscription.objects.filter(tenant=request.tenant).select_related('plan').first()
        recent_invoices = Invoice.objects.filter(tenant=request.tenant).order_by('-issue_date')[:5]
        recent_payments = Payment.objects.filter(tenant=request.tenant).order_by('-created_at')[:5]
        return render(request, 'tenants/subscription.html', {
            'subscription': sub,
            'recent_invoices': recent_invoices,
            'recent_payments': recent_payments,
        })


class SubscriptionChangeView(TenantAdminRequiredMixin, View):
    def post(self, request, plan_slug):
        plan = get_object_or_404(Plan, slug=plan_slug, is_active=True)
        sub = Subscription.objects.filter(tenant=request.tenant).first()
        if sub is None:
            sub = start_trial_for_new_tenant(request.tenant)
        sub.plan = plan
        sub.status = 'active'
        sub.cancel_at_period_end = False
        sub.cancelled_at = None
        sub.save()
        messages.success(request, f'Plan updated to {plan.name}.')
        return redirect('tenants:subscription')


class SubscriptionCancelView(TenantAdminRequiredMixin, View):
    def post(self, request):
        sub = get_object_or_404(Subscription, tenant=request.tenant)
        sub.cancel_at_period_end = True
        sub.cancelled_at = timezone.now()
        sub.save()
        messages.info(request, 'Subscription set to cancel at period end.')
        return redirect('tenants:subscription')


class SubscriptionResumeView(TenantAdminRequiredMixin, View):
    def post(self, request):
        sub = get_object_or_404(Subscription, tenant=request.tenant)
        sub.cancel_at_period_end = False
        sub.cancelled_at = None
        if sub.status == 'cancelled':
            sub.status = 'active'
        sub.save()
        messages.success(request, 'Subscription resumed.')
        return redirect('tenants:subscription')


# ----- Invoices -----

class InvoiceListView(TenantRequiredMixin, ListView):
    model = Invoice
    template_name = 'tenants/invoices.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        qs = Invoice.objects.filter(tenant=self.request.tenant)
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = Invoice.STATUS_CHOICES
        outstanding = Invoice.objects.filter(
            tenant=self.request.tenant, status='open'
        ).aggregate(s=Sum('total'))['s'] or 0
        ctx['outstanding'] = outstanding
        return ctx


class InvoiceDetailView(TenantRequiredMixin, DetailView):
    model = Invoice
    template_name = 'tenants/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        return Invoice.objects.filter(tenant=self.request.tenant).prefetch_related('line_items', 'payments')


class InvoicePayView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, tenant=request.tenant)
        if invoice.status == 'paid':
            messages.info(request, 'Invoice already paid.')
            return redirect('tenants:invoice_detail', pk=pk)
        mark_invoice_paid(invoice)
        messages.success(request, f'Invoice {invoice.number} paid (mock gateway).')
        return redirect('tenants:invoice_detail', pk=pk)


# ----- Branding -----

class BrandingView(TenantAdminRequiredMixin, View):
    def get(self, request):
        branding, _ = BrandingSettings.objects.get_or_create(tenant=request.tenant)
        return render(request, 'tenants/branding.html', {'form': BrandingForm(instance=branding), 'branding': branding})

    def post(self, request):
        branding, _ = BrandingSettings.objects.get_or_create(tenant=request.tenant)
        form = BrandingForm(request.POST, request.FILES, instance=branding)
        if form.is_valid():
            form.save()
            messages.success(request, 'Branding updated.')
            return redirect('tenants:branding')
        return render(request, 'tenants/branding.html', {'form': form, 'branding': branding})


class EmailTemplateListView(TenantAdminRequiredMixin, ListView):
    model = EmailTemplate
    template_name = 'tenants/email_templates.html'
    context_object_name = 'templates'
    paginate_by = 20

    def get_queryset(self):
        return EmailTemplate.objects.filter(tenant=self.request.tenant)


class EmailTemplateEditView(TenantAdminRequiredMixin, View):
    def get(self, request, pk):
        tmpl = get_object_or_404(EmailTemplate, pk=pk, tenant=request.tenant)
        return render(request, 'tenants/email_template_form.html', {
            'form': EmailTemplateForm(instance=tmpl), 'template': tmpl,
        })

    def post(self, request, pk):
        tmpl = get_object_or_404(EmailTemplate, pk=pk, tenant=request.tenant)
        form = EmailTemplateForm(request.POST, instance=tmpl)
        if form.is_valid():
            form.save()
            messages.success(request, 'Template saved.')
            return redirect('tenants:email_template_list')
        return render(request, 'tenants/email_template_form.html', {'form': form, 'template': tmpl})


# ----- Health monitoring -----

class HealthView(TenantRequiredMixin, View):
    def get(self, request):
        snapshots = list(
            TenantHealthSnapshot.objects.filter(tenant=request.tenant).order_by('-captured_at')[:30]
        )
        snapshots.reverse()
        latest = snapshots[-1] if snapshots else None
        alerts = HealthAlert.objects.filter(tenant=request.tenant).order_by('-created_at')[:20]
        return render(request, 'tenants/health.html', {
            'snapshots': snapshots,
            'latest': latest,
            'alerts': alerts,
            'dates': [s.captured_at.strftime('%Y-%m-%d') for s in snapshots],
            'scores': [float(s.health_score) for s in snapshots],
            'api_calls': [s.api_calls_24h for s in snapshots],
            'response_times': [s.avg_response_ms for s in snapshots],
        })


# ----- Audit log -----

class AuditLogView(TenantAdminRequiredMixin, ListView):
    model = TenantAuditLog
    template_name = 'tenants/audit_log.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        return TenantAuditLog.objects.filter(tenant=self.request.tenant).select_related('user')
