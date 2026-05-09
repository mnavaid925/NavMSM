"""Module 15 - IoT & SCADA Integration views.

Class-based views mirroring apps/utility/views.py + apps/eam/views.py.

RBAC (L-10):
    * Read surfaces: TenantRequiredMixin (logged in + tenant attached)
    * Write/workflow surfaces: TenantAdminRequiredMixin
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.views import TenantAdminRequiredMixin, TenantRequiredMixin

from . import forms, models
from .services import (
    ingestion as ingest_svc,
    oee as oee_svc,
    twin as twin_svc,
    twin_simulation as twin_sim_svc,
)


PAGE_SIZE = 25


def _paginate(qs, request, size=PAGE_SIZE):
    paginator = Paginator(qs, size)
    page = request.GET.get('page', 1)
    try:
        return paginator.page(page)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def _atomic_status_transition(model, pk, tenant, from_states, to_state, extra_fields=None):
    fields = {'status': to_state}
    if extra_fields:
        fields.update(extra_fields)
    with transaction.atomic():
        rowcount = model.objects.filter(
            pk=pk, tenant=tenant, status__in=from_states,
        ).update(**fields)
    return rowcount > 0


# ============================================================================
# Dashboard
# ============================================================================

class IndexView(TenantRequiredMixin, View):
    template_name = 'iot/index.html'

    def get(self, request):
        tenant = request.tenant
        if tenant is None:
            return render(request, self.template_name, {
                'kpi': {}, 'recent_readings': [], 'open_anomalies': [],
                'oee_chart': [], 'anomaly_chart': [],
            })
        now = timezone.now()
        past_24h = now - timedelta(hours=24)
        today = now.date()

        kpi = {
            'device_count': models.Device.objects.filter(tenant=tenant, status='active').count(),
            'broker_count': models.DeviceBroker.objects.filter(tenant=tenant, status='active').count(),
            'readings_24h': models.IoTReading.objects.filter(tenant=tenant, timestamp__gte=past_24h).count(),
            'open_anomalies': models.AnomalyDetection.objects.filter(
                tenant=tenant, status__in=('new', 'acknowledged'),
            ).count(),
            'twin_count': models.DigitalTwin.objects.filter(tenant=tenant, status='active').count(),
            'oee_today': models.OEEPeriod.objects.filter(
                tenant=tenant, period_date=today,
            ).aggregate(avg=Sum('oee_pct'))['avg'] or Decimal('0'),
        }
        recent_readings = list(
            models.IoTReading.objects.filter(tenant=tenant)
            .select_related('device_tag', 'device_tag__device')
            .order_by('-timestamp')[:8]
        )
        open_anomalies = list(
            models.AnomalyDetection.objects.filter(
                tenant=tenant, status__in=('new', 'acknowledged'),
            ).select_related('rule').order_by('-detected_at')[:8]
        )
        oee_rows = (
            models.OEEPeriod.objects.filter(
                tenant=tenant, period_date__gte=today - timedelta(days=14),
            )
            .values('period_date')
            .annotate(
                a=Sum('availability_pct'), p=Sum('performance_pct'),
                q=Sum('quality_pct'), o=Sum('oee_pct'), n=Count('id'),
            )
            .order_by('period_date')
        )
        oee_chart = [
            {
                'day': r['period_date'].strftime('%m-%d'),
                'availability': float(r['a'] / r['n']) if r['n'] else 0,
                'performance': float(r['p'] / r['n']) if r['n'] else 0,
                'quality': float(r['q'] / r['n']) if r['n'] else 0,
                'oee': float(r['o'] / r['n']) if r['n'] else 0,
            }
            for r in oee_rows
        ]
        anomaly_rows = list(
            models.AnomalyDetection.objects.filter(
                tenant=tenant, detected_at__gte=now - timedelta(days=30),
            ).values_list('detected_at', 'severity')
        )
        days = {}
        for dt, sev in anomaly_rows:
            key = dt.date().strftime('%m-%d')
            d = days.setdefault(key, Counter())
            d[sev] += 1
        anomaly_chart = [
            {
                'day': k,
                'critical': v.get('critical', 0),
                'high': v.get('high', 0),
                'medium': v.get('medium', 0),
                'low': v.get('low', 0),
            }
            for k, v in sorted(days.items())
        ]

        return render(request, self.template_name, {
            'kpi': kpi,
            'recent_readings': recent_readings,
            'open_anomalies': open_anomalies,
            'oee_chart': oee_chart,
            'anomaly_chart': anomaly_chart,
        })


# ============================================================================
# Generic helpers
# ============================================================================

class _TenantListBase(TenantRequiredMixin, View):
    model = None
    template_name = ''
    context_qs_name = 'object_list'
    select_related: tuple = ()
    search_fields: tuple = ()

    def filter_qs(self, qs, request):
        return qs

    def extra_context(self, request):
        return {}

    def get(self, request):
        qs = self.model.objects.filter(tenant=request.tenant)
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        q = (request.GET.get('q') or '').strip()
        if q and self.search_fields:
            ors = Q()
            for f in self.search_fields:
                ors |= Q(**{f'{f}__icontains': q})
            qs = qs.filter(ors)
        qs = self.filter_qs(qs, request)
        page = _paginate(qs, request)
        ctx = {self.context_qs_name: page, 'page_obj': page, 'page': page, 'q': q}
        ctx.update(self.extra_context(request))
        return render(request, self.template_name, ctx)


class _TenantDeleteBase(TenantAdminRequiredMixin, View):
    model = None
    redirect_url_name = ''
    success_message = 'Deleted successfully.'

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk, tenant=request.tenant)
        obj.delete()
        messages.success(request, self.success_message)
        return redirect(self.redirect_url_name)

    def get(self, request, pk):
        return self.post(request, pk)


# ============================================================================
# 15.1  Connectivity Hub - Protocols (shared catalog, no tenant scoping)
# ============================================================================

class DeviceProtocolListView(TenantRequiredMixin, View):
    def get(self, request):
        qs = models.DeviceProtocol.objects.all().order_by('code')
        page = _paginate(qs, request)
        return render(request, 'iot/protocols/list.html', {
            'object_list': page, 'page_obj': page,
        })


class DeviceProtocolCreateView(TenantAdminRequiredMixin, View):
    template_name = 'iot/protocols/form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': forms.DeviceProtocolForm()})

    def post(self, request):
        form = forms.DeviceProtocolForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Protocol created.')
            return redirect('iot:protocol_list')
        return render(request, self.template_name, {'form': form})


class DeviceProtocolEditView(TenantAdminRequiredMixin, View):
    template_name = 'iot/protocols/form.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.DeviceProtocol, pk=pk)
        return render(request, self.template_name, {
            'form': forms.DeviceProtocolForm(instance=obj), 'object': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.DeviceProtocol, pk=pk)
        form = forms.DeviceProtocolForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Protocol updated.')
            return redirect('iot:protocol_list')
        return render(request, self.template_name, {'form': form, 'object': obj})


class DeviceProtocolDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DeviceProtocol, pk=pk)
        obj.delete()
        messages.success(request, 'Protocol deleted.')
        return redirect('iot:protocol_list')

    def get(self, request, pk):
        return self.post(request, pk)


# ============================================================================
# 15.1  Connectivity Hub - Brokers
# ============================================================================

class DeviceBrokerListView(_TenantListBase):
    model = models.DeviceBroker
    template_name = 'iot/brokers/list.html'
    select_related = ('protocol',)
    search_fields = ('broker_number', 'name', 'host')

    def filter_qs(self, qs, request):
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def extra_context(self, request):
        return {'status_choices': models.DeviceBroker.STATUS_CHOICES}


class _BrokerFormView(TenantAdminRequiredMixin, View):
    template_name = 'iot/brokers/form.html'

    def get(self, request, pk=None):
        obj = get_object_or_404(models.DeviceBroker, pk=pk, tenant=request.tenant) if pk else None
        return render(request, self.template_name, {
            'form': forms.DeviceBrokerForm(instance=obj, tenant=request.tenant),
            'object': obj,
        })

    def post(self, request, pk=None):
        obj = get_object_or_404(models.DeviceBroker, pk=pk, tenant=request.tenant) if pk else None
        form = forms.DeviceBrokerForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            broker = form.save(commit=False)
            broker.tenant = request.tenant
            broker.save()
            messages.success(request, 'Broker saved.')
            return redirect('iot:broker_list')
        return render(request, self.template_name, {'form': form, 'object': obj})


class DeviceBrokerCreateView(_BrokerFormView):
    pass


class DeviceBrokerEditView(_BrokerFormView):
    pass


class DeviceBrokerDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(models.DeviceBroker, pk=pk, tenant=request.tenant)
        return render(request, 'iot/brokers/detail.html', {
            'object': obj,
            'devices': list(obj.devices.all()[:25]),
        })


class DeviceBrokerDeleteView(_TenantDeleteBase):
    model = models.DeviceBroker
    redirect_url_name = 'iot:broker_list'
    success_message = 'Broker deleted.'


class DeviceBrokerHeartbeatView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DeviceBroker, pk=pk, tenant=request.tenant)
        form = forms.BrokerHeartbeatForm(request.POST)
        if form.is_valid():
            ok = form.cleaned_data.get('success', True)
            obj.last_heartbeat_at = timezone.now()
            obj.status = 'active' if ok else 'error'
            obj.error_message = '' if ok else (form.cleaned_data.get('error_message') or 'Heartbeat failed')
            obj.save(update_fields=['last_heartbeat_at', 'status', 'error_message'])
            messages.success(request, 'Heartbeat recorded.')
        return redirect('iot:broker_detail', pk=pk)


# ============================================================================
# 15.1  Connectivity Hub - Devices
# ============================================================================

class DeviceListView(_TenantListBase):
    model = models.Device
    template_name = 'iot/devices/list.html'
    select_related = ('broker', 'protocol', 'asset')
    search_fields = ('device_number', 'name', 'serial_number')

    def filter_qs(self, qs, request):
        status = request.GET.get('status')
        device_type = request.GET.get('device_type')
        if status:
            qs = qs.filter(status=status)
        if device_type:
            qs = qs.filter(device_type=device_type)
        return qs

    def extra_context(self, request):
        return {
            'status_choices': models.Device.STATUS_CHOICES,
            'type_choices': models.Device.DEVICE_TYPE_CHOICES,
        }


class _DeviceFormView(TenantAdminRequiredMixin, View):
    template_name = 'iot/devices/form.html'

    def get(self, request, pk=None):
        obj = get_object_or_404(models.Device, pk=pk, tenant=request.tenant) if pk else None
        form = forms.DeviceForm(instance=obj, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'object': obj})

    def post(self, request, pk=None):
        obj = get_object_or_404(models.Device, pk=pk, tenant=request.tenant) if pk else None
        form = forms.DeviceForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            d = form.save(commit=False)
            d.tenant = request.tenant
            d.save()
            messages.success(request, 'Device saved.')
            return redirect('iot:device_list')
        return render(request, self.template_name, {'form': form, 'object': obj})


class DeviceCreateView(_DeviceFormView):
    pass


class DeviceEditView(_DeviceFormView):
    pass


class DeviceDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            models.Device.objects.select_related('broker', 'protocol', 'asset'),
            pk=pk, tenant=request.tenant,
        )
        tags = list(obj.tags.all())
        recent_readings = list(
            models.IoTReading.objects.filter(
                tenant=request.tenant, device_tag__device=obj,
            ).select_related('device_tag').order_by('-timestamp')[:25]
        )
        return render(request, 'iot/devices/detail.html', {
            'object': obj, 'tags': tags, 'recent_readings': recent_readings,
        })


class DeviceDeleteView(_TenantDeleteBase):
    model = models.Device
    redirect_url_name = 'iot:device_list'
    success_message = 'Device deleted.'


class DeviceRetireView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Device, pk=pk, tenant=request.tenant)
        if not obj.is_retirable():
            messages.error(request, 'Device cannot be retired in its current state.')
            return redirect('iot:device_detail', pk=pk)
        obj.status = 'decommissioned'
        obj.save(update_fields=['status'])
        messages.success(request, 'Device retired.')
        return redirect('iot:device_detail', pk=pk)


class DeviceReactivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.Device, pk=pk, tenant=request.tenant)
        if not obj.is_reactivatable():
            messages.error(request, 'Device cannot be reactivated.')
            return redirect('iot:device_detail', pk=pk)
        obj.status = 'active'
        obj.save(update_fields=['status'])
        messages.success(request, 'Device reactivated.')
        return redirect('iot:device_detail', pk=pk)


# ============================================================================
# 15.1  Connectivity Hub - Tags
# ============================================================================

class DeviceTagListView(_TenantListBase):
    model = models.DeviceTag
    template_name = 'iot/tags/list.html'
    select_related = ('device',)
    search_fields = ('name', 'address')

    def filter_qs(self, qs, request):
        device = request.GET.get('device')
        data_type = request.GET.get('data_type')
        active = request.GET.get('active')
        if device:
            qs = qs.filter(device_id=device)
        if data_type:
            qs = qs.filter(data_type=data_type)
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs

    def extra_context(self, request):
        return {
            'devices': models.Device.objects.filter(tenant=request.tenant),
            'data_type_choices': models.DeviceTag.DATA_TYPE_CHOICES,
        }


class _TagFormView(TenantAdminRequiredMixin, View):
    template_name = 'iot/tags/form.html'

    def get(self, request, pk=None):
        obj = get_object_or_404(models.DeviceTag, pk=pk, tenant=request.tenant) if pk else None
        form = forms.DeviceTagForm(instance=obj, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'object': obj})

    def post(self, request, pk=None):
        obj = get_object_or_404(models.DeviceTag, pk=pk, tenant=request.tenant) if pk else None
        form = forms.DeviceTagForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            tag = form.save(commit=False)
            tag.tenant = request.tenant
            tag.save()
            messages.success(request, 'Tag saved.')
            return redirect('iot:tag_list')
        return render(request, self.template_name, {'form': form, 'object': obj})


class DeviceTagCreateView(_TagFormView):
    pass


class DeviceTagEditView(_TagFormView):
    pass


class DeviceTagDeleteView(_TenantDeleteBase):
    model = models.DeviceTag
    redirect_url_name = 'iot:tag_list'
    success_message = 'Tag deleted.'


# ============================================================================
# 15.2  IoTReading
# ============================================================================

class IoTReadingListView(_TenantListBase):
    model = models.IoTReading
    template_name = 'iot/readings/list.html'
    select_related = ('device_tag', 'device_tag__device', 'batch')
    search_fields = ('entry_number', 'value_text')

    def filter_qs(self, qs, request):
        tag = request.GET.get('tag')
        device = request.GET.get('device')
        quality = request.GET.get('quality')
        if tag:
            qs = qs.filter(device_tag_id=tag)
        if device:
            qs = qs.filter(device_tag__device_id=device)
        if quality:
            qs = qs.filter(quality=quality)
        return qs.order_by('-timestamp', '-id')

    def extra_context(self, request):
        return {
            'devices': models.Device.objects.filter(tenant=request.tenant),
            'quality_choices': models.IoTReading.QUALITY_CHOICES,
        }


class IoTReadingCreateView(TenantAdminRequiredMixin, View):
    template_name = 'iot/readings/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.IoTReadingForm(tenant=request.tenant),
        })

    def post(self, request):
        form = forms.IoTReadingForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            r = form.save(commit=False)
            r.tenant = request.tenant
            r.source = 'manual'
            r.save()
            messages.success(request, f'Reading {r.entry_number} created.')
            return redirect('iot:reading_list')
        return render(request, self.template_name, {'form': form})


class IoTReadingDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            models.IoTReading.objects.select_related('device_tag', 'device_tag__device', 'batch'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'iot/readings/detail.html', {'object': obj})


class IoTReadingDeleteView(_TenantDeleteBase):
    model = models.IoTReading
    redirect_url_name = 'iot:reading_list'
    success_message = 'Reading deleted.'


class IoTReadingIngestView(TenantAdminRequiredMixin, View):
    template_name = 'iot/readings/ingest.html'

    def get(self, request):
        return render(request, self.template_name, {'form': forms.IoTReadingIngestForm()})

    def post(self, request):
        form = forms.IoTReadingIngestForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})
        try:
            batch, created, errors = ingest_svc.bulk_ingest(
                tenant=request.tenant,
                payload=form.cleaned_data['payload'],
                source_format=form.cleaned_data['source_format'],
                user=request.user,
                notes=form.cleaned_data.get('notes', ''),
            )
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Ingest failed: {exc}')
            return render(request, self.template_name, {'form': form})
        if batch is None:
            messages.error(request, '; '.join(errors) or 'Ingest failed.')
            return render(request, self.template_name, {'form': form})
        if errors:
            messages.warning(request, f'Ingest partially completed: {created} rows in, {len(errors)} errors.')
        else:
            messages.success(request, f'Ingest complete: {created} rows in batch {batch.batch_number}.')
        return redirect('iot:batch_detail', pk=batch.pk)


# ============================================================================
# 15.2  Batches
# ============================================================================

class IoTReadingBatchListView(_TenantListBase):
    model = models.IoTReadingBatch
    template_name = 'iot/batches/list.html'
    search_fields = ('batch_number',)

    def filter_qs(self, qs, request):
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-ingested_at')

    def extra_context(self, request):
        return {'status_choices': models.IoTReadingBatch.STATUS_CHOICES}


class IoTReadingBatchDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(models.IoTReadingBatch, pk=pk, tenant=request.tenant)
        readings = list(obj.readings.select_related('device_tag').all()[:50])
        return render(request, 'iot/batches/detail.html', {'object': obj, 'readings': readings})


# ============================================================================
# 15.2  Edge processors
# ============================================================================

class EdgeProcessorListView(_TenantListBase):
    model = models.EdgeProcessor
    template_name = 'iot/edge_processors/list.html'
    select_related = ('input_tag', 'output_tag')
    search_fields = ('name',)


class _EdgeFormView(TenantAdminRequiredMixin, View):
    template_name = 'iot/edge_processors/form.html'

    def get(self, request, pk=None):
        obj = get_object_or_404(models.EdgeProcessor, pk=pk, tenant=request.tenant) if pk else None
        form = forms.EdgeProcessorForm(instance=obj, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'object': obj})

    def post(self, request, pk=None):
        obj = get_object_or_404(models.EdgeProcessor, pk=pk, tenant=request.tenant) if pk else None
        form = forms.EdgeProcessorForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            e = form.save(commit=False)
            e.tenant = request.tenant
            e.save()
            messages.success(request, 'Edge processor saved.')
            return redirect('iot:edge_list')
        return render(request, self.template_name, {'form': form, 'object': obj})


class EdgeProcessorCreateView(_EdgeFormView):
    pass


class EdgeProcessorEditView(_EdgeFormView):
    pass


class EdgeProcessorDeleteView(_TenantDeleteBase):
    model = models.EdgeProcessor
    redirect_url_name = 'iot:edge_list'
    success_message = 'Edge processor deleted.'


# ============================================================================
# 15.2  Stream metrics (read-only)
# ============================================================================

class StreamMetricListView(_TenantListBase):
    model = models.StreamMetric
    template_name = 'iot/stream_metrics/list.html'
    select_related = ('device_tag', 'device_tag__device')

    def filter_qs(self, qs, request):
        device = request.GET.get('device')
        if device:
            qs = qs.filter(device_tag__device_id=device)
        return qs.order_by('-latest_timestamp')

    def extra_context(self, request):
        return {'devices': models.Device.objects.filter(tenant=request.tenant)}


# ============================================================================
# 15.3  Digital Twin
# ============================================================================

class DigitalTwinListView(_TenantListBase):
    model = models.DigitalTwin
    template_name = 'iot/twins/list.html'
    select_related = ('asset',)
    search_fields = ('twin_number', 'name')

    def filter_qs(self, qs, request):
        status = request.GET.get('status')
        twin_type = request.GET.get('twin_type')
        if status:
            qs = qs.filter(status=status)
        if twin_type:
            qs = qs.filter(twin_type=twin_type)
        return qs

    def extra_context(self, request):
        return {
            'status_choices': models.DigitalTwin.STATUS_CHOICES,
            'type_choices': models.DigitalTwin.TWIN_TYPE_CHOICES,
        }


class _TwinFormView(TenantAdminRequiredMixin, View):
    template_name = 'iot/twins/form.html'

    def get(self, request, pk=None):
        obj = get_object_or_404(models.DigitalTwin, pk=pk, tenant=request.tenant) if pk else None
        form = forms.DigitalTwinForm(instance=obj, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'object': obj})

    def post(self, request, pk=None):
        obj = get_object_or_404(models.DigitalTwin, pk=pk, tenant=request.tenant) if pk else None
        if obj and not obj.is_editable():
            messages.error(request, 'Twin cannot be edited in its current state.')
            return redirect('iot:twin_detail', pk=obj.pk)
        form = forms.DigitalTwinForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            t = form.save(commit=False)
            t.tenant = request.tenant
            t.save()
            messages.success(request, 'Twin saved.')
            return redirect('iot:twin_detail', pk=t.pk)
        return render(request, self.template_name, {'form': form, 'object': obj})


class DigitalTwinCreateView(_TwinFormView):
    pass


class DigitalTwinEditView(_TwinFormView):
    pass


class DigitalTwinDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            models.DigitalTwin.objects.select_related('asset'),
            pk=pk, tenant=request.tenant,
        )
        attrs = list(obj.attributes.select_related('source_tag').all())
        scenarios = list(obj.scenarios.all()[:10])
        snapshots = list(obj.snapshots.all()[:10])
        return render(request, 'iot/twins/detail.html', {
            'object': obj, 'attrs': attrs, 'scenarios': scenarios, 'snapshots': snapshots,
        })


class DigitalTwinDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DigitalTwin, pk=pk, tenant=request.tenant)
        if not obj.is_deletable():
            messages.error(request, 'Twin can only be deleted in draft state.')
            return redirect('iot:twin_detail', pk=pk)
        obj.delete()
        messages.success(request, 'Twin deleted.')
        return redirect('iot:twin_list')

    def get(self, request, pk):
        return self.post(request, pk)


class DigitalTwinActivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.DigitalTwin, pk, request.tenant, ('draft',), 'active',
        )
        if ok:
            messages.success(request, 'Twin activated.')
        else:
            messages.error(request, 'Twin cannot be activated.')
        return redirect('iot:twin_detail', pk=pk)


class DigitalTwinArchiveView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        ok = _atomic_status_transition(
            models.DigitalTwin, pk, request.tenant, ('draft', 'active'), 'archived',
        )
        if ok:
            messages.success(request, 'Twin archived.')
        else:
            messages.error(request, 'Twin cannot be archived.')
        return redirect('iot:twin_detail', pk=pk)


class DigitalTwinSnapshotView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DigitalTwin, pk=pk, tenant=request.tenant)
        form = forms.TwinSnapshotForm(request.POST)
        notes = form.cleaned_data.get('notes', '') if form.is_valid() else ''
        state = twin_svc.compute_twin_state(obj)
        models.TwinStateSnapshot.objects.create(
            tenant=request.tenant, twin=obj, snapshot_at=timezone.now(),
            state_payload={k: (str(v) if v is not None else None) for k, v in state.items()},
            triggered_by='manual', captured_by=request.user, notes=notes,
        )
        messages.success(request, 'Snapshot captured.')
        return redirect('iot:twin_detail', pk=pk)


class DigitalTwinRecomputeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.DigitalTwin, pk=pk, tenant=request.tenant)
        state = twin_svc.compute_twin_state(obj)
        for attr in obj.attributes.all():
            v = state.get(attr.name)
            if isinstance(v, Decimal):
                attr.current_value_numeric = v
                attr.current_value_text = ''
            elif v is None:
                attr.current_value_numeric = None
                attr.current_value_text = ''
            else:
                attr.current_value_text = str(v)
            attr.current_value_at = timezone.now()
            attr.save(update_fields=[
                'current_value_numeric', 'current_value_text', 'current_value_at',
            ])
        messages.success(request, 'Twin attributes recomputed.')
        return redirect('iot:twin_detail', pk=pk)


# Twin attributes inline
class TwinAttributeCreateView(TenantAdminRequiredMixin, View):
    template_name = 'iot/twin_attributes/form.html'

    def get(self, request, twin_pk):
        twin = get_object_or_404(models.DigitalTwin, pk=twin_pk, tenant=request.tenant)
        form = forms.TwinStateAttributeForm(initial={'twin': twin}, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'twin': twin})

    def post(self, request, twin_pk):
        twin = get_object_or_404(models.DigitalTwin, pk=twin_pk, tenant=request.tenant)
        form = forms.TwinStateAttributeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            attr = form.save(commit=False)
            attr.tenant = request.tenant
            attr.twin = twin
            attr.save()
            messages.success(request, 'Attribute added.')
            return redirect('iot:twin_detail', pk=twin.pk)
        return render(request, self.template_name, {'form': form, 'twin': twin})


class TwinAttributeEditView(TenantAdminRequiredMixin, View):
    template_name = 'iot/twin_attributes/form.html'

    def get(self, request, pk):
        attr = get_object_or_404(models.TwinStateAttribute, pk=pk, tenant=request.tenant)
        form = forms.TwinStateAttributeForm(instance=attr, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'object': attr, 'twin': attr.twin})

    def post(self, request, pk):
        attr = get_object_or_404(models.TwinStateAttribute, pk=pk, tenant=request.tenant)
        form = forms.TwinStateAttributeForm(request.POST, instance=attr, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, 'Attribute updated.')
            return redirect('iot:twin_detail', pk=attr.twin.pk)
        return render(request, self.template_name, {'form': form, 'object': attr, 'twin': attr.twin})


class TwinAttributeDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        attr = get_object_or_404(models.TwinStateAttribute, pk=pk, tenant=request.tenant)
        twin_pk = attr.twin_id
        attr.delete()
        messages.success(request, 'Attribute deleted.')
        return redirect('iot:twin_detail', pk=twin_pk)

    def get(self, request, pk):
        return self.post(request, pk)


# Twin scenarios
class TwinScenarioCreateView(TenantAdminRequiredMixin, View):
    template_name = 'iot/twin_scenarios/form.html'

    def get(self, request, twin_pk):
        twin = get_object_or_404(models.DigitalTwin, pk=twin_pk, tenant=request.tenant)
        form = forms.TwinSimulationScenarioForm(initial={'twin': twin}, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'twin': twin})

    def post(self, request, twin_pk):
        twin = get_object_or_404(models.DigitalTwin, pk=twin_pk, tenant=request.tenant)
        form = forms.TwinSimulationScenarioForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            s = form.save(commit=False)
            s.tenant = request.tenant
            s.twin = twin
            s.save()
            messages.success(request, f'Scenario {s.scenario_number} created.')
            return redirect('iot:twin_scenario_detail', pk=s.pk)
        return render(request, self.template_name, {'form': form, 'twin': twin})


class TwinScenarioDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            models.TwinSimulationScenario.objects.select_related('twin'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'iot/twin_scenarios/detail.html', {'object': obj})


class TwinScenarioRunView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.TwinSimulationScenario, pk=pk, tenant=request.tenant)
        if not obj.is_runnable():
            messages.error(request, 'Scenario is already running.')
            return redirect('iot:twin_scenario_detail', pk=pk)
        obj.status = 'running'
        obj.save(update_fields=['status'])
        try:
            payload = twin_sim_svc.run_simulation(obj)
            obj.result_payload = payload
            obj.status = 'completed' if not payload.get('errors') else 'failed'
            obj.run_at = timezone.now()
            obj.error_message = '\n'.join(payload.get('errors', []))[:500]
        except Exception as exc:  # noqa: BLE001
            obj.status = 'failed'
            obj.error_message = str(exc)[:500]
        obj.save()
        messages.success(request, f'Scenario {obj.scenario_number} {obj.status}.')
        return redirect('iot:twin_scenario_detail', pk=pk)


class TwinScenarioDeleteView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.TwinSimulationScenario, pk=pk, tenant=request.tenant)
        if not obj.is_deletable():
            messages.error(request, 'Scenario currently running.')
            return redirect('iot:twin_scenario_detail', pk=pk)
        twin_pk = obj.twin_id
        obj.delete()
        messages.success(request, 'Scenario deleted.')
        return redirect('iot:twin_detail', pk=twin_pk)

    def get(self, request, pk):
        return self.post(request, pk)


# ============================================================================
# 15.4  OEE
# ============================================================================

class OEEDashboardView(TenantRequiredMixin, View):
    def get(self, request):
        tenant = request.tenant
        today = timezone.now().date()
        rows = list(
            models.OEEPeriod.objects.filter(
                tenant=tenant, period_date__gte=today - timedelta(days=14),
            ).select_related('asset', 'shift').order_by('-period_date')[:50]
        )
        loss_pareto = list(
            models.MachineStateLog.objects.filter(
                tenant=tenant, started_at__gte=timezone.now() - timedelta(days=30),
                loss_reason__isnull=False,
            ).values('loss_reason__code', 'loss_reason__name')
            .annotate(total=Sum('duration_seconds'))
            .order_by('-total')[:10]
        )
        chart = [
            {
                'asset': r.asset.asset_number if hasattr(r.asset, 'asset_number') else str(r.asset),
                'date': r.period_date.strftime('%m-%d'),
                'availability': float(r.availability_pct),
                'performance': float(r.performance_pct),
                'quality': float(r.quality_pct),
                'oee': float(r.oee_pct),
            }
            for r in rows
        ]
        return render(request, 'iot/oee/dashboard.html', {
            'rows': rows, 'chart': chart, 'loss_pareto': loss_pareto,
        })


class OEEPeriodListView(_TenantListBase):
    model = models.OEEPeriod
    template_name = 'iot/oee/periods/list.html'
    select_related = ('asset', 'shift')
    search_fields = ('period_number',)

    def filter_qs(self, qs, request):
        asset = request.GET.get('asset')
        if asset:
            qs = qs.filter(asset_id=asset)
        return qs.order_by('-period_date')

    def extra_context(self, request):
        from apps.eam.models import Asset
        return {'assets': Asset.objects.filter(tenant=request.tenant)}


class _OEEPeriodFormView(TenantAdminRequiredMixin, View):
    template_name = 'iot/oee/periods/form.html'

    def get(self, request, pk=None):
        obj = get_object_or_404(models.OEEPeriod, pk=pk, tenant=request.tenant) if pk else None
        form = forms.OEEPeriodForm(instance=obj, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'object': obj})

    def post(self, request, pk=None):
        obj = get_object_or_404(models.OEEPeriod, pk=pk, tenant=request.tenant) if pk else None
        form = forms.OEEPeriodForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            p = form.save(commit=False)
            p.tenant = request.tenant
            p.save()
            messages.success(request, f'OEE period {p.period_number} saved.')
            return redirect('iot:oee_period_detail', pk=p.pk)
        return render(request, self.template_name, {'form': form, 'object': obj})


class OEEPeriodCreateView(_OEEPeriodFormView):
    pass


class OEEPeriodEditView(_OEEPeriodFormView):
    pass


class OEEPeriodDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            models.OEEPeriod.objects.select_related('asset', 'shift'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'iot/oee/periods/detail.html', {'object': obj})


class OEEPeriodDeleteView(_TenantDeleteBase):
    model = models.OEEPeriod
    redirect_url_name = 'iot:oee_period_list'
    success_message = 'OEE period deleted.'


class OEEPeriodRecomputeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.OEEPeriod, pk=pk, tenant=request.tenant)
        try:
            oee_svc.recompute_period(obj)
            messages.success(request, 'OEE period recomputed.')
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Recompute failed: {exc}')
        return redirect('iot:oee_period_detail', pk=pk)


# Loss Reason CRUD
class LossReasonListView(_TenantListBase):
    model = models.LossReason
    template_name = 'iot/oee/loss_reasons/list.html'
    search_fields = ('code', 'name')

    def filter_qs(self, qs, request):
        cat = request.GET.get('category')
        if cat:
            qs = qs.filter(category=cat)
        return qs

    def extra_context(self, request):
        return {'category_choices': models.LossReason.CATEGORY_CHOICES}


class _LossReasonFormView(TenantAdminRequiredMixin, View):
    template_name = 'iot/oee/loss_reasons/form.html'

    def get(self, request, pk=None):
        obj = get_object_or_404(models.LossReason, pk=pk, tenant=request.tenant) if pk else None
        form = forms.LossReasonForm(instance=obj, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'object': obj})

    def post(self, request, pk=None):
        obj = get_object_or_404(models.LossReason, pk=pk, tenant=request.tenant) if pk else None
        form = forms.LossReasonForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            r = form.save(commit=False)
            r.tenant = request.tenant
            r.save()
            messages.success(request, 'Loss reason saved.')
            return redirect('iot:loss_reason_list')
        return render(request, self.template_name, {'form': form, 'object': obj})


class LossReasonCreateView(_LossReasonFormView):
    pass


class LossReasonEditView(_LossReasonFormView):
    pass


class LossReasonDeleteView(_TenantDeleteBase):
    model = models.LossReason
    redirect_url_name = 'iot:loss_reason_list'
    success_message = 'Loss reason deleted.'


# State Log CRUD
class MachineStateLogListView(_TenantListBase):
    model = models.MachineStateLog
    template_name = 'iot/oee/state_logs/list.html'
    select_related = ('asset', 'loss_reason')

    def filter_qs(self, qs, request):
        asset = request.GET.get('asset')
        state = request.GET.get('state')
        if asset:
            qs = qs.filter(asset_id=asset)
        if state:
            qs = qs.filter(state=state)
        return qs.order_by('-started_at')

    def extra_context(self, request):
        from apps.eam.models import Asset
        return {
            'assets': Asset.objects.filter(tenant=request.tenant),
            'state_choices': models.MachineStateLog.STATE_CHOICES,
        }


class MachineStateLogCreateView(TenantAdminRequiredMixin, View):
    template_name = 'iot/oee/state_logs/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': forms.MachineStateLogForm(tenant=request.tenant),
        })

    def post(self, request):
        form = forms.MachineStateLogForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            log = form.save(commit=False)
            log.tenant = request.tenant
            log.source = 'manual'
            log.save()
            messages.success(request, 'State log created.')
            return redirect('iot:state_log_list')
        return render(request, self.template_name, {'form': form})


class MachineStateLogDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            models.MachineStateLog.objects.select_related('asset', 'loss_reason'),
            pk=pk, tenant=request.tenant,
        )
        return render(request, 'iot/oee/state_logs/detail.html', {'object': obj})


class MachineStateLogDeleteView(_TenantDeleteBase):
    model = models.MachineStateLog
    redirect_url_name = 'iot:state_log_list'
    success_message = 'State log deleted.'


# ============================================================================
# 15.5  Alerts
# ============================================================================

class AlertRuleListView(_TenantListBase):
    model = models.AlertRule
    template_name = 'iot/alerts/rules/list.html'
    select_related = ('device_tag', 'scope_device', 'scope_asset')
    search_fields = ('rule_number', 'name')

    def filter_qs(self, qs, request):
        cond = request.GET.get('condition_type')
        sev = request.GET.get('severity')
        active = request.GET.get('active')
        if cond:
            qs = qs.filter(condition_type=cond)
        if sev:
            qs = qs.filter(severity=sev)
        if active == 'active':
            qs = qs.filter(is_active=True)
        elif active == 'inactive':
            qs = qs.filter(is_active=False)
        return qs

    def extra_context(self, request):
        return {
            'condition_choices': models.AlertRule.CONDITION_CHOICES,
            'severity_choices': models.AlertRule.SEVERITY_CHOICES,
        }


class _AlertRuleFormView(TenantAdminRequiredMixin, View):
    template_name = 'iot/alerts/rules/form.html'

    def get(self, request, pk=None):
        obj = get_object_or_404(models.AlertRule, pk=pk, tenant=request.tenant) if pk else None
        form = forms.AlertRuleForm(instance=obj, tenant=request.tenant)
        return render(request, self.template_name, {'form': form, 'object': obj})

    def post(self, request, pk=None):
        obj = get_object_or_404(models.AlertRule, pk=pk, tenant=request.tenant) if pk else None
        form = forms.AlertRuleForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.tenant = request.tenant
            rule.save()
            messages.success(request, f'Rule {rule.rule_number} saved.')
            return redirect('iot:rule_detail', pk=rule.pk)
        return render(request, self.template_name, {'form': form, 'object': obj})


class AlertRuleCreateView(_AlertRuleFormView):
    pass


class AlertRuleEditView(_AlertRuleFormView):
    pass


class AlertRuleDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            models.AlertRule.objects.select_related('device_tag', 'scope_device', 'scope_asset'),
            pk=pk, tenant=request.tenant,
        )
        recent_detections = list(obj.detections.order_by('-detected_at')[:10])
        return render(request, 'iot/alerts/rules/detail.html', {
            'object': obj, 'recent_detections': recent_detections,
        })


class AlertRuleDeleteView(_TenantDeleteBase):
    model = models.AlertRule
    redirect_url_name = 'iot:rule_list'
    success_message = 'Alert rule deleted.'


class AlertRuleActivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        with transaction.atomic():
            n = models.AlertRule.objects.filter(
                pk=pk, tenant=request.tenant,
            ).update(is_active=True)
        if n:
            messages.success(request, 'Rule activated.')
        else:
            messages.error(request, 'Rule not found.')
        return redirect('iot:rule_detail', pk=pk)


class AlertRuleDeactivateView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        with transaction.atomic():
            n = models.AlertRule.objects.filter(
                pk=pk, tenant=request.tenant,
            ).update(is_active=False)
        if n:
            messages.success(request, 'Rule deactivated.')
        else:
            messages.error(request, 'Rule not found.')
        return redirect('iot:rule_detail', pk=pk)


# Anomaly detections
class AnomalyDetectionListView(_TenantListBase):
    model = models.AnomalyDetection
    template_name = 'iot/alerts/detections/list.html'
    select_related = ('rule', 'source_reading', 'source_reading__device_tag')

    def filter_qs(self, qs, request):
        sev = request.GET.get('severity')
        st = request.GET.get('status')
        if sev:
            qs = qs.filter(severity=sev)
        if st:
            qs = qs.filter(status=st)
        return qs.order_by('-detected_at')

    def extra_context(self, request):
        return {
            'severity_choices': models.AlertRule.SEVERITY_CHOICES,
            'status_choices': models.AnomalyDetection.STATUS_CHOICES,
        }


class AnomalyDetectionDetailView(TenantRequiredMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            models.AnomalyDetection.objects.select_related(
                'rule', 'source_reading', 'source_reading__device_tag',
            ),
            pk=pk, tenant=request.tenant,
        )
        notifications = list(obj.notifications.all())
        return render(request, 'iot/alerts/detections/detail.html', {
            'object': obj, 'notifications': notifications,
        })


class AnomalyDetectionAcknowledgeView(TenantAdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(models.AnomalyDetection, pk=pk, tenant=request.tenant)
        if not obj.is_acknowledgeable():
            messages.error(request, 'Detection cannot be acknowledged.')
            return redirect('iot:detection_detail', pk=pk)
        obj.status = 'acknowledged'
        obj.acknowledged_by = request.user
        obj.acknowledged_at = timezone.now()
        obj.save(update_fields=['status', 'acknowledged_by', 'acknowledged_at'])
        messages.success(request, 'Detection acknowledged.')
        return redirect('iot:detection_detail', pk=pk)


class AnomalyDetectionResolveView(TenantAdminRequiredMixin, View):
    template_name = 'iot/alerts/detections/resolve.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.AnomalyDetection, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.AnomalyResolveForm(), 'object': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.AnomalyDetection, pk=pk, tenant=request.tenant)
        if not obj.is_resolvable():
            messages.error(request, 'Detection cannot be resolved.')
            return redirect('iot:detection_detail', pk=pk)
        form = forms.AnomalyResolveForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form, 'object': obj})
        obj.status = 'resolved'
        obj.resolved_by = request.user
        obj.resolved_at = timezone.now()
        obj.resolution_notes = form.cleaned_data['resolution_notes']
        obj.save(update_fields=['status', 'resolved_by', 'resolved_at', 'resolution_notes'])
        messages.success(request, 'Detection resolved.')
        return redirect('iot:detection_detail', pk=pk)


class AnomalyDetectionFalsePositiveView(TenantAdminRequiredMixin, View):
    template_name = 'iot/alerts/detections/false_positive.html'

    def get(self, request, pk):
        obj = get_object_or_404(models.AnomalyDetection, pk=pk, tenant=request.tenant)
        return render(request, self.template_name, {
            'form': forms.AnomalyFalsePositiveForm(), 'object': obj,
        })

    def post(self, request, pk):
        obj = get_object_or_404(models.AnomalyDetection, pk=pk, tenant=request.tenant)
        if not obj.is_markable_false_positive():
            messages.error(request, 'Detection cannot be marked false positive.')
            return redirect('iot:detection_detail', pk=pk)
        form = forms.AnomalyFalsePositiveForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form, 'object': obj})
        obj.status = 'false_positive'
        obj.resolved_by = request.user
        obj.resolved_at = timezone.now()
        obj.resolution_notes = form.cleaned_data['resolution_notes']
        obj.save(update_fields=['status', 'resolved_by', 'resolved_at', 'resolution_notes'])
        messages.success(request, 'Detection marked as false positive.')
        return redirect('iot:detection_detail', pk=pk)


# Notifications
class AlertNotificationListView(_TenantListBase):
    model = models.AlertNotification
    template_name = 'iot/alerts/notifications/list.html'
    select_related = ('detection', 'detection__rule')

    def filter_qs(self, qs, request):
        ch = request.GET.get('channel')
        st = request.GET.get('status')
        if ch:
            qs = qs.filter(channel=ch)
        if st:
            qs = qs.filter(status=st)
        return qs

    def extra_context(self, request):
        return {
            'channel_choices': models.AlertNotification.CHANNEL_CHOICES,
            'status_choices': models.AlertNotification.STATUS_CHOICES,
        }
