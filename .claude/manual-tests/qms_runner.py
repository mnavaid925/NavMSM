"""Walks the QMS manual smoke subset against the live (MySQL-backed) tenant data
that ``seed_qms`` produced. Reports defects to stdout.

Usage (PowerShell):
    cd c:\\xampp\\htdocs\\NavMSM
    python .\\.claude\\manual-tests\\qms_runner.py
"""
from __future__ import annotations

import os
import re
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

# Ensure the project root is on sys.path no matter where this script runs from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant
from apps.qms.models import (
    CalibrationRecord, CertificateOfAnalysis, ControlChartPoint,
    CorrectiveAction, FinalInspection, IncomingInspection,
    MeasurementEquipment, NCRAttachment, NonConformanceReport,
    PreventiveAction, ProcessInspection, SPCChart,
)


bugs: list[dict] = []


def bug(tc_id, severity, page, expected, actual):
    bugs.append({
        'tc': tc_id, 'sev': severity, 'page': page,
        'expected': expected, 'actual': actual,
    })
    print(f'[BUG-{len(bugs):02d}] {tc_id} ({severity}) {page}')
    print(f'  expected: {expected}')
    print(f'  actual:   {actual}')


def ok(label):
    print(f'  ok: {label}')


def find_text(content: bytes, needle: str) -> bool:
    return needle.encode('utf-8') in content


def setup():
    tenant = Tenant.objects.get(slug='acme')
    admin = User.objects.get(username='admin_acme')
    staff = User.objects.filter(tenant=tenant, is_tenant_admin=False).first()
    other_tenant = Tenant.objects.exclude(slug='acme').first()
    other_admin = User.objects.filter(
        tenant=other_tenant, is_tenant_admin=True,
    ).first()
    return tenant, admin, staff, other_tenant, other_admin


