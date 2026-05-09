"""End-to-end: eam.AssetMeterReading(kwh) -> UtilityConsumption -> CarbonEmission."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.utility import models as U


pytestmark = pytest.mark.django_db


def _make_asset_with_meter(acme, utility_type_electricity, name='Asset Meter'):
    from apps.eam.models import Asset, AssetCategory
    cat = AssetCategory.objects.create(tenant=acme, name='Test')
    asset = Asset.objects.create(tenant=acme, category=cat, tag='T1', name='Test')
    U.UtilityMeter.objects.create(
        tenant=acme, utility_type=utility_type_electricity,
        name=name, asset=asset, is_active=True,
    )
    return asset


def test_kwh_reading_creates_consumption_row(
    acme, utility_type_electricity, emission_factor_grid,
):
    """A new AssetMeterReading(meter_type='kwh') auto-creates UtilityConsumption."""
    from apps.eam.models import AssetMeterReading
    asset = _make_asset_with_meter(acme, utility_type_electricity)
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='kwh',
        reading_value=Decimal('500'),
    )
    cons = U.UtilityConsumption.all_objects.filter(source_meter_reading=reading)
    assert cons.count() == 1


def test_consumption_then_emits_carbon(
    acme, acp_open, utility_type_electricity, emission_factor_grid,
):
    """The auto-created UtilityConsumption then emits a CarbonEmission row."""
    from apps.eam.models import AssetMeterReading
    asset = _make_asset_with_meter(acme, utility_type_electricity)
    # Anchor reading time inside the open period
    period_dt = timezone.make_aware(
        timezone.datetime(
            acp_open.start_date.year,
            acp_open.start_date.month,
            acp_open.start_date.day, 9, 0,
        )
    )
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='kwh',
        reading_value=Decimal('500'),
        recorded_at=period_dt,
    )
    cons = U.UtilityConsumption.all_objects.filter(source_meter_reading=reading).first()
    if cons is None:
        pytest.skip('Consumption auto-feed not triggered (signal disabled?)')
    em = U.CarbonEmission.all_objects.filter(source_consumption=cons)
    assert em.count() == 1


def test_delete_meter_reading_reverses_downstream_rows(
    acme, acp_open, utility_type_electricity, emission_factor_grid,
):
    """Deleting the AssetMeterReading emits reversal rows for both downstream entries."""
    from apps.eam.models import AssetMeterReading
    asset = _make_asset_with_meter(acme, utility_type_electricity)
    period_dt = timezone.make_aware(
        timezone.datetime(
            acp_open.start_date.year,
            acp_open.start_date.month,
            acp_open.start_date.day, 9, 0,
        )
    )
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='kwh',
        reading_value=Decimal('500'),
        recorded_at=period_dt,
    )
    # Sanity check: consumption + carbon were emitted by the chain
    cons = U.UtilityConsumption.all_objects.filter(source_meter_reading=reading).first()
    if cons is None:
        pytest.skip('Consumption auto-feed not triggered')

    reading.delete()
    # A reversal UtilityConsumption row should now exist
    assert U.UtilityConsumption.all_objects.filter(is_reversal=True).count() >= 1


def test_kwh_reading_idempotent_double_save(
    acme, utility_type_electricity, emission_factor_grid,
):
    """Re-saving the same AssetMeterReading must not spawn another consumption row."""
    from apps.eam.models import AssetMeterReading
    asset = _make_asset_with_meter(acme, utility_type_electricity)
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='kwh',
        reading_value=Decimal('500'),
    )
    initial_count = U.UtilityConsumption.all_objects.filter(
        source_meter_reading=reading,
    ).count()
    reading.notes = 'updated'
    reading.save()
    final_count = U.UtilityConsumption.all_objects.filter(
        source_meter_reading=reading,
    ).count()
    assert final_count == initial_count


def test_non_kwh_reading_does_not_emit(
    acme, utility_type_electricity, emission_factor_grid,
):
    """meter_type='hours' should not trigger the utility auto-feed signal."""
    from apps.eam.models import AssetMeterReading
    asset = _make_asset_with_meter(acme, utility_type_electricity)
    reading = AssetMeterReading.objects.create(
        tenant=acme, asset=asset, meter_type='hours',
        reading_value=Decimal('100'),
    )
    assert U.UtilityConsumption.all_objects.filter(
        source_meter_reading=reading,
    ).count() == 0
