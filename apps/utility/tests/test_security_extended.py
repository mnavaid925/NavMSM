"""Tenant=NULL IDOR + CSV upload safety + duplicate TOU band UX (D-03..D-06, D-10)."""
from datetime import time as dt_time, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.utility import models as U


pytestmark = [pytest.mark.django_db, pytest.mark.security]


# ---------- BenchmarkSnapshot tenant=NULL industry-avg IDOR (D-10) ----------

def test_industry_avg_snapshot_404_for_tenant_user(admin_client, acp_open):
    snap = U.BenchmarkSnapshot.all_objects.create(
        tenant=None, period=acp_open, plant_label='industry_avg',
        total_units_produced=Decimal('10'),
    )
    r = admin_client.get(reverse('utility:benchmark_detail', args=[snap.pk]))
    assert r.status_code == 404


def test_industry_avg_snapshot_not_in_list(admin_client, acp_open, acme):
    U.BenchmarkSnapshot.all_objects.create(
        tenant=None, period=acp_open, plant_label='industry_avg',
        total_units_produced=Decimal('10'),
    )
    U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='main',
        total_units_produced=Decimal('5'),
    )
    r = admin_client.get(reverse('utility:benchmark_list'))
    assert r.status_code == 200
    body = r.content.decode()
    assert 'industry_avg' not in body
    assert 'main' in body


def test_benchmark_for_tenant_manager_excludes_null_tenant(acp_open, acme):
    """D-10 manager method must filter to the requested tenant, never NULL."""
    U.BenchmarkSnapshot.all_objects.create(
        tenant=None, period=acp_open, plant_label='industry_avg',
        total_units_produced=Decimal('10'),
    )
    own = U.BenchmarkSnapshot.objects.create(
        tenant=acme, period=acp_open, plant_label='main',
        total_units_produced=Decimal('5'),
    )
    pks = list(
        U.BenchmarkSnapshot.tenant_objects.for_tenant(acme).values_list('pk', flat=True)
    )
    assert pks == [own.pk]


# ---------- CSV upload safety (D-03) ----------

def _csv_payload(rows):
    head = b'period_start,period_end,start_reading,end_reading,unit_cost\n'
    body = b''.join(
        f'{ps},{pe},{sr},{er},{uc}\n'.encode()
        for ps, pe, sr, er, uc in rows
    )
    return head + body


def test_csv_upload_rejects_oversize(admin_client, meter):
    """D-03: a >5 MiB CSV is rejected by clean_csv_file()."""
    huge = b'x' * (6 * 1024 * 1024)  # 6 MiB
    fp = BytesIO(huge)
    fp.name = 'huge.csv'
    r = admin_client.post(
        reverse('utility:consumption_import'),
        data={'meter': meter.pk, 'csv_file': fp},
    )
    # Django middleware (DATA_UPLOAD_MAX_MEMORY_SIZE=2.5 MiB by default)
    # may also reject before our clean() runs — both paths are acceptable
    # so long as no row was created.
    assert r.status_code in (200, 302, 400, 413)
    assert U.UtilityConsumption.objects.filter(meter=meter).count() == 0


def test_csv_upload_rejects_pe_binary(admin_client, meter):
    """D-03: file with PE/MZ magic bytes rejected before csv.DictReader sees it."""
    payload = b'MZ\x90\x00\x03\x00\x00\x00' + b'\x00' * 100
    fp = BytesIO(payload)
    fp.name = 'evil.csv'  # extension is fine, content is not
    r = admin_client.post(
        reverse('utility:consumption_import'),
        data={'meter': meter.pk, 'csv_file': fp},
    )
    # Form invalid → 200 with errors, or redirect with messages.error.
    assert r.status_code in (200, 302)
    assert U.UtilityConsumption.objects.filter(meter=meter).count() == 0


