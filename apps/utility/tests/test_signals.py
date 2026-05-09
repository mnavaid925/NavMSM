"""Cross-module signal hooks + L-18 dispatch_uid presence guard."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.models.signals import post_save, pre_delete, pre_save
from django.utils import timezone

from apps.utility import models as U


pytestmark = pytest.mark.django_db


def _all_uids():
    """Collect every dispatch_uid currently attached across the three signals."""
    out = set()
    for sig in (pre_save, post_save, pre_delete):
        for lookup_key, _ in sig.receivers:
            uid = lookup_key[0]  # lookup_key = (uid_hash, sender_id)
            out.add(uid)
    return out


# ---------- L-18 dispatch_uid presence (factory + module-scope handlers) ----------

REQUIRED_PRE_SAVE_UIDS = [
    'utility.dre.pre_save',
    'utility.peak_suggestion.pre_save',
    'utility.allocation.is_posted_to_cost.pre_save',
    'utility.carbon.is_reversal.pre_save',
]
REQUIRED_POST_SAVE_UIDS = [
    'utility.dre.post_save',
    'utility.peak_suggestion.post_save',
    'utility.allocation.is_posted_to_cost.post_save',
    'utility.carbon.is_reversal.post_save',
    'utility.consumption_to_carbon',
    'utility.eam_meter_reading_to_consumption',
]
REQUIRED_PRE_DELETE_UIDS = [
    'utility.consumption_to_carbon_reverse',
    'utility.eam_meter_reading_to_consumption_reverse',
]


def _hash_uids():
    """Hash every dispatch_uid the same way Django stores them so we can membership-check."""
    # Django stores receiver keys as (hash(dispatch_uid), sender_id). Use python's hash().
    return _all_uids()


def test_factory_audit_dispatch_uids_attached_pre_save():
    """L-18: every factory-registered pre_save uid must be present after apps.ready().

    Django stores ``lookup_key[0]`` as the raw dispatch_uid string (not a hash)
    when a uid is provided to ``connect()``.
    """
    uids = {r[0][0] for r in pre_save.receivers}
    missing = set(REQUIRED_PRE_SAVE_UIDS) - uids
    assert not missing, f'Missing pre_save dispatch_uids: {missing}'


def test_factory_audit_dispatch_uids_attached_post_save():
    uids = {r[0][0] for r in post_save.receivers}
    missing = set(REQUIRED_POST_SAVE_UIDS) - uids
    assert not missing, f'Missing post_save dispatch_uids: {missing}'


def test_pre_delete_dispatch_uids_attached():
    uids = {r[0][0] for r in pre_delete.receivers}
    missing = set(REQUIRED_PRE_DELETE_UIDS) - uids
    assert not missing, f'Missing pre_delete dispatch_uids: {missing}'


def test_signals_module_imports_cleanly():
    """Smoke: importing utility.signals does not raise; required factory exists."""
    from apps.utility import signals as sigs
    assert hasattr(sigs, '_mk_status_signals')
    assert hasattr(sigs, '_mk_flag_signals')


# ---------- Cross-module: UtilityConsumption -> CarbonEmission ----------

def test_consumption_post_save_emits_carbon(acme, acp_open, meter, emission_factor_grid):
    now = timezone.now()
    # Anchor inside the open period
    period_dt = timezone.make_aware(
        timezone.datetime(
            acp_open.start_date.year,
            acp_open.start_date.month,
            acp_open.start_date.day, 10, 0,
        )
    )
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=period_dt,
        period_end=period_dt + timedelta(hours=1),
        start_reading=Decimal('0'), end_reading=Decimal('100'),
        unit_cost=Decimal('0.10'),
    )
    assert U.CarbonEmission.all_objects.filter(source_consumption=c).count() == 1


def test_consumption_post_save_idempotent_under_double_save(
    acme, acp_open, meter, emission_factor_grid,
):
    period_dt = timezone.make_aware(
        timezone.datetime(
            acp_open.start_date.year,
            acp_open.start_date.month,
            acp_open.start_date.day, 11, 0,
        )
    )
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=period_dt,
        period_end=period_dt + timedelta(hours=1),
        start_reading=Decimal('0'), end_reading=Decimal('100'),
        unit_cost=Decimal('0.10'),
    )
    c.notes = 'updated'
    c.save()
    assert U.CarbonEmission.all_objects.filter(source_consumption=c).count() == 1


def test_consumption_silent_skip_when_no_factor(acme, acp_open, meter):
    """No EmissionFactor -> the post_save hook silently returns; no emission row."""
    now = timezone.now()
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=now - timedelta(hours=1), period_end=now,
        start_reading=Decimal('0'), end_reading=Decimal('100'),
    )
    assert U.CarbonEmission.all_objects.filter(source_consumption=c).count() == 0


def test_consumption_pre_delete_reverses_carbon(
    acme, acp_open, meter, emission_factor_grid,
):
    """pre_delete on consumption emits a reversal CarbonEmission row."""
    period_dt = timezone.make_aware(
        timezone.datetime(
            acp_open.start_date.year,
            acp_open.start_date.month,
            acp_open.start_date.day, 12, 0,
        )
    )
    c = U.UtilityConsumption.objects.create(
        tenant=acme, meter=meter,
        period_start=period_dt,
        period_end=period_dt + timedelta(hours=1),
        start_reading=Decimal('0'), end_reading=Decimal('100'),
        unit_cost=Decimal('0.10'),
    )
    original_pk = c.pk
    # Confirm carbon row exists
    assert U.CarbonEmission.all_objects.filter(source_consumption=c).count() == 1
    c.delete()
    # Original carbon row's source_consumption FK is SET_NULL; reversal row was emitted
    reversal_count = U.CarbonEmission.all_objects.filter(is_reversal=True).count()
    assert reversal_count >= 1


# ---------- Cross-module: eam.AssetMeterReading -> UtilityConsumption ----------

def test_kwh_meter_reading_creates_consumption(
    acme, utility_type_electricity, emission_factor_grid,
):
    from apps.eam.models import Asset, AssetCategory, AssetMeterReading
    cat = AssetCategory.objects.create(tenant=acme, name='Test1')
    asset = Asset.objects.create(tenant=acme, category=cat, tag='T1', name='Test')
    # Link a UtilityMeter to this asset (utility_type code 'electricity')
    U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        name='Asset Meter', asset=asset, is_active=True,
    )
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='kwh',
        reading_value=Decimal('500'),
    )
    assert U.UtilityConsumption.all_objects.filter(
        source_meter_reading=reading,
    ).count() == 1


def test_non_kwh_reading_silently_skips(
    acme, utility_type_electricity, emission_factor_grid,
):
    """Hours / cycles meter readings should not auto-emit a consumption."""
    from apps.eam.models import Asset, AssetCategory, AssetMeterReading
    cat = AssetCategory.objects.create(tenant=acme, name='Test2')
    asset = Asset.objects.create(tenant=acme, category=cat, tag='T2', name='Test')
    U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        name='Asset Meter', asset=asset, is_active=True,
    )
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='hours',
        reading_value=Decimal('100'),
    )
    assert U.UtilityConsumption.all_objects.filter(
        source_meter_reading=reading,
    ).count() == 0


def test_kwh_reading_skips_when_no_utility_meter(acme):
    """No matching UtilityMeter(asset=…) -> silent skip, no consumption row."""
    from apps.eam.models import Asset, AssetCategory, AssetMeterReading
    cat = AssetCategory.objects.create(tenant=acme, name='Test3')
    asset = Asset.objects.create(tenant=acme, category=cat, tag='T3', name='Test')
    # No UtilityMeter linked to this asset
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='kwh',
        reading_value=Decimal('100'),
    )
    assert U.UtilityConsumption.all_objects.filter(
        source_meter_reading=reading,
    ).count() == 0


def test_kwh_reading_pre_delete_reverses_consumption(
    acme, utility_type_electricity, emission_factor_grid,
):
    """pre_delete on AssetMeterReading emits a reversal UtilityConsumption row."""
    from apps.eam.models import Asset, AssetCategory, AssetMeterReading
    cat = AssetCategory.objects.create(tenant=acme, name='Test4')
    asset = Asset.objects.create(tenant=acme, category=cat, tag='T4', name='Test')
    U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        name='Asset Meter', asset=asset, is_active=True,
    )
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='kwh',
        reading_value=Decimal('500'),
    )
    assert U.UtilityConsumption.all_objects.filter(
        source_meter_reading=reading,
    ).count() == 1
    reading.delete()
    # Reversal row emitted
    assert U.UtilityConsumption.all_objects.filter(is_reversal=True).count() >= 1


# ---------- Audit factory smoke ----------

def test_dre_save_does_not_crash(acme, utility_type_electricity):
    """Status transitions on DRE flow through factory signals without raising."""
    now = timezone.now()
    e = U.DemandResponseEvent.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        start_at=now, end_at=now + timedelta(hours=1),
        status='scheduled',
    )
    e.status = 'active'
    e.save()  # triggers _pre / _post audit handlers
    e.refresh_from_db()
    assert e.status == 'active'


def test_allocation_flag_transition_does_not_crash(acme, acp_open, meter, consumption):
    """is_posted_to_cost flip flows through _mk_flag_signals without raising."""
    a = U.UtilityAllocation.objects.create(
        tenant=acme, period=acp_open, meter=meter, share_pct=Decimal('100'),
        is_posted_to_cost=False,
    )
    a.is_posted_to_cost = True
    a.save()
    a.refresh_from_db()
    assert a.is_posted_to_cost is True
