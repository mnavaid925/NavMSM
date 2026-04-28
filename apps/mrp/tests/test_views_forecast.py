"""Forecast Model + Forecast Run view tests.

Converts manual plan §4.3.1 (CREATE FM), §4.6 EDIT FM, §4.7 DELETE FM,
§4.11.1 (Run forecast), and TC-NEG-11 (engine error path).
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.mrp.models import ForecastModel, ForecastResult, ForecastRun


@pytest.mark.django_db
class TestForecastModelCreate:
    def test_happy_path_create(self, admin_client, acme, acme_admin):
        r = admin_client.post(reverse('mrp:forecast_model_create'), {
            'name': 'Manual SMA-3', 'description': 'desc',
            'method': 'moving_avg', 'params': '{"window": 3}',
            'period_type': 'week', 'horizon_periods': 12,
            'is_active': 'on',
        })
        assert r.status_code == 302
        fm = ForecastModel.objects.get(tenant=acme, name='Manual SMA-3')
        assert fm.method == 'moving_avg'
        assert fm.created_by_id == acme_admin.pk

    def test_duplicate_name_blocked(self, admin_client, acme, forecast_model):
        r = admin_client.post(reverse('mrp:forecast_model_create'), {
            'name': forecast_model.name, 'description': '',
            'method': 'moving_avg', 'params': '{}',
            'period_type': 'week', 'horizon_periods': 12,
        })
        # Form re-renders (200) with errors; only one row exists.
        assert r.status_code == 200
        assert ForecastModel.objects.filter(tenant=acme, name=forecast_model.name).count() == 1

    def test_horizon_over_max_rejected(self, admin_client, acme):
        r = admin_client.post(reverse('mrp:forecast_model_create'), {
            'name': 'Over', 'description': '',
            'method': 'moving_avg', 'params': '{}',
            'period_type': 'week', 'horizon_periods': 200,
        })
        assert r.status_code == 200
        assert not ForecastModel.objects.filter(tenant=acme, name='Over').exists()

    def test_xss_in_description_escaped_on_detail(self, admin_client, acme):
        admin_client.post(reverse('mrp:forecast_model_create'), {
            'name': 'XSS', 'description': '<script>alert(1)</script>',
            'method': 'moving_avg', 'params': '{}',
            'period_type': 'week', 'horizon_periods': 4,
        })
        fm = ForecastModel.objects.get(tenant=acme, name='XSS')
        r = admin_client.get(reverse('mrp:forecast_model_detail', args=[fm.pk]))
        assert r.status_code == 200
        assert b'<script>alert(1)</script>' not in r.content


@pytest.mark.django_db
class TestForecastModelEdit:
    def test_edit_pre_fills_and_saves(self, admin_client, forecast_model):
        # GET pre-fills
        r = admin_client.get(reverse('mrp:forecast_model_edit', args=[forecast_model.pk]))
        assert r.status_code == 200
        assert forecast_model.name.encode() in r.content
        # POST with new description persists
        r = admin_client.post(reverse('mrp:forecast_model_edit', args=[forecast_model.pk]), {
            'name': forecast_model.name, 'description': 'Updated desc',
            'method': forecast_model.method, 'params': '{"window": 3}',
            'period_type': forecast_model.period_type,
            'horizon_periods': forecast_model.horizon_periods,
            'is_active': 'on',
        })
        assert r.status_code == 302
        forecast_model.refresh_from_db()
        assert forecast_model.description == 'Updated desc'

    def test_edit_to_existing_name_blocked(self, admin_client, acme, forecast_model):
        ForecastModel.objects.create(
            tenant=acme, name='Other Model', method='moving_avg',
            params={'window': 3}, period_type='week',
            horizon_periods=12, is_active=True,
        )
        r = admin_client.post(reverse('mrp:forecast_model_edit', args=[forecast_model.pk]), {
            'name': 'Other Model', 'description': '',
            'method': forecast_model.method, 'params': '{}',
            'period_type': forecast_model.period_type,
            'horizon_periods': forecast_model.horizon_periods,
        })
        assert r.status_code == 200
        forecast_model.refresh_from_db()
        assert forecast_model.name != 'Other Model'


@pytest.mark.django_db
class TestForecastModelDelete:
    def test_delete_unreferenced_allowed(self, admin_client, acme):
        fm = ForecastModel.objects.create(
            tenant=acme, name='Lonely', method='moving_avg',
            params={}, period_type='week', horizon_periods=4, is_active=True,
        )
        r = admin_client.post(reverse('mrp:forecast_model_delete', args=[fm.pk]))
        assert r.status_code == 302
        assert not ForecastModel.objects.filter(pk=fm.pk).exists()

    def test_delete_referenced_by_run_blocked(
        self, admin_client, forecast_model, completed_forecast_run,
    ):
        r = admin_client.post(reverse('mrp:forecast_model_delete', args=[forecast_model.pk]))
        # Caught ProtectedError → redirect to detail with red flash; row remains.
        assert r.status_code == 302
        assert ForecastModel.objects.filter(pk=forecast_model.pk).exists()


@pytest.mark.django_db
class TestForecastModelRun:
    def test_run_happy_path_completes(self, admin_client, acme, forecast_model, fg_product):
        r = admin_client.post(reverse('mrp:forecast_model_run', args=[forecast_model.pk]))
        assert r.status_code == 302
        run = ForecastRun.objects.filter(tenant=acme).order_by('-created_at').first()
        assert run is not None
        assert run.status == 'completed'
        # Should have produced ForecastResult rows (one product × horizon periods).
        assert ForecastResult.objects.filter(run=run).count() == forecast_model.horizon_periods

    def test_run_with_bad_params_marks_failed(self, admin_client, acme, forecast_model, fg_product):
        # Bad params trigger int('abc') ValueError inside the engine; the view
        # catches Exception and persists the message to error_message.
        forecast_model.params = {'window': 'abc'}
        forecast_model.save()
        r = admin_client.post(reverse('mrp:forecast_model_run', args=[forecast_model.pk]))
        assert r.status_code == 302
        run = ForecastRun.objects.filter(tenant=acme).order_by('-created_at').first()
        assert run is not None
        assert run.status == 'failed'
        assert run.error_message  # populated, but the user-facing flash is generic (D-18).


@pytest.mark.django_db
class TestForecastRunListAndDetail:
    def test_list_renders(self, admin_client, completed_forecast_run):
        r = admin_client.get(reverse('mrp:forecast_run_list'))
        assert r.status_code == 200
        assert completed_forecast_run.run_number.encode() in r.content

    def test_detail_renders(self, admin_client, completed_forecast_run):
        r = admin_client.get(reverse('mrp:forecast_run_detail', args=[completed_forecast_run.pk]))
        assert r.status_code == 200

    def test_delete_cascades_results(self, admin_client, acme, completed_forecast_run):
        run_pk = completed_forecast_run.pk
        # Confirm there are results to cascade.
        assert ForecastResult.objects.filter(run_id=run_pk).exists()
        r = admin_client.post(reverse('mrp:forecast_run_delete', args=[run_pk]))
        assert r.status_code == 302
        assert not ForecastRun.objects.filter(pk=run_pk).exists()
        assert not ForecastResult.objects.filter(run_id=run_pk).exists()