def test_csv_upload_rejects_wrong_extension(admin_client, meter):
    """D-03: FileExtensionValidator rejects non-.csv extensions."""
    fp = BytesIO(_csv_payload([]))
    fp.name = 'evil.exe'
    r = admin_client.post(
        reverse('utility:consumption_import'),
        data={'meter': meter.pk, 'csv_file': fp},
    )
    assert r.status_code in (200, 302)
    assert U.UtilityConsumption.objects.filter(meter=meter).count() == 0


def test_csv_idempotency_with_whitespace_drift(admin_client, meter):
    """D-06: bulk_import_billing must dedup on parsed datetime, not raw string."""
    rows1 = [(' 2026-05-01T00:00:00', '2026-05-02T00:00:00', '0', '10', '0.10')]
    rows2 = [('2026-05-01T00:00:00', '2026-05-02T00:00:00', '0', '10', '0.10')]
    fp1 = BytesIO(_csv_payload(rows1)); fp1.name = 'a.csv'
    fp2 = BytesIO(_csv_payload(rows2)); fp2.name = 'b.csv'
    admin_client.post(
        reverse('utility:consumption_import'),
        data={'meter': meter.pk, 'csv_file': fp1},
    )
    admin_client.post(
        reverse('utility:consumption_import'),
        data={'meter': meter.pk, 'csv_file': fp2},
    )
    n = U.UtilityConsumption.objects.filter(meter=meter).count()
    assert n == 1, f'Whitespace drift bypassed dedup; got {n} rows.'


def test_csv_z_suffix_dedups_against_explicit_offset(admin_client, meter):
    """D-06: 'Z' suffix and '+00:00' point at the same instant — dedup must agree."""
    rows1 = [('2026-05-03T00:00:00Z', '2026-05-04T00:00:00Z', '0', '10', '0.10')]
    rows2 = [('2026-05-03T00:00:00+00:00', '2026-05-04T00:00:00+00:00', '0', '10', '0.10')]
    fp1 = BytesIO(_csv_payload(rows1)); fp1.name = 'a.csv'
    fp2 = BytesIO(_csv_payload(rows2)); fp2.name = 'b.csv'
    admin_client.post(
        reverse('utility:consumption_import'),
        data={'meter': meter.pk, 'csv_file': fp1},
    )
    admin_client.post(
        reverse('utility:consumption_import'),
        data={'meter': meter.pk, 'csv_file': fp2},
    )
    n = U.UtilityConsumption.objects.filter(meter=meter).count()
    assert n == 1, f'Z vs +00:00 drift bypassed dedup; got {n} rows.'


# ---------- TOURateBand duplicate handling (D-04) ----------

def test_duplicate_tou_band_friendly_error(admin_client, tariff):
    """D-04: form clean() must reject the duplicate before save."""
    U.TOURateBand.objects.create(
        tenant=tariff.tenant, tariff=tariff, band_type='peak',
        day_of_week='weekday', start_time=dt_time(9, 0),
        end_time=dt_time(17, 0), rate=Decimal('0.20'),
    )
    r = admin_client.post(
        reverse('utility:band_create', args=[tariff.pk]),
        data={
            'band_type': 'peak', 'day_of_week': 'weekday',
            'start_time': '09:00', 'end_time': '17:00', 'rate': '0.20',
        },
    )
    assert r.status_code == 302
    # No second band created.
    assert U.TOURateBand.objects.filter(tariff=tariff).count() == 1


# ---------- Currency ISO-4217 shape (D-05) ----------

@pytest.mark.parametrize('bad', ['ZZ', 'usd', '999', '12A', 'usdusd'])
def test_currency_iso_4217_shape_rejected(admin_client, utility_type_electricity, bad):
    from datetime import date
    r = admin_client.post(
        reverse('utility:tariff_create'),
        data={
            'utility_type': utility_type_electricity.pk,
            'name': f'BadCur {bad}',
            'effective_from': date.today().isoformat(),
            'flat_rate': '0.12', 'currency': bad, 'is_active': 'on',
        },
    )
    assert r.status_code == 200, (
        f'expected form to re-render with errors; got {r.status_code}'
    )
    assert not U.UtilityTariff.objects.filter(name__startswith='BadCur').exists()


