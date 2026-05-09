"""seed_iot - Idempotent demo data for Module 15 (IoT & SCADA).

Per tenant:
    * 6 DeviceProtocol rows (tenant-NULL shared catalog) - get_or_create
    * 2 DeviceBroker rows (MQTT-LOCAL, OPCUA-LOCAL)
    * 6 Device rows linked to first 6 eam.Asset rows where present
    * ~24 DeviceTag rows (4 per device on average)
    * 5 LossReason rows
    * 4 AlertRule rows (high temp, high vibration, missing data, electrical zscore)
    * ~120 IoTReading rows (24h * 5 tags) with normal-noise values
    * 2 deliberately anomalous readings to verify the AnomalyDetection cascade
    * 6 DigitalTwin rows + 18 TwinStateAttribute rows
    * 1 completed TwinSimulationScenario + 1 TwinStateSnapshot
    * 7 days * 6 assets of OEEPeriod rows
    * ~30 MachineStateLog rows
    * ~5 EdgeProcessor rows

Idempotent guard: if Device.objects.filter(tenant=tenant).exists(): skip.
Honors --flush to wipe tenant-scoped IoT data first.
ASCII-only stdout (Lesson L-09).
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Tenant, set_current_tenant
from apps.iot import models as iot_models


PROTOCOL_SEED = [
    ('mqtt', 'MQTT', 1883),
    ('opc_ua', 'OPC-UA', 4840),
    ('modbus_tcp', 'Modbus TCP', 502),
    ('modbus_rtu', 'Modbus RTU', None),
    ('http_polling', 'HTTP Polling', 80),
    ('coap', 'CoAP', 5683),
]


class Command(BaseCommand):
    help = 'Seed Module 15 (IoT & SCADA) demo data per tenant'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Delete tenant-scoped IoT data first')
        parser.add_argument('--tenant', type=str, help='Restrict to a single tenant slug')

    def handle(self, *args, **options):
        # Step 1: protocols (shared catalog)
        for code, name, port in PROTOCOL_SEED:
            iot_models.DeviceProtocol.objects.get_or_create(
                code=code, defaults={'name': name, 'default_port': port},
            )
        self.stdout.write(f'Protocols: {iot_models.DeviceProtocol.objects.count()} rows.')

        tenants = Tenant.objects.all()
        if options.get('tenant'):
            tenants = tenants.filter(slug=options['tenant'])
        if not tenants.exists():
            self.stdout.write('No tenants found. Run seed_data first.')
            return

        for tenant in tenants:
            self._seed_tenant(tenant, flush=options.get('flush'))
        self.stdout.write(self.style.SUCCESS('seed_iot complete.'))
        self.stdout.write('Login as a tenant admin (e.g. admin_acme / Welcome@123) to view IoT data.')
        self.stdout.write('WARNING: Superuser admin has tenant=None and will see no IoT rows.')

    def _seed_tenant(self, tenant, flush=False):
        self.stdout.write(f'-> Tenant: {tenant.name} ({tenant.slug})')
        set_current_tenant(tenant)

        if flush:
            iot_models.AlertNotification.objects.filter(tenant=tenant).delete()
            iot_models.AnomalyDetection.objects.filter(tenant=tenant).delete()
            iot_models.AlertRule.objects.filter(tenant=tenant).delete()
            iot_models.OEEPeriod.objects.filter(tenant=tenant).delete()
            iot_models.MachineStateLog.objects.filter(tenant=tenant).delete()
            iot_models.LossReason.objects.filter(tenant=tenant).delete()
            iot_models.TwinStateSnapshot.objects.filter(tenant=tenant).delete()
            iot_models.TwinSimulationScenario.objects.filter(tenant=tenant).delete()
            iot_models.TwinStateAttribute.objects.filter(tenant=tenant).delete()
            iot_models.DigitalTwin.objects.filter(tenant=tenant).delete()
            iot_models.EdgeProcessor.objects.filter(tenant=tenant).delete()
            iot_models.StreamMetric.objects.filter(tenant=tenant).delete()
            iot_models.IoTReading.objects.filter(tenant=tenant).delete()
            iot_models.IoTReadingBatch.objects.filter(tenant=tenant).delete()
            iot_models.DeviceTag.objects.filter(tenant=tenant).delete()
            iot_models.Device.objects.filter(tenant=tenant).delete()
            iot_models.DeviceBroker.objects.filter(tenant=tenant).delete()

        if iot_models.Device.objects.filter(tenant=tenant).exists():
            self.stdout.write('   already seeded; use --flush to re-seed.')
            return

        with transaction.atomic():
            brokers = self._brokers(tenant)
            devices = self._devices(tenant, brokers)
            tags = self._tags(tenant, devices)
            self._loss_reasons(tenant)
            self._alert_rules(tenant, devices, tags)
            self._readings(tenant, tags)
            self._digital_twins(tenant, devices, tags)
            self._oee(tenant)
            self._edge_processors(tenant, tags)

    def _brokers(self, tenant):
        mqtt = iot_models.DeviceProtocol.objects.get(code='mqtt')
        opcua = iot_models.DeviceProtocol.objects.get(code='opc_ua')
        return [
            iot_models.DeviceBroker.objects.create(
                tenant=tenant, name='MQTT-LOCAL', protocol=mqtt,
                host='broker.local', port=1883, status='active',
                last_heartbeat_at=timezone.now(),
            ),
            iot_models.DeviceBroker.objects.create(
                tenant=tenant, name='OPCUA-LOCAL', protocol=opcua,
                host='opc.local', port=4840, status='active',
                last_heartbeat_at=timezone.now(),
            ),
        ]

    def _devices(self, tenant, brokers):
        try:
            from apps.eam.models import Asset
            assets = list(Asset.objects.filter(tenant=tenant).order_by('asset_number')[:6])
        except Exception:  # noqa: BLE001
            assets = []
        mqtt_b, opcua_b = brokers[0], brokers[1]
        names = ['SENSOR-PUMP-01', 'SENSOR-MOTOR-01', 'PLC-CNC-LATHE-01',
                 'PLC-CNC-MILL-01', 'SENSOR-CONV-01', 'GATEWAY-HVAC-01']
        types = ['sensor_node', 'sensor_node', 'plc', 'plc', 'sensor_node', 'edge_gateway']
        out = []
        for i, name in enumerate(names):
            broker = mqtt_b if i % 2 == 0 else opcua_b
            asset = assets[i] if i < len(assets) else None
            d = iot_models.Device.objects.create(
                tenant=tenant, name=name, broker=broker, protocol=broker.protocol,
                asset=asset, device_type=types[i],
                serial_number=f'SN{tenant.slug.upper()[:3]}{i+1:03d}',
                firmware_version='2.4.0', status='active',
                last_seen_at=timezone.now(),
            )
            out.append(d)
        return out

    def _tags(self, tenant, devices):
        tag_specs = [
            ('temperature', 'plant/{}/temp_c', 'float', 'C'),
            ('vibration_x', 'plant/{}/vib_x_mm_s', 'float', 'mm/s'),
            ('pressure', 'plant/{}/pressure_psi', 'float', 'psi'),
            ('electrical_load', 'plant/{}/load_kw', 'float', 'kW'),
            ('machine_state', 'plant/{}/state', 'int', ''),
        ]
        tags_by_device = {}
        for d in devices:
            tags = []
            for spec_name, addr_tmpl, dtype, unit in tag_specs:
                t = iot_models.DeviceTag.objects.create(
                    tenant=tenant, device=d, name=spec_name,
                    address=addr_tmpl.format(d.name),
                    data_type=dtype, unit=unit, sampling_interval_seconds=60,
                    is_active=True,
                )
                tags.append(t)
            tags_by_device[d.pk] = tags
        return tags_by_device

    def _loss_reasons(self, tenant):
        rows = [
            ('PLANNED_MAINT', 'Planned Maintenance', 'availability', True),
            ('BREAKDOWN', 'Equipment Breakdown', 'availability', False),
            ('STARVED', 'Material Starved', 'availability', False),
            ('MICRO_STOP', 'Micro Stoppage', 'performance', False),
            ('SETUP_CHANGEOVER', 'Setup / Changeover', 'performance', True),
        ]
        for code, name, cat, planned in rows:
            iot_models.LossReason.objects.create(
                tenant=tenant, code=code, name=name, category=cat,
                is_planned=planned, is_active=True,
            )

    def _alert_rules(self, tenant, devices, tags):
        rules = []
        # Build temperature threshold for first device's temp tag
        if devices and tags.get(devices[0].pk):
            temp_tag = tags[devices[0].pk][0]
            r = iot_models.AlertRule.objects.create(
                tenant=tenant, name='High Temperature',
                device_tag=temp_tag, condition_type='threshold_high',
                threshold_high=Decimal('85.00'), severity='high',
                notification_channels='in_app,mes_andon',
                cooldown_seconds=600, is_active=True,
            )
            rules.append(r)
        if devices and tags.get(devices[1].pk):
            vib_tag = tags[devices[1].pk][1]
            r = iot_models.AlertRule.objects.create(
                tenant=tenant, name='High Vibration',
                device_tag=vib_tag, condition_type='threshold_high',
                threshold_high=Decimal('10.00'), severity='critical',
                notification_channels='in_app,email,mes_andon',
                cooldown_seconds=300, is_active=True,
            )
            rules.append(r)
        if devices:
            r = iot_models.AlertRule.objects.create(
                tenant=tenant, name='Electrical Z-Score',
                scope_device=devices[0], condition_type='zscore',
                severity='medium', notification_channels='in_app',
                cooldown_seconds=900, is_active=True,
            )
            rules.append(r)
        if devices and tags.get(devices[0].pk):
            ml_tag = tags[devices[0].pk][3]
            r = iot_models.AlertRule.objects.create(
                tenant=tenant, name='Missing Data Watchdog',
                device_tag=ml_tag, condition_type='missing_data',
                window_seconds=300, severity='low',
                notification_channels='in_app',
                cooldown_seconds=3600, is_active=True,
            )
            rules.append(r)
        return rules

    def _readings(self, tenant, tags):
        batch = iot_models.IoTReadingBatch.objects.create(
            tenant=tenant, source_format='seed', status='processed', notes='seed fixture',
        )
        now = timezone.now()
        # 24h * 5 tags per device * 6 devices = 720 rows; use 4-tag x 6-device x 5 hours = 120 rows
        for device_pk, tag_list in tags.items():
            for tag in tag_list[:4]:
                for h in range(5):
                    ts = now - timedelta(hours=h * 4 + random.randint(0, 60))
                    if tag.data_type == 'int':
                        v = Decimal(random.randint(0, 2))
                    elif tag.name == 'temperature':
                        v = Decimal(str(round(random.uniform(60, 75), 2)))
                    elif tag.name == 'vibration_x':
                        v = Decimal(str(round(random.uniform(2, 7), 2)))
                    elif tag.name == 'pressure':
                        v = Decimal(str(round(random.uniform(40, 60), 2)))
                    elif tag.name == 'electrical_load':
                        v = Decimal(str(round(random.uniform(20, 40), 2)))
                    else:
                        v = Decimal('0')
                    iot_models.IoTReading.objects.create(
                        tenant=tenant, device_tag=tag, timestamp=ts,
                        value_numeric=v, quality='good', source='seed', batch=batch,
                    )
        # 2 deliberately anomalous readings to fire alert rules
        if tags:
            first_device_tags = next(iter(tags.values()))
            if first_device_tags:
                temp_tag = first_device_tags[0]
                iot_models.IoTReading.objects.create(
                    tenant=tenant, device_tag=temp_tag, timestamp=now,
                    value_numeric=Decimal('92.5'), quality='good',
                    source='seed', batch=batch,
                )
            second_device_tags = list(tags.values())[1] if len(tags) > 1 else None
            if second_device_tags:
                vib_tag = second_device_tags[1]
                iot_models.IoTReading.objects.create(
                    tenant=tenant, device_tag=vib_tag, timestamp=now,
                    value_numeric=Decimal('15.2'), quality='good',
                    source='seed', batch=batch,
                )

    def _digital_twins(self, tenant, devices, tags):
        for device in devices[:3]:  # first 3 get twins
            asset = device.asset
            twin = iot_models.DigitalTwin.objects.create(
                tenant=tenant, name=f'Twin {device.name}', asset=asset,
                twin_type='machine', model_version='1.0.0', status='active',
            )
            tag_list = tags.get(device.pk, [])
            for t in tag_list[:3]:
                iot_models.TwinStateAttribute.objects.create(
                    tenant=tenant, twin=twin, name=t.name,
                    attribute_type='measurement', source_tag=t, unit=t.unit,
                )
            iot_models.TwinStateAttribute.objects.create(
                tenant=tenant, twin=twin, name='health_score',
                attribute_type='derived',
                formula='100 - (temperature - 60) * 2',
                unit='%',
            )
            # 1 completed scenario per first twin
            if device == devices[0]:
                scenario = iot_models.TwinSimulationScenario.objects.create(
                    tenant=tenant, twin=twin, name='Baseline',
                    description='Default operating point',
                    input_payload={'temperature': 68, 'vibration_x': 4.0},
                    expected_output={},
                    status='completed',
                    result_payload={'computed': {'health_score': '84'}, 'matched_expected': True, 'errors': []},
                    run_at=timezone.now(),
                )
                iot_models.TwinStateSnapshot.objects.create(
                    tenant=tenant, twin=twin, snapshot_at=timezone.now(),
                    state_payload={'temperature': '68', 'health_score': '84'},
                    triggered_by='manual',
                )

    def _oee(self, tenant):
        try:
            from apps.eam.models import Asset
            assets = list(Asset.objects.filter(tenant=tenant)[:3])
        except Exception:  # noqa: BLE001
            return
        if not assets:
            return
        today = timezone.now().date()
        for d in range(7):
            period_date = today - timedelta(days=d)
            for a in assets:
                p = iot_models.OEEPeriod(
                    tenant=tenant, asset=a, shift=None, period_date=period_date,
                    planned_run_minutes=Decimal('480'),
                    run_minutes=Decimal(str(random.randint(380, 470))),
                    ideal_cycle_seconds=Decimal('60'),
                    total_count=Decimal(str(random.randint(380, 470))),
                    good_count=Decimal(str(random.randint(360, 460))),
                    scrap_count=Decimal(str(random.randint(0, 10))),
                )
                p.save()
                # Add a state log per period
                start_dt = datetime.combine(period_date, datetime.min.time(), tzinfo=timezone.get_current_timezone())
                iot_models.MachineStateLog.objects.create(
                    tenant=tenant, asset=a, state='running',
                    started_at=start_dt, ended_at=start_dt + timedelta(hours=8),
                    source='seed',
                )

    def _edge_processors(self, tenant, tags):
        if not tags:
            return
        first_device_tags = next(iter(tags.values()))
        if not first_device_tags:
            return
        iot_models.EdgeProcessor.objects.create(
            tenant=tenant, name='Temp 5-min Avg',
            input_tag=first_device_tags[0], transform_type='rolling_avg',
            window_seconds=300, is_active=True,
        )
        iot_models.EdgeProcessor.objects.create(
            tenant=tenant, name='Vibration Threshold Count',
            input_tag=first_device_tags[1], transform_type='threshold_count',
            window_seconds=600, threshold_value=Decimal('8'), is_active=True,
        )