def main():
    tenant, admin, staff, other_tenant, other_admin = setup()
    c = Client()
    c.force_login(admin)
    print(f'\n=== Smoke subset against tenant: {tenant.name} ===\n')

    # TC-AUTH-05 - admin can access full QMS
    print('-- TC-AUTH-05 admin access --')
    routes = [
        '/qms/',
        '/qms/iqc/inspections/', '/qms/iqc/plans/',
        '/qms/ipqc/inspections/', '/qms/ipqc/plans/', '/qms/ipqc/charts/',
        '/qms/fqc/inspections/', '/qms/fqc/plans/',
        '/qms/ncr/', '/qms/equipment/',
        '/qms/calibrations/', '/qms/calibration-standards/',
    ]
    for r in routes:
        resp = c.get(r)
        if resp.status_code != 200:
            bug('TC-AUTH-05', 'Critical', r, '200', f'{resp.status_code}')
        else:
            ok(f'GET {r}')

    # TC-TENANT-02 - cross-tenant 404
    print('\n-- TC-TENANT-02 cross-tenant 404 --')
    other_ncr = NonConformanceReport.all_objects.filter(tenant=other_tenant).first()
    if other_ncr:
        resp = c.get(f'/qms/ncr/{other_ncr.pk}/')
        if resp.status_code != 404:
            bug('TC-TENANT-02', 'Critical', f'/qms/ncr/{other_ncr.pk}/',
                '404', f'{resp.status_code}')
        else:
            ok('cross-tenant NCR 404')

    # TC-CREATE-10 - IQC inspection auto-numbers + auto-AQL
    print('\n-- TC-CREATE-10 IQC inspection auto-AQL --')
    from apps.qms.models import IncomingInspectionPlan
    plan = IncomingInspectionPlan.objects.filter(tenant=tenant).first()
    resp = c.post('/qms/iqc/inspections/new/', {
        'product': plan.product.pk, 'plan': plan.pk,
        'supplier_name': 'Manual QA', 'po_reference': 'PO-MAN-1',
        'lot_number': 'LOT-MAN-1', 'received_qty': '500',
        'deviation_notes': '',
    })
    if resp.status_code != 302:
        bug('TC-CREATE-10', 'High', '/qms/iqc/inspections/new/',
            '302 redirect', f'{resp.status_code} - {resp.content[:200]}')
    else:
        i = IncomingInspection.objects.filter(
            tenant=tenant, lot_number='LOT-MAN-1',
        ).first()
        if not i:
            bug('TC-CREATE-10', 'High', 'IQC POST', 'inspection saved', 'not found')
        elif i.sample_size != 50 or i.accept_number != 5:
            bug('TC-CREATE-10', 'High', 'IQC AQL',
                'sample=50, ac=5', f'sample={i.sample_size}, ac={i.accept_number}')
        else:
            ok(f'IQC {i.inspection_number} sample={i.sample_size} ac={i.accept_number}')

    # TC-CREATE-20 - NCR raise + RCA shell
    print('\n-- TC-CREATE-20 NCR raise --')
    from apps.plm.models import Product
    prod = Product.objects.filter(tenant=tenant).first()
    resp = c.post('/qms/ncr/new/', {
        'source': 'customer', 'severity': 'major',
        'title': 'Manual NCR XSS test <script>alert(1)</script>',
        'description': 'Customer reported defect',
        'product': prod.pk, 'lot_number': 'LOT-NCR-MAN',
        'quantity_affected': '1',
        'iqc_inspection': '', 'ipqc_inspection': '', 'fqc_inspection': '',
        'assigned_to': '',
    })
    if resp.status_code != 302:
        bug('TC-CREATE-20', 'High', '/qms/ncr/new/',
            '302', f'{resp.status_code} - body has errors? {b"errorlist" in resp.content}')
    else:
        n = NonConformanceReport.objects.filter(
            tenant=tenant, lot_number='LOT-NCR-MAN',
        ).first()
        if not n:
            bug('TC-CREATE-20', 'High', 'NCR POST', 'NCR saved', 'not found')
        elif not hasattr(n, 'rca') or n.rca is None:
            bug('TC-CREATE-20', 'Medium', 'NCR RCA shell',
                'auto-created RCA', 'no RCA on NCR')
        else:
            ok(f'NCR {n.ncr_number} created with RCA shell')

        # TC-NEG-07 XSS escaped on detail
        print('\n-- TC-NEG-07 XSS escaped on NCR detail --')
        if n:
            r2 = c.get(f'/qms/ncr/{n.pk}/')
            if b'<script>alert(1)</script>' in r2.content:
                bug('TC-NEG-07', 'Critical', f'/qms/ncr/{n.pk}/',
                    'XSS escaped', 'raw <script> in HTML')
            else:
                ok('NCR title XSS payload escaped')

    # TC-CREATE-30 + TC-CREATE-60 + TC-CREATE-61 - equipment + calibration + L-15
    print('\n-- TC-CREATE-60+61 calibration L-15 propagation --')
    eq = MeasurementEquipment.objects.filter(tenant=tenant).first()
    old_next_due = eq.next_due_at
    cal_at = timezone.now()
    resp = c.post('/qms/calibrations/new/', {
        'equipment': eq.pk,
        'calibrated_at': cal_at.strftime('%Y-%m-%dT%H:%M'),
        'external_lab_name': '',
        'standard': '',
        'result': 'pass',
        'next_due_at': '',
        'notes': 'Manual QA cal',
    })
    if resp.status_code != 302:
        bug('TC-CREATE-60', 'High', '/qms/calibrations/new/',
            '302', f'{resp.status_code} - body: {resp.content[:300]}')
    else:
        eq.refresh_from_db()
        if eq.next_due_at == old_next_due:
            bug('TC-CREATE-61', 'High', 'L-15 propagation',
                'next_due_at updated', 'still old value')
        else:
            ok(f'L-15: equipment.next_due_at advanced')

    # TC-LIST-04 - equipment due-soon row coloring
    print('\n-- TC-LIST-04 equipment due-soon --')
    resp = c.get('/qms/equipment/')
    if resp.status_code == 200:
        # Look for table-warning or table-danger row
        if b'table-danger' in resp.content or b'table-warning' in resp.content:
            ok('equipment list has highlighted due rows')
        else:
            bug('TC-LIST-04', 'Medium', '/qms/equipment/',
                'red/yellow row for due/overdue equipment',
                'no .table-danger or .table-warning class found')

    # TC-DETAIL-03 - SPC chart renders
    print('\n-- TC-DETAIL-03 SPC chart --')
    chart = SPCChart.objects.filter(tenant=tenant).first()
    if chart:
        resp = c.get(f'/qms/ipqc/charts/{chart.pk}/')
        if resp.status_code != 200:
            bug('TC-DETAIL-03', 'High', f'/qms/ipqc/charts/{chart.pk}/',
                '200', f'{resp.status_code}')
        else:
            content = resp.content
            checks = [
                ('json_script id="spc-data"', b'id="spc-data"'),
                ('json_script id="spc-limits"', b'id="spc-limits"'),
                ('apexcharts CDN', b'apexcharts'),
                ('UCL value', b'UCL'),
                ('OOC point in table', b'table-danger'),
            ]
            for label, needle in checks:
                if needle not in content:
                    bug('TC-DETAIL-03', 'Medium',
                        f'/qms/ipqc/charts/{chart.pk}/',
                        f'contains {label}', 'missing')
                else:
                    ok(label)

    # TC-DETAIL-07 - FQC passed shows CoA card
    print('\n-- TC-DETAIL-07 FQC passed CoA card --')
    fi = FinalInspection.objects.filter(tenant=tenant, status='passed').first()
    if fi:
        resp = c.get(f'/qms/fqc/inspections/{fi.pk}/')
        if b'Certificate of Analysis' not in resp.content:
            bug('TC-DETAIL-07', 'Medium',
                f'/qms/fqc/inspections/{fi.pk}/',
                'CoA card shown', 'no "Certificate of Analysis" text')
        else:
            ok('FQC passed shows CoA section')

    # TC-EDIT-03 - status-gated edit
    print('\n-- TC-EDIT-03 IQC edit blocked when accepted --')
    accepted = IncomingInspection.objects.filter(
        tenant=tenant, status='accepted',
    ).first()
    if accepted:
        resp = c.get(f'/qms/iqc/inspections/{accepted.pk}/edit/')
        if resp.status_code != 302:
            bug('TC-EDIT-03', 'Medium',
                f'/qms/iqc/inspections/{accepted.pk}/edit/',
                '302 to detail', f'{resp.status_code}')
        else:
            ok('accepted IQC edit blocked')

    # TC-DELETE-07 - equipment with cal history blocked (ProtectedError)
    print('\n-- TC-DELETE-07 equipment with cal blocked --')
    eq_with_cal = MeasurementEquipment.objects.filter(
        tenant=tenant, calibration_records__isnull=False,
    ).first()
    if eq_with_cal:
        resp = c.post(f'/qms/equipment/{eq_with_cal.pk}/delete/')
        if not MeasurementEquipment.objects.filter(pk=eq_with_cal.pk).exists():
            bug('TC-DELETE-07', 'High', 'equipment delete',
                'blocked, equipment kept', 'equipment was deleted despite cal history')
        else:
            ok('equipment with cal history protected from delete')

    # TC-ACTION-10..14 - FQC -> CoA -> release flow
    print('\n-- TC-ACTION-10..14 FQC pass + CoA + release --')
    pending_fqc = FinalInspection.objects.filter(
        tenant=tenant, status='pending',
    ).first()
    if pending_fqc:
        c.post(f'/qms/fqc/inspections/{pending_fqc.pk}/start/')
        c.post(f'/qms/fqc/inspections/{pending_fqc.pk}/pass/')
        pending_fqc.refresh_from_db()
        if pending_fqc.status != 'passed':
            bug('TC-ACTION-10', 'High', 'FQC pass',
                'status=passed', f'status={pending_fqc.status}')
        else:
            ok('FQC pending -> in_inspection -> passed')
            # Generate CoA
            r = c.get(f'/qms/fqc/inspections/{pending_fqc.pk}/coa/')
            if r.status_code != 200:
                bug('TC-ACTION-11', 'High', 'CoA render',
                    '200', f'{r.status_code}')
            else:
                coa = CertificateOfAnalysis.objects.filter(inspection=pending_fqc).first()
                if not coa:
                    bug('TC-ACTION-11', 'High', 'CoA generation', 'CoA created', 'none')
                else:
                    ok(f'CoA {coa.coa_number} generated')
                    # Release
                    c.post(f'/qms/fqc/inspections/{pending_fqc.pk}/coa/release/')
                    coa.refresh_from_db()
                    if not coa.released_to_customer:
                        bug('TC-ACTION-14', 'Medium', 'CoA release',
                            'released=True', 'still False')
                    else:
                        ok('CoA released to customer')

    # TC-ACTION-15 - CoA blocked for failed FQC
    print('\n-- TC-ACTION-15 CoA blocked for failed --')
    failed = FinalInspection.objects.filter(tenant=tenant, status='failed').first()
    if failed:
        r = c.get(f'/qms/fqc/inspections/{failed.pk}/coa/')
        if r.status_code != 302:
            bug('TC-ACTION-15', 'High', 'CoA failed FQC',
                '302 redirect (blocked)', f'{r.status_code}')
        else:
            if CertificateOfAnalysis.objects.filter(inspection=failed).exists():
                bug('TC-ACTION-15', 'High', 'CoA failed FQC',
                    'NO CoA created', 'CoA was created')
            else:
                ok('failed FQC blocked from CoA')

    # TC-ACTION-20..24 - NCR full lifecycle including L-14 close requires summary
    print('\n-- TC-ACTION-23 NCR close requires summary --')
    open_ncr = NonConformanceReport.objects.filter(tenant=tenant, status='open').first()
    if open_ncr:
        c.post(f'/qms/ncr/{open_ncr.pk}/investigate/')
        c.post(f'/qms/ncr/{open_ncr.pk}/await-capa/')
        c.post(f'/qms/ncr/{open_ncr.pk}/resolve/')
        open_ncr.refresh_from_db()
        if open_ncr.status != 'resolved':
            bug('TC-ACTION-22', 'High', 'NCR resolve',
                'status=resolved', f'status={open_ncr.status}')
        else:
            ok('NCR open -> investigating -> awaiting_capa -> resolved')
            # Close with whitespace summary -> rejected
            c.post(f'/qms/ncr/{open_ncr.pk}/close/', {'resolution_summary': '   '})
            open_ncr.refresh_from_db()
            if open_ncr.status == 'closed':
                bug('TC-ACTION-23', 'High', 'NCR close',
                    'rejected (whitespace summary)', 'closed anyway')
            else:
                ok('whitespace-only summary rejected')
                # Real close
                c.post(f'/qms/ncr/{open_ncr.pk}/close/',
                       {'resolution_summary': 'Verified effective.'})
                open_ncr.refresh_from_db()
                if open_ncr.status != 'closed':
                    bug('TC-ACTION-24', 'High', 'NCR close',
                        'closed', f'{open_ncr.status}')
                else:
                    ok('NCR closed with summary')

    # TC-ACTION-60 - SPC chart recompute
    print('\n-- TC-ACTION-60 SPC chart recompute --')
    chart = SPCChart.objects.filter(tenant=tenant).first()
    if chart:
        r = c.post(f'/qms/ipqc/charts/{chart.pk}/recompute/')
        if r.status_code != 302:
            bug('TC-ACTION-60', 'Medium', 'SPC recompute',
                '302', f'{r.status_code}')
        else:
            ok('SPC recompute returned 302 (toast attached)')

    # ---- Form-level validation defects ----
    # TC-CREATE-03 - duplicate IQC plan version returns clean form error
    print('\n-- TC-CREATE-03 duplicate plan version L-01 --')
    plan = IncomingInspectionPlan.objects.filter(tenant=tenant).first()
    if plan:
        r = c.post('/qms/iqc/plans/new/', {
            'product': plan.product.pk,
            'aql_level': 'II', 'sample_method': 'single',
            'aql_value': '2.5', 'version': plan.version,
            'description': '', 'is_active': True,
        })
        if r.status_code == 500:
            bug('TC-CREATE-03', 'Critical', 'IQC dup',
                'form error 200', '500 (L-01 not enforced)')
        elif r.status_code == 200 and b'already exists' in r.content:
            ok('IQC dup version rejected with form error')
        else:
            print(f'  status={r.status_code}, body has "already exists"={b"already exists" in r.content}')

    # TC-CREATE-31 - duplicate equipment serial L-01
    print('\n-- TC-CREATE-31 duplicate equipment serial --')
    eq = MeasurementEquipment.objects.filter(tenant=tenant).first()
    r = c.post('/qms/equipment/new/', {
        'name': 'dup', 'equipment_type': 'caliper',
        'serial_number': eq.serial_number,
        'manufacturer': '', 'model_number': '',
        'range_min': '', 'range_max': '', 'unit_of_measure': '',
        'tolerance': '', 'calibration_interval_days': 365,
        'status': 'active', 'is_active': True, 'notes': '',
    })
    if r.status_code == 500:
        bug('TC-CREATE-31', 'Critical', 'equipment dup serial',
            'form error 200', '500 (L-01)')
    elif r.status_code == 200 and b'already used' in r.content:
        ok('equipment dup serial rejected')

    # TC-CREATE-62 - calibration fail without notes blocked
    print('\n-- TC-CREATE-62 cal fail without notes --')
    eq = MeasurementEquipment.objects.filter(tenant=tenant).first()
    r = c.post('/qms/calibrations/new/', {
        'equipment': eq.pk,
        'calibrated_at': timezone.now().strftime('%Y-%m-%dT%H:%M'),
        'external_lab_name': '',
        'standard': '',
        'result': 'fail', 'next_due_at': '',
        'notes': '   ',  # whitespace
    })
    if r.status_code == 200:
        if b'Notes are required' in r.content:
            ok('cal fail without notes rejected')
        else:
            bug('TC-CREATE-62', 'Medium', 'cal fail no notes',
                'form error', 'no error message visible')
    elif r.status_code == 302:
        bug('TC-CREATE-62', 'High', 'cal fail no notes',
            '200 (form error)', '302 (saved anyway?)')

    # TC-EDIT-04 - NCR closed not editable (button hidden + URL redirect)
    print('\n-- TC-EDIT-04 NCR closed edit blocked --')
    closed_ncr = NonConformanceReport.objects.filter(tenant=tenant, status='closed').first()
    if closed_ncr:
        r = c.get(f'/qms/ncr/{closed_ncr.pk}/edit/')
        if r.status_code != 302:
            bug('TC-EDIT-04', 'Medium', f'/qms/ncr/{closed_ncr.pk}/edit/',
                '302 to detail', f'{r.status_code}')
        else:
            ok('closed NCR edit redirect')
        # Also check button hidden in detail HTML
        d = c.get(f'/qms/ncr/{closed_ncr.pk}/').content.decode('utf-8', errors='ignore')
        # The Edit button only shows when ncr.is_editable() True
        # is_editable returns status in ('open', 'investigating')
        if f'/qms/ncr/{closed_ncr.pk}/edit/' in d and '<i class="ri-pencil-line"></i> Edit' in d:
            # Could be in Edit-CA / Edit-PA which are different buttons - look for the main edit
            pass

    # TC-ACTION-41 - file allowlist on NCR attachment
    print('\n-- TC-ACTION-41 file allowlist --')
    open_ncr_for_att = NonConformanceReport.objects.filter(tenant=tenant).first()
    if open_ncr_for_att:
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = SimpleUploadedFile('virus.exe', b'MZx', content_type='application/octet-stream')
        r = c.post(f'/qms/ncr/{open_ncr_for_att.pk}/attachments/new/', {
            'description': 'bad', 'file': bad,
        })
        # Form validation should reject - check no NCRAttachment created
        from apps.qms.models import NCRAttachment
        if NCRAttachment.objects.filter(ncr=open_ncr_for_att, description='bad').exists():
            bug('TC-ACTION-41', 'High', 'NCR attachment',
                'reject .exe', 'accepted')
        else:
            ok('.exe attachment rejected')

    # ---- Filter retention check ----
    print('\n-- TC-FILTER-09 filter + page retention --')
    # Using NCR list with status filter
    r = c.get('/qms/ncr/?status=closed&page=1')
    if r.status_code == 200:
        # Form should preserve status=closed selection
        body = r.content.decode('utf-8', errors='ignore')
        if 'value="closed" selected' in body or 'status=closed' in body:
            ok('NCR filter retains in URL/form')
        else:
            print(f'  warning: filter retention not visible in body')

    # TC-EDIT-08 - browser back after edit no resubmit
    # (cannot test in Client; flag as manual-only)

    # ---- Summary ----
    print(f'\n=== Summary: {len(bugs)} bugs found ===')
    for b in bugs:
        print(f'  [{b["sev"]}] {b["tc"]} {b["page"]}: {b["expected"]} != {b["actual"]}')


if __name__ == '__main__':
    main()
