"""Walks the EAM manual smoke subset against the live (MySQL-backed) tenant data
that ``seed_eam`` produced. Reports defects to stdout.

Usage (PowerShell):
    cd c:\\xampp\\htdocs\\NavMSM
    python .\\.claude\\manual-tests\\eam_walkthrough.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

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
from apps.eam.models import (
    Asset, AssetCategory, ConditionMonitoringPoint, ConditionReading,
    DowntimeEvent, FailurePrediction, MaintenancePlan,
    MaintenanceWorkOrder, PMSchedule, Tool,
)


bugs: list[dict] = []
oks: list[str] = []


def bug(tc, sev, page, expected, actual):
    bugs.append({
        'tc': tc, 'sev': sev, 'page': page,
        'expected': expected, 'actual': actual,
    })
    print(f'[BUG-{len(bugs):02d}] {tc} ({sev}) {page}')
    print(f'  expected: {expected}')
    print(f'  actual:   {actual}')


def ok(label):
    oks.append(label)
    print(f'  ok: {label}')


def find_text(content: bytes, needle: str) -> bool:
    return needle.encode('utf-8') in content


def setup():
    tenant = Tenant.objects.get(slug='acme')
    admin = User.objects.get(username='admin_acme')
    staff = User.objects.filter(
        tenant=tenant, is_tenant_admin=False,
    ).exclude(role='supplier').first()
    other_tenant = Tenant.objects.exclude(pk=tenant.pk).filter(is_active=True).first()
    other_admin = User.objects.filter(
        tenant=other_tenant, is_tenant_admin=True,
    ).first()
    return tenant, admin, staff, other_tenant, other_admin


def crawl_get_pages(c: Client, urls_with_labels: list[tuple[str, str, str]]):
    """Each tuple is (tc_id, label, url). Issue GET, fail on non-200."""
    for tc, label, url in urls_with_labels:
        r = c.get(url)
        if r.status_code != 200:
            bug(tc, 'High', url,
                'GET returns 200',
                f'GET returned {r.status_code}: {r.content[:200] if r.content else ""!r}')
            continue
        ok(f'{tc} {label} GET 200')


def main():
    tenant, admin, staff, other_tenant, other_admin = setup()
    c = Client()
    c.force_login(admin)
    print(f'\n=== EAM walkthrough against tenant: {tenant.name} ===\n')

    # --- TC-AUTH-05 + TC-LIST-01..12: every list/dashboard renders 200 ---
    print('-- crawl: every list page --')
    crawl_get_pages(c, [
        ('TC-LIST-01', 'dashboard', reverse('eam:index')),
        ('TC-LIST-02', 'asset list', reverse('eam:asset_list')),
        ('TC-LIST-04', 'category list', reverse('eam:category_list')),
        ('TC-LIST-05', 'pm plan list', reverse('eam:pmplan_list')),
        ('TC-LIST-06', 'pm schedule list', reverse('eam:pmschedule_list')),
        ('TC-LIST-07', 'monitoring point list', reverse('eam:condition_point_list')),
        ('TC-LIST-08', 'mwo list', reverse('eam:mwo_list')),
        ('TC-LIST-10', 'downtime list', reverse('eam:downtime_list')),
        ('TC-LIST-11', 'tool list', reverse('eam:tool_list')),
        ('TC-LIST-12', 'failure prediction list', reverse('eam:prediction_list')),
        ('TC-LIST-13', 'condition reading list', reverse('eam:condition_reading_list')),
        ('TC-LIST-14', 'meter reading list', reverse('eam:meter_reading_list')),
        ('TC-LIST-15', 'tool maintenance list', reverse('eam:tool_maintenance_list')),
    ])

    # --- create form GETs ---
    print('\n-- crawl: create form GETs --')
    crawl_get_pages(c, [
        ('TC-CREATE-01', 'category create form', reverse('eam:category_create')),
        ('TC-CREATE-03', 'asset create form', reverse('eam:asset_create')),
        ('TC-CREATE-07', 'pm plan create form', reverse('eam:pmplan_create')),
        ('TC-CREATE-X', 'pm schedule create form', reverse('eam:pmschedule_create')),
        ('TC-CREATE-10', 'monitoring point create form', reverse('eam:condition_point_create')),
        ('TC-CREATE-12', 'mwo create form', reverse('eam:mwo_create')),
        ('TC-CREATE-13', 'tool create form', reverse('eam:tool_create')),
    ])

    # --- detail pages for seeded primary records ---
    print('\n-- crawl: seeded detail pages --')
    asset = Asset.objects.filter(tenant=tenant).first()
    plan = MaintenancePlan.objects.filter(tenant=tenant).first()
    schedule = PMSchedule.objects.filter(tenant=tenant).first()
    point = ConditionMonitoringPoint.objects.filter(tenant=tenant).first()
    prediction = FailurePrediction.objects.filter(tenant=tenant).first()
    mwo_completed = MaintenanceWorkOrder.objects.filter(
        tenant=tenant, status='completed',
    ).first()
    mwo_scheduled = MaintenanceWorkOrder.objects.filter(
        tenant=tenant, status='scheduled',
    ).first()
    mwo_inprog = MaintenanceWorkOrder.objects.filter(
        tenant=tenant, status='in_progress',
    ).first()
    tool = Tool.objects.filter(tenant=tenant).first()
    mold = Tool.objects.filter(tenant=tenant, tool_type='mold').first()

    detail_targets = []
    if asset:
        detail_targets.append(('TC-DETAIL-01', f'asset {asset.tag}',
                               reverse('eam:asset_detail', args=[asset.pk])))
    if plan:
        detail_targets.append(('TC-DETAIL-PMPLAN', f'plan {plan.name}',
                               reverse('eam:pmplan_detail', args=[plan.pk])))
    if schedule:
        detail_targets.append(('TC-DETAIL-05', f'schedule {schedule.schedule_number}',
                               reverse('eam:pmschedule_detail', args=[schedule.pk])))
    if point:
        detail_targets.append(('TC-DETAIL-CMP', f'point {point.name}',
                               reverse('eam:condition_point_detail', args=[point.pk])))
    if prediction:
        detail_targets.append(('TC-DETAIL-10', 'prediction',
                               reverse('eam:prediction_detail', args=[prediction.pk])))
    if mwo_completed:
        detail_targets.append(('TC-DETAIL-07', f'mwo completed {mwo_completed.mwo_number}',
                               reverse('eam:mwo_detail', args=[mwo_completed.pk])))
    if mwo_scheduled:
        detail_targets.append(('TC-DETAIL-06', f'mwo scheduled {mwo_scheduled.mwo_number}',
                               reverse('eam:mwo_detail', args=[mwo_scheduled.pk])))
    if mwo_inprog:
        detail_targets.append(('TC-DETAIL-INPROG', f'mwo in_progress {mwo_inprog.mwo_number}',
                               reverse('eam:mwo_detail', args=[mwo_inprog.pk])))
    if tool:
        detail_targets.append(('TC-DETAIL-09', f'tool {tool.tool_id}',
                               reverse('eam:tool_detail', args=[tool.pk])))
    if mold and mold.pk != tool.pk:
        detail_targets.append(('TC-DETAIL-08', f'mold {mold.tool_id}',
                               reverse('eam:tool_detail', args=[mold.pk])))
    crawl_get_pages(c, detail_targets)

    # --- TC-LIST-09: completed MWO row in list page hides Edit + Delete ---
    print('\n-- TC-LIST-09: completed MWO list-row Edit/Delete hidden --')
    if mwo_completed:
        r = c.get(reverse('eam:mwo_list'))
        # Look for the completed MWO's edit URL and delete URL on the page.
        edit_url = reverse('eam:mwo_edit', args=[mwo_completed.pk])
        del_url = reverse('eam:mwo_delete', args=[mwo_completed.pk])
        # Edit must NOT appear next to the completed row; Delete also.
        if find_text(r.content, edit_url):
            bug('TC-LIST-09', 'High', '/eam/mwo/',
                'Completed MWO row hides Edit (pencil) action',
                f'Completed MWO {mwo_completed.mwo_number} edit URL is rendered: {edit_url}')
        else:
            ok('TC-LIST-09 completed MWO row hides Edit')
        if find_text(r.content, del_url):
            bug('TC-LIST-09b', 'High', '/eam/mwo/',
                'Completed MWO row hides Delete (bin) action',
                f'Completed MWO {mwo_completed.mwo_number} delete URL is rendered: {del_url}')
        else:
            ok('TC-LIST-09b completed MWO row hides Delete')

    # --- TC-DETAIL-07: completed MWO header has NO Start/Hold/Complete buttons ---
    print('\n-- TC-DETAIL-07: completed MWO header workflow buttons gone --')
    if mwo_completed:
        r = c.get(reverse('eam:mwo_detail', args=[mwo_completed.pk]))
        for label, urlname in [
            ('Start', 'eam:mwo_start'),
            ('Hold', 'eam:mwo_hold'),
            ('Resume', 'eam:mwo_resume'),
            ('Complete form', 'eam:mwo_complete'),
            ('Schedule', 'eam:mwo_schedule'),
            ('Cancel', 'eam:mwo_cancel'),
        ]:
            url = reverse(urlname, args=[mwo_completed.pk])
            if find_text(r.content, url):
                bug(f'TC-DETAIL-07-{label.lower()}', 'High',
                    reverse('eam:mwo_detail', args=[mwo_completed.pk]),
                    f'Completed MWO must NOT show {label} action',
                    f'Completed MWO renders URL {url}')
            else:
                ok(f'TC-DETAIL-07 completed MWO hides {label}')

    # --- TC-NEG-14: operator cannot reach asset_create ---
    print('\n-- TC-NEG-14: operator denied admin actions --')
    if staff:
        oc = Client()
        oc.force_login(staff)
        r = oc.get(reverse('eam:asset_create'))
        if r.status_code != 302:
            bug('TC-NEG-14', 'Critical', reverse('eam:asset_create'),
                'Operator hits 302 redirect from asset_create',
                f'Operator got {r.status_code}')
        else:
            ok('TC-NEG-14 operator redirected from asset_create')
        r = oc.post(reverse('eam:mwo_cancel', args=[mwo_scheduled.pk if mwo_scheduled else 0]))
        if mwo_scheduled:
            mwo_scheduled.refresh_from_db()
            if mwo_scheduled.status == 'cancelled':
                bug('TC-NEG-14b', 'Critical',
                    reverse('eam:mwo_cancel', args=[mwo_scheduled.pk]),
                    'Operator cannot cancel an MWO',
                    'Operator successfully cancelled the MWO')
            else:
                ok('TC-NEG-14b operator cannot cancel MWO')
    else:
        bug('TC-NEG-14', 'Low', '(no operator user)',
            'A non-admin tenant user must exist to test RBAC',
            'No staff user found; create one to run TC-NEG-14')

    # --- TC-TENANT-01: cross-tenant 404 ---
    print('\n-- TC-TENANT-01: cross-tenant 404 --')
    other_asset = Asset.objects.filter(tenant=other_tenant).first() if other_tenant else None
    if other_asset:
        r = c.get(reverse('eam:asset_detail', args=[other_asset.pk]))
        if r.status_code != 404:
            bug('TC-TENANT-01', 'Critical',
                reverse('eam:asset_detail', args=[other_asset.pk]),
                'Cross-tenant asset detail returns 404',
                f'Acme admin viewing Globex asset got {r.status_code}')
        else:
            ok('TC-TENANT-01 cross-tenant 404 enforced')

    # --- TC-INT-01: andon equipment alert auto-spawns breakdown MWO ---
    print('\n-- TC-INT-01: andon -> MWO auto-spawn --')
    from apps.mes.models import AndonAlert
    from apps.pps.models import WorkCenter
    wc = WorkCenter.objects.filter(tenant=tenant).first()
    if asset and wc:
        before = MaintenanceWorkOrder.all_objects.filter(tenant=tenant).count()
        andon = AndonAlert.objects.create(
            tenant=tenant,
            alert_number=f'ANDQA-{timezone.now().timestamp():.0f}',
            alert_type='equipment',
            severity='high',
            title='QA walkthrough equipment alert',
            message='Auto-test of EAM cross-module hook.',
            work_center=wc,
            raised_by=admin,
            raised_at=timezone.now(),
            asset=asset,
        )
        after = MaintenanceWorkOrder.all_objects.filter(tenant=tenant).count()
        if after != before + 1:
            bug('TC-INT-01', 'Critical', '(signal)',
                'Equipment-type andon with asset link spawns 1 breakdown MWO',
                f'Expected MWO count {before+1}, got {after}')
        else:
            spawned = MaintenanceWorkOrder.all_objects.filter(source_andon=andon).first()
            if not spawned:
                bug('TC-INT-01b', 'Critical', '(signal)',
                    'Spawned MWO carries source_andon FK',
                    'No MWO references the seeded andon')
            elif spawned.wo_type != 'breakdown':
                bug('TC-INT-01c', 'High', '(signal)',
                    'Spawned MWO is type=breakdown',
                    f'Got wo_type={spawned.wo_type}')
            else:
                ok('TC-INT-01 andon -> MWO spawn fires + sets source_andon + wo_type=breakdown')
                # idempotency: re-saving andon should not respawn
                andon.message = 'Edited message'
                andon.save()
                after2 = MaintenanceWorkOrder.all_objects.filter(tenant=tenant).count()
                if after2 != after:
                    bug('TC-INT-04', 'High', '(signal)',
                        'Re-saving andon does not duplicate the spawned MWO',
                        f'Count went from {after} to {after2}')
                else:
                    ok('TC-INT-04 andon re-save idempotent')
                # cleanup
                spawned.delete()
                andon.delete()

    # --- TC-INT-02: andon equipment WITHOUT asset link does not spawn ---
    print('\n-- TC-INT-02: equipment andon without asset does not spawn MWO --')
    if wc:
        before = MaintenanceWorkOrder.all_objects.filter(tenant=tenant).count()
        andon = AndonAlert.objects.create(
            tenant=tenant,
            alert_number=f'ANDQA2-{timezone.now().timestamp():.0f}',
            alert_type='equipment',
            severity='medium',
            title='QA andon no asset',
            work_center=wc,
            raised_by=admin,
            raised_at=timezone.now(),
        )
        after = MaintenanceWorkOrder.all_objects.filter(tenant=tenant).count()
        if after != before:
            bug('TC-INT-02', 'High', '(signal)',
                'Equipment andon without asset does NOT spawn MWO',
                f'MWO count moved from {before} to {after}')
        else:
            ok('TC-INT-02 equipment andon without asset skips spawn')
        andon.delete()

    # --- TC-ACTION-08: Generate Upcoming idempotency ---
    print('\n-- TC-ACTION-08: Generate Upcoming idempotent --')
    if plan and plan.is_active:
        before = PMSchedule.all_objects.filter(plan=plan).count()
        r = c.post(reverse('eam:pmplan_generate', args=[plan.pk]))
        if r.status_code != 302:
            bug('TC-ACTION-08', 'Medium',
                reverse('eam:pmplan_generate', args=[plan.pk]),
                'Generate Upcoming POST returns 302 redirect',
                f'Got {r.status_code}')
        else:
            after1 = PMSchedule.all_objects.filter(plan=plan).count()
            r = c.post(reverse('eam:pmplan_generate', args=[plan.pk]))
            after2 = PMSchedule.all_objects.filter(plan=plan).count()
            if after2 != after1:
                bug('TC-ACTION-08b', 'Medium', '(idempotency)',
                    '2nd Generate-Upcoming click does not create more rows',
                    f'Count moved from {after1} to {after2}')
            else:
                ok(f'TC-ACTION-08 Generate Upcoming idempotent (count stable at {after2})')

    # --- TC-ACTION-16: critical reading auto-spawns prediction (idempotent) ---
    print('\n-- TC-ACTION-16: critical reading auto-spawn (idempotent) --')
    if point and point.high_alarm:
        # First clear existing open predictions for this asset.
        FailurePrediction.all_objects.filter(
            tenant=tenant, asset=point.asset, status__in=('open', 'investigating'),
        ).delete()
        before = FailurePrediction.all_objects.filter(tenant=tenant).count()
        ConditionReading.objects.create(
            tenant=tenant, point=point,
            reading_value=point.high_alarm * Decimal('2'),
            recorded_by=admin,
        )
        after1 = FailurePrediction.all_objects.filter(tenant=tenant).count()
        if after1 != before + 1:
            bug('TC-ACTION-16', 'Critical', '(signal)',
                'First critical reading spawns 1 FailurePrediction',
                f'Count moved from {before} to {after1}')
        else:
            ok('TC-ACTION-16 first critical reading spawns 1 prediction')
            ConditionReading.objects.create(
                tenant=tenant, point=point,
                reading_value=point.high_alarm * Decimal('2.5'),
                recorded_by=admin,
            )
            after2 = FailurePrediction.all_objects.filter(tenant=tenant).count()
            if after2 != after1:
                bug('TC-ACTION-16b', 'High', '(signal)',
                    '2nd critical reading does NOT spawn duplicate prediction (open exists)',
                    f'Count moved from {after1} to {after2}')
            else:
                ok('TC-ACTION-16b 2nd critical reading skipped (idempotent)')

    # --- Filter dropdown tenant scoping: list pages must NOT show other-tenant FKs ---
    print('\n-- filter dropdowns are tenant-scoped --')
    other_asset = Asset.objects.filter(tenant=other_tenant).first() if other_tenant else None
    if other_asset:
        for tc, urlname in [
            ('TC-FILTER-tenant-asset', 'eam:asset_list'),
            ('TC-FILTER-tenant-mwo', 'eam:mwo_list'),
            ('TC-FILTER-tenant-pmplan', 'eam:pmplan_list'),
            ('TC-FILTER-tenant-downtime', 'eam:downtime_list'),
        ]:
            r = c.get(reverse(urlname))
            if find_text(r.content, f'value="{other_asset.pk}"'):
                # Tag for the foreign asset would only appear if its pk leaked into a select.
                bug(tc, 'High', reverse(urlname),
                    'Asset filter dropdown shows ONLY in-tenant assets',
                    f'Other-tenant asset pk {other_asset.pk} appears in dropdown')
            else:
                ok(f'{tc} {urlname} filter dropdowns tenant-scoped')

    # --- POST a new Asset via form (TC-CREATE-03) ---
    print('\n-- TC-CREATE-03 POST: create asset ---')
    cat = AssetCategory.objects.filter(tenant=tenant).first()
    if cat:
        r = c.post(reverse('eam:asset_create'), data={
            'name': f'Walkthrough QA Asset {timezone.now().timestamp():.0f}',
            'description': '',
            'category': cat.pk,
            'parent': '',
            'warehouse': '',
            'location_detail': '',
            'manufacturer': '',
            'model_number': '',
            'serial_number': '',
            'installation_date': '',
            'commissioning_date': '',
            'criticality': 'medium',
            'status': 'operational',
            'purchase_cost': '0',
            'current_value': '0',
            'warranty_expiry': '',
            'is_active': 'on',
            'notes': '',
        })
        if r.status_code != 302:
            bug('TC-CREATE-03', 'High', reverse('eam:asset_create'),
                'POST returns 302 redirect on successful create',
                f'Got {r.status_code}: {r.content[:300]!r}')
        else:
            ok('TC-CREATE-03 asset create POST returns 302')

    # --- Edit an MWO that is already completed should redirect with error toast ---
    print('\n-- TC-EDIT-05: Edit completed MWO blocked --')
    if mwo_completed:
        r = c.get(reverse('eam:mwo_edit', args=[mwo_completed.pk]))
        if r.status_code != 302:
            bug('TC-EDIT-05', 'High',
                reverse('eam:mwo_edit', args=[mwo_completed.pk]),
                'Editing a completed MWO redirects (status-gated)',
                f'Got {r.status_code}')
        else:
            ok('TC-EDIT-05 completed MWO edit redirects')

    # --- DELETE protected by audit children (TC-DELETE-04) ---
    print('\n-- TC-DELETE-04: asset with meter readings is PROTECT-blocked --')
    if asset:
        from apps.eam.models import AssetMeterReading
        if AssetMeterReading.all_objects.filter(asset=asset).exists():
            r = c.post(reverse('eam:asset_delete', args=[asset.pk]))
            asset.refresh_from_db()
            # Expect: redirect happened (302) AND asset still exists.
            still_exists = Asset.all_objects.filter(pk=asset.pk).exists()
            if not still_exists:
                bug('TC-DELETE-04', 'Critical',
                    reverse('eam:asset_delete', args=[asset.pk]),
                    'Asset with audit-trail children is PROTECT-blocked',
                    'Asset was deleted despite having AssetMeterReading rows')
            else:
                ok('TC-DELETE-04 asset with meter readings is PROTECT-blocked')

    # --- summary ---
    print('\n=== summary ===')
    print(f'OK:   {len(oks)}')
    print(f'BUGS: {len(bugs)}')

    out = PROJECT_ROOT / '.claude' / 'manual-tests' / 'eam_walkthrough_results.json'
    out.write_text(json.dumps({
        'tenant': tenant.slug,
        'oks': oks,
        'bugs': bugs,
    }, indent=2, default=str), encoding='utf-8')
    print(f'\nResults written to {out}')

    if bugs:
        sys.exit(1)


if __name__ == '__main__':
    main()
