"""Admin registrations for Module 14 — Energy & Utility Management.

Full registration block; mirrors the discoverability pattern used by apps/cost/admin.py.
"""
from django.contrib import admin

from . import models


@admin.register(models.UtilityType)
class UtilityTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'unit_of_measure', 'cost_driver', 'is_active', 'tenant']
    list_filter = ['is_active', 'tenant']
    search_fields = ['code', 'name']


@admin.register(models.UtilityMeter)
class UtilityMeterAdmin(admin.ModelAdmin):
    list_display = ['meter_number', 'name', 'utility_type', 'location', 'is_active', 'tenant']
    list_filter = ['utility_type', 'is_active', 'tenant']
    search_fields = ['meter_number', 'name']


@admin.register(models.UtilityConsumption)
class UtilityConsumptionAdmin(admin.ModelAdmin):
    list_display = ['entry_number', 'meter', 'period_start', 'period_end', 'consumption', 'total_cost', 'source']
    list_filter = ['source', 'is_reversal', 'tenant']
    search_fields = ['entry_number', 'meter__meter_number']


@admin.register(models.UtilityTariff)
class UtilityTariffAdmin(admin.ModelAdmin):
    list_display = ['tariff_number', 'name', 'utility_type', 'flat_rate', 'currency', 'is_active', 'tenant']
    list_filter = ['utility_type', 'is_active', 'tenant']
    search_fields = ['tariff_number', 'name']


@admin.register(models.TOURateBand)
class TOURateBandAdmin(admin.ModelAdmin):
    list_display = ['tariff', 'band_type', 'day_of_week', 'start_time', 'end_time', 'rate']
    list_filter = ['band_type', 'day_of_week']


@admin.register(models.UtilityAllocation)
class UtilityAllocationAdmin(admin.ModelAdmin):
    list_display = ['allocation_number', 'period', 'meter', 'allocation_method', 'allocated_cost', 'is_posted_to_cost']
    list_filter = ['allocation_method', 'is_posted_to_cost', 'tenant']
    search_fields = ['allocation_number']


@admin.register(models.DemandResponseEvent)
class DemandResponseEventAdmin(admin.ModelAdmin):
    list_display = ['event_number', 'utility_type', 'event_type', 'start_at', 'end_at', 'status']
    list_filter = ['event_type', 'status', 'tenant']
    search_fields = ['event_number']


@admin.register(models.PeakShavingSuggestion)
class PeakShavingSuggestionAdmin(admin.ModelAdmin):
    list_display = ['suggestion_number', 'production_order', 'scheduled_operation', 'estimated_savings', 'status']
    list_filter = ['status', 'tenant']
    search_fields = ['suggestion_number']


@admin.register(models.EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ['source_type', 'scope', 'region', 'factor', 'unit_of_measure', 'is_active', 'tenant']
    list_filter = ['scope', 'source_type', 'is_active', 'tenant']
    search_fields = ['source_type']


@admin.register(models.CarbonEmission)
class CarbonEmissionAdmin(admin.ModelAdmin):
    list_display = ['entry_number', 'period', 'scope', 'source_type', 'co2e_kg', 'is_reversal']
    list_filter = ['scope', 'source_type', 'is_reversal', 'tenant']
    search_fields = ['entry_number']


@admin.register(models.SustainabilityKPI)
class SustainabilityKPIAdmin(admin.ModelAdmin):
    list_display = ['period', 'total_co2e_kg', 'total_kwh', 'co2e_per_unit_produced', 'generated_at']
    list_filter = ['tenant']


@admin.register(models.BenchmarkSnapshot)
class BenchmarkSnapshotAdmin(admin.ModelAdmin):
    list_display = ['period', 'plant_label', 'total_kwh', 'total_co2e_kg', 'kwh_per_unit', 'co2e_per_unit', 'tenant']
    list_filter = ['plant_label', 'tenant']


@admin.register(models.BenchmarkComparison)
class BenchmarkComparisonAdmin(admin.ModelAdmin):
    list_display = ['report_number', 'comparison_type', 'from_snapshot', 'to_snapshot', 'kwh_delta_pct', 'co2e_delta_pct']
    list_filter = ['comparison_type', 'tenant']
    search_fields = ['report_number']
