"""Pytest fixtures for Module 19 - DMS tests."""
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from apps.core.models import Tenant, set_current_tenant


@pytest.fixture
def tenant_a(db):
    t = Tenant.objects.create(name='Tenant A', slug='tenant-a')
    set_current_tenant(t)
    yield t
    set_current_tenant(None)


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name='Tenant B', slug='tenant-b')


@pytest.fixture
def tenant_admin(db, tenant_a):
    User = get_user_model()
    return User.objects.create_user(
        username='admin_a', password='pw', email='admin@example.com',
        tenant=tenant_a, is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def staff_user(db, tenant_a):
    User = get_user_model()
    return User.objects.create_user(
        username='staff_a', password='pw', email='staff@example.com',
        tenant=tenant_a, is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def other_tenant_user(db, tenant_b):
    User = get_user_model()
    return User.objects.create_user(
        username='admin_b', password='pw', email='b@example.com',
        tenant=tenant_b, is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def department(db, tenant_a):
    from apps.labor.models import Department
    return Department.objects.create(tenant=tenant_a, name='Quality', code='QUAL')


@pytest.fixture
def position(db, tenant_a, department):
    from apps.labor.models import Position
    return Position.objects.create(tenant=tenant_a, title='Inspector', code='INSP', department=department)


@pytest.fixture
def employee(db, tenant_a, department, position, staff_user):
    from apps.labor.models import Employee
    return Employee.objects.create(
        tenant=tenant_a, employee_number='EMP-001',
        user=staff_user,
        first_name='Test', last_name='Worker',
        department=department, position=position,
        employment_type='full_time', hire_date=date(2020, 1, 1),
        status='active',
    )


@pytest.fixture
def policy(db, tenant_a):
    from apps.dms.models import RetentionPolicy
    return RetentionPolicy.objects.create(
        tenant=tenant_a, name='Test 5-Year Policy',
        applies_to_doc_type='any', retention_years=5,
    )


@pytest.fixture
def category(db, tenant_a):
    from apps.dms.models import DocumentCategory
    return DocumentCategory.objects.create(
        tenant=tenant_a, code='QUAL', name='Quality',
    )


@pytest.fixture
def document(db, tenant_a, category, policy, tenant_admin):
    from apps.dms.models import Document
    return Document.objects.create(
        tenant=tenant_a, title='Test SOP',
        doc_type='sop', category=category, owner=tenant_admin,
        retention_policy=policy,
    )


@pytest.fixture
def version(db, tenant_a, document):
    from apps.dms.models import DocumentVersion
    return DocumentVersion.objects.create(
        tenant=tenant_a, document=document, version='1.0',
        content_html='<p>Body.</p>',
    )


@pytest.fixture
def workflow_with_stages(db, tenant_a):
    from apps.dms.models import ApprovalStage, ApprovalWorkflow
    wf = ApprovalWorkflow.objects.create(
        tenant=tenant_a, name='Test Workflow', applies_to_doc_type='any',
    )
    ApprovalStage.objects.create(
        tenant=tenant_a, workflow=wf, stage_no=1, name='Reviewer',
        approver_role='department_head', min_approvals=1,
    )
    ApprovalStage.objects.create(
        tenant=tenant_a, workflow=wf, stage_no=2, name='Approver',
        approver_role='quality_manager', min_approvals=1,
    )
    return wf
