"""Core dashboard view — aggregates KPIs from tenants/accounts."""
from datetime import timedelta
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views import View

from apps.accounts.models import User, UserInvite
from apps.tenants.models import (
    Subscription, Invoice, TenantAuditLog, TenantHealthSnapshot,
)


class DashboardView(LoginRequiredMixin, View):
    template_name = 'dashboard/index.html'

    def get(self, request):
        tenant = request.tenant
        if tenant is None:
            return render(request, self.template_name, {'no_tenant': True})

        today = timezone.now()
        thirty_days_ago = today - timedelta(days=30)

        subscription = Subscription.objects.filter(tenant=tenant).select_related('plan').first()
        active_users = User.objects.filter(tenant=tenant, is_active=True).count()
        pending_invites = UserInvite.objects.filter(tenant=tenant, status='pending').count()
        open_invoices_qs = Invoice.objects.filter(tenant=tenant, status='open')
        open_invoices_count = open_invoices_qs.count()
        outstanding_balance = sum((inv.total for inv in open_invoices_qs), 0) or 0

        last_payment = (
            Invoice.objects.filter(tenant=tenant, status='paid')
            .order_by('-issue_date').first()
        )

        health_snapshots = list(
            TenantHealthSnapshot.objects.filter(
                tenant=tenant, captured_at__gte=thirty_days_ago,
            ).order_by('captured_at')
        )
        latest_health = health_snapshots[-1] if health_snapshots else None

        recent_activity = (
            TenantAuditLog.objects.filter(tenant=tenant)
            .select_related('user').order_by('-timestamp')[:10]
        )

        context = {
            'subscription': subscription,
            'active_users': active_users,
            'pending_invites': pending_invites,
            'open_invoices_count': open_invoices_count,
            'outstanding_balance': outstanding_balance,
            'last_payment': last_payment,
            'latest_health': latest_health,
            'health_snapshots': health_snapshots,
            'health_dates': [s.captured_at.strftime('%Y-%m-%d') for s in health_snapshots],
            'health_scores': [float(s.health_score) for s in health_snapshots],
            'api_calls': [s.api_calls_24h for s in health_snapshots],
            'recent_activity': recent_activity,
        }
        return render(request, self.template_name, context)
