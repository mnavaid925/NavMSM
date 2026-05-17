"""Form validation - unique_together (L-01), per-workflow required (L-14)."""
from datetime import date, timedelta

import pytest

from apps.wfa import forms as F
from apps.wfa import models as M


pytestmark = pytest.mark.django_db


def test_process_category_unique_code_per_tenant(tenant_a):
    M.ProcessCategory.objects.create(tenant=tenant_a, code='X', name='X')
    f = F.ProcessCategoryForm(
        data={'name': 'X2', 'code': 'X', 'is_active': True},
        tenant=tenant_a,
    )
    assert not f.is_valid()


def test_approval_policy_unique_code_per_tenant(tenant_a):
    M.ApprovalPolicy.objects.create(tenant=tenant_a, code='POL', name='X')
    f = F.ApprovalPolicyForm(
        data={'name': 'Y', 'code': 'POL', 'applies_to_type': '', 'is_active': True},
        tenant=tenant_a,
    )
    assert not f.is_valid()


def test_approval_reject_requires_notes():
    f = F.ApprovalRejectForm(data={'notes': ''})
    assert not f.is_valid()
    f2 = F.ApprovalRejectForm(data={'notes': 'reason'})
    assert f2.is_valid()


def test_process_instance_cancel_requires_reason():
    f = F.ProcessInstanceCancelForm(data={'reason': ''})
    assert not f.is_valid()
    f2 = F.ProcessInstanceCancelForm(data={'reason': 'changed mind'})
    assert f2.is_valid()


def test_suggestion_dismiss_requires_notes():
    f = F.SuggestionStatusForm(data={'notes': ''})
    assert not f.is_valid()
    f2 = F.SuggestionStatusForm(data={'notes': 'not applicable'})
    assert f2.is_valid()


def test_delegation_form_rejects_same_delegator_delegate(tenant_a, tenant_admin):
    f = F.ApprovalDelegationForm(
        data={
            'delegator': tenant_admin.pk, 'delegate': tenant_admin.pk,
            'policy': '', 'starts_at': date(2025, 1, 1),
            'ends_at': date(2025, 1, 10), 'reason': '', 'is_active': True,
        },
        tenant=tenant_a,
    )
    assert not f.is_valid()


def test_delegation_form_rejects_end_before_start(tenant_a, tenant_admin, staff_user):
    f = F.ApprovalDelegationForm(
        data={
            'delegator': tenant_admin.pk, 'delegate': staff_user.pk,
            'policy': '', 'starts_at': date(2025, 1, 10),
            'ends_at': date(2025, 1, 5), 'reason': '', 'is_active': True,
        },
        tenant=tenant_a,
    )
    assert not f.is_valid()


def test_bottleneck_form_rejects_end_before_start(tenant_a, definition):
    f = F.BottleneckAnalysisForm(
        data={
            'definition': definition.pk,
            'period_start': '2025-02-01',
            'period_end': '2025-01-01',
            'notes': '',
        },
        tenant=tenant_a,
    )
    assert not f.is_valid()


def test_template_form_parses_channels_csv(tenant_a):
    f = F.NotificationTemplateForm(
        data={
            'code': 'T1', 'name': 'Test',
            'event_type': 'x.y',
            'subject_template': 's', 'body_template': 'b',
            'channels_csv': 'email, in_app, sms',
            'is_active': True,
        },
        tenant=tenant_a,
    )
    assert f.is_valid(), f.errors
    obj = f.save(commit=False)
    obj.tenant = tenant_a
    obj.save()
    assert obj.channels == ['email', 'in_app', 'sms']
