"""Shared fixtures for the QMS test suite."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product
from apps.pps.models import Routing, RoutingOperation, WorkCenter

from apps.qms.models import (
    CalibrationStandard, FinalInspectionPlan, FinalTestSpec,
    IncomingInspectionPlan, InspectionCharacteristic, MeasurementEquipment,
    NonConformanceReport, ProcessInspectionPlan, RootCauseAnalysis,
)


@pytest.fixture(autouse=True)
def _clear_tenant():
    yield
    set_current_tenant(None)


# ---------- Tenants & users ----------

@pytest.fixture
def acme(db):
    return Tenant.objects.create(name='Acme Test', slug='acme-test', is_active=True)


@pytest.fixture
def globex(db):
    return Tenant.objects.create(name='Globex Test', slug='globex-test', is_active=True)


@pytest.fixture
def acme_admin(db, acme):
    return User.objects.create_user(
        username='admin_acme_test', password='pw', tenant=acme, is_tenant_admin=True,
    )


@pytest.fixture
def acme_staff(db, acme):
    return User.objects.create_user(
        username='staff_acme_test', password='pw', tenant=acme, is_tenant_admin=False,
    )


@pytest.fixture
def globex_admin(db, globex):
    return User.objects.create_user(
        username='admin_globex_test', password='pw', tenant=globex, is_tenant_admin=True,
    )


@pytest.fixture
def admin_client(client, acme_admin):
    client.force_login(acme_admin)
    return client


@pytest.fixture
def staff_client(client, acme_staff):
    client.force_login(acme_staff)
    return client


@pytest.fixture
def globex_client(client, globex_admin):
    client.force_login(globex_admin)
    return client


# ---------- PLM / PPS prerequisites ----------

@pytest.fixture
def raw_product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='RAW-1', name='Raw material A',
        product_type='raw_material', unit_of_measure='kg', status='active',
    )


@pytest.fixture
def fg_product(db, acme):
    return Product.objects.create(
        tenant=acme, sku='FG-1', name='Finished good A',
        product_type='finished_good', unit_of_measure='ea', status='active',
    )


@pytest.fixture
def globex_product(db, globex):
    return Product.objects.create(
        tenant=globex, sku='RAW-GBX', name='Globex raw',
        product_type='raw_material', unit_of_measure='kg', status='active',
    )


@pytest.fixture
def work_center(db, acme):
    return WorkCenter.objects.create(
        tenant=acme, code='WC-Q1', name='QC Bench', work_center_type='cell',
        capacity_per_hour=Decimal('5'), efficiency_pct=Decimal('100'),
        cost_per_hour=Decimal('40'), is_active=True,
    )


@pytest.fixture
def routing(db, acme, fg_product, work_center, acme_admin):
    r = Routing.objects.create(
        tenant=acme, product=fg_product, version='A', routing_number='ROUT-Q1',
        status='active', is_default=True, created_by=acme_admin,
    )
    RoutingOperation.objects.create(
        tenant=acme, routing=r, sequence=10, operation_name='Inspect',
        work_center=work_center,
        setup_minutes=Decimal('5'), run_minutes_per_unit=Decimal('1'),
        queue_minutes=Decimal('1'), move_minutes=Decimal('1'),
    )
    return r


@pytest.fixture
def routing_operation(db, routing):
    return routing.operations.first()


# ---------- QMS fixtures ----------

@pytest.fixture
def iqc_plan(db, acme, raw_product):
    plan = IncomingInspectionPlan.objects.create(
        tenant=acme, product=raw_product, aql_level='II',
        aql_value=Decimal('2.5'), sample_method='single', version='1.0',
        is_active=True,
    )
    InspectionCharacteristic.objects.create(
        tenant=acme, plan=plan, sequence=10, name='Length',
        characteristic_type='dimensional', nominal=Decimal('100'),
        usl=Decimal('100.5'), lsl=Decimal('99.5'), unit_of_measure='mm',
    )
    return plan


@pytest.fixture
def ipqc_plan(db, acme, fg_product, routing_operation):
    return ProcessInspectionPlan.objects.create(
        tenant=acme, product=fg_product, routing_operation=routing_operation,
        name='IPQC test plan', frequency='every_n_parts', frequency_value=10,
        chart_type='x_bar_r', subgroup_size=5,
        nominal=Decimal('100'), usl=Decimal('100.5'), lsl=Decimal('99.5'),
        unit_of_measure='mm', is_active=True,
    )


@pytest.fixture
def fqc_plan(db, acme, fg_product):
    plan = FinalInspectionPlan.objects.create(
        tenant=acme, product=fg_product, name='FQC test plan',
        version='1.0', is_active=True,
    )
    FinalTestSpec.objects.create(
        tenant=acme, plan=plan, sequence=10, test_name='Functional check',
        test_method='functional', is_critical=True,
    )
    return plan


@pytest.fixture
def open_ncr(db, acme, fg_product, acme_admin):
    ncr = NonConformanceReport.objects.create(
        tenant=acme, ncr_number='NCR-T0001', source='ipqc', severity='major',
        status='open', title='Test NCR', description='Failed test',
        product=fg_product, lot_number='LOT-001',
        quantity_affected=Decimal('5'),
        reported_by=acme_admin, reported_at=timezone.now(),
        assigned_to=acme_admin,
    )
    RootCauseAnalysis.objects.create(tenant=acme, ncr=ncr)
    return ncr


@pytest.fixture
def equipment(db, acme):
    return MeasurementEquipment.objects.create(
        tenant=acme, equipment_number='EQP-T0001', name='Caliper test',
        equipment_type='caliper', serial_number='SN-T-001',
        calibration_interval_days=365,
        last_calibrated_at=timezone.now() - timedelta(days=300),
        next_due_at=timezone.now() + timedelta(days=65),
        status='active', is_active=True,
    )


@pytest.fixture
def calibration_standard(db, acme):
    return CalibrationStandard.objects.create(
        tenant=acme, name='NIST gauge', standard_number='STD-T-001',
        traceable_to='NIST', is_active=True,
    )