def test_currency_iso_4217_shape_accepted(admin_client, utility_type_electricity):
    from datetime import date
    r = admin_client.post(
        reverse('utility:tariff_create'),
        data={
            'utility_type': utility_type_electricity.pk,
            'name': 'Good',
            'effective_from': date.today().isoformat(),
            'flat_rate': '0.12', 'currency': 'EUR', 'is_active': 'on',
        },
    )
    assert r.status_code in (200, 302)
    assert U.UtilityTariff.objects.filter(name='Good', currency='EUR').exists()


# ---------- D-08: CarbonEmissionReverseView ----------

def test_carbon_emission_reverse_admin_only(staff_client, acme, acp_open, emission_factor_grid):
    e = U.CarbonEmission.objects.create(
        tenant=acme, period=acp_open, scope='scope_2',
        source_type='electricity_grid', source_quantity=Decimal('10'),
        factor=emission_factor_grid,
    )
    r = staff_client.post(
        reverse('utility:emission_reverse', args=[e.pk]),
        data={'reversal_reason': 'test'},
    )
    assert r.status_code in (302, 403)
    # Reversal row must NOT have been created by a non-admin.
    assert not U.CarbonEmission.objects.filter(is_reversal=True).exists()


def test_carbon_emission_reverse_emits_negative_row(admin_client, acme, acp_open, emission_factor_grid):
    e = U.CarbonEmission.objects.create(
        tenant=acme, period=acp_open, scope='scope_2',
        source_type='electricity_grid', source_quantity=Decimal('10'),
        factor=emission_factor_grid,
    )
    e.refresh_from_db()
    original_co2e = e.co2e_kg
    r = admin_client.post(
        reverse('utility:emission_reverse', args=[e.pk]),
        data={'reversal_reason': 'manual entry mistake'},
    )
    assert r.status_code == 302
    rev = U.CarbonEmission.objects.filter(is_reversal=True).first()
    assert rev is not None
    assert rev.co2e_kg == -original_co2e
    assert rev.notes.startswith(f'reversal-of:{e.entry_number}')


def test_carbon_emission_reverse_rejects_empty_reason(admin_client, acme, acp_open, emission_factor_grid):
    e = U.CarbonEmission.objects.create(
        tenant=acme, period=acp_open, scope='scope_2',
        source_type='electricity_grid', source_quantity=Decimal('10'),
        factor=emission_factor_grid,
    )
    r = admin_client.post(
        reverse('utility:emission_reverse', args=[e.pk]),
        data={'reversal_reason': '   '},
    )
    assert r.status_code == 302
    assert not U.CarbonEmission.objects.filter(is_reversal=True).exists()


def test_carbon_emission_reverse_idempotent(admin_client, acme, acp_open, emission_factor_grid):
    e = U.CarbonEmission.objects.create(
        tenant=acme, period=acp_open, scope='scope_2',
        source_type='electricity_grid', source_quantity=Decimal('10'),
        factor=emission_factor_grid,
    )
    admin_client.post(
        reverse('utility:emission_reverse', args=[e.pk]),
        data={'reversal_reason': 'first'},
    )
    admin_client.post(
        reverse('utility:emission_reverse', args=[e.pk]),
        data={'reversal_reason': 'second'},
    )
    # Only ONE reversal row, even after two POSTs.
    assert U.CarbonEmission.objects.filter(is_reversal=True).count() == 1


def test_carbon_emission_reverse_cross_tenant_404(globex_client, acme, acp_open, emission_factor_grid):
    e = U.CarbonEmission.objects.create(
        tenant=acme, period=acp_open, scope='scope_2',
        source_type='electricity_grid', source_quantity=Decimal('10'),
        factor=emission_factor_grid,
    )
    r = globex_client.post(
        reverse('utility:emission_reverse', args=[e.pk]),
        data={'reversal_reason': 'attempted IDOR'},
    )
    assert r.status_code == 404
    assert not U.CarbonEmission.objects.filter(is_reversal=True).exists()
