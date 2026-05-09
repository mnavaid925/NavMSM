"""URL patterns for Module 14 - Energy & Utility Management.

Surface mirrors apps/cost/urls.py conventions:
    <resource>_list / _create / _detail / _edit / _delete plus per-workflow
    POST endpoints (post / reverse / activate / cancel / scan / ack / dismiss /
    recompute / generate).
"""
from django.urls import path

from . import views

app_name = 'utility'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),

    # 14.1 Utility Types
    path('types/', views.UtilityTypeListView.as_view(), name='type_list'),
    path('types/new/', views.UtilityTypeCreateView.as_view(), name='type_create'),
    path('types/<int:pk>/edit/', views.UtilityTypeEditView.as_view(), name='type_edit'),
    path('types/<int:pk>/delete/', views.UtilityTypeDeleteView.as_view(), name='type_delete'),

    # 14.1 Utility Meters
    path('meters/', views.UtilityMeterListView.as_view(), name='meter_list'),
    path('meters/new/', views.UtilityMeterCreateView.as_view(), name='meter_create'),
    path('meters/<int:pk>/', views.UtilityMeterDetailView.as_view(), name='meter_detail'),
    path('meters/<int:pk>/edit/', views.UtilityMeterEditView.as_view(), name='meter_edit'),
    path('meters/<int:pk>/delete/', views.UtilityMeterDeleteView.as_view(), name='meter_delete'),

    # 14.1 Utility Consumption
    path('consumption/', views.UtilityConsumptionListView.as_view(), name='consumption_list'),
    path('consumption/new/', views.UtilityConsumptionCreateView.as_view(), name='consumption_create'),
    path('consumption/<int:pk>/', views.UtilityConsumptionDetailView.as_view(), name='consumption_detail'),
    path('consumption/<int:pk>/edit/', views.UtilityConsumptionEditView.as_view(), name='consumption_edit'),
    path('consumption/<int:pk>/delete/', views.UtilityConsumptionDeleteView.as_view(), name='consumption_delete'),
    path('consumption/import/', views.UtilityConsumptionImportView.as_view(), name='consumption_import'),

    # 14.2 Utility Tariffs
    path('tariffs/', views.UtilityTariffListView.as_view(), name='tariff_list'),
    path('tariffs/new/', views.UtilityTariffCreateView.as_view(), name='tariff_create'),
    path('tariffs/<int:pk>/', views.UtilityTariffDetailView.as_view(), name='tariff_detail'),
    path('tariffs/<int:pk>/edit/', views.UtilityTariffEditView.as_view(), name='tariff_edit'),
    path('tariffs/<int:pk>/delete/', views.UtilityTariffDeleteView.as_view(), name='tariff_delete'),
    path('tariffs/<int:tariff_pk>/bands/new/', views.TOURateBandCreateView.as_view(), name='band_create'),
    path('tariffs/bands/<int:pk>/delete/', views.TOURateBandDeleteView.as_view(), name='band_delete'),

    # 14.2 Utility Allocations
    path('allocations/', views.UtilityAllocationListView.as_view(), name='allocation_list'),
    path('allocations/post/', views.UtilityAllocationPostView.as_view(), name='allocation_post'),
    path('allocations/<int:pk>/', views.UtilityAllocationDetailView.as_view(), name='allocation_detail'),
    path('allocations/<int:pk>/reverse/', views.UtilityAllocationReverseView.as_view(), name='allocation_reverse'),
    path('allocations/<int:pk>/delete/', views.UtilityAllocationDeleteView.as_view(), name='allocation_delete'),

    # 14.3 Demand Response Events
    path('dr-events/', views.DemandResponseEventListView.as_view(), name='dr_event_list'),
    path('dr-events/new/', views.DemandResponseEventCreateView.as_view(), name='dr_event_create'),
    path('dr-events/<int:pk>/', views.DemandResponseEventDetailView.as_view(), name='dr_event_detail'),
    path('dr-events/<int:pk>/edit/', views.DemandResponseEventEditView.as_view(), name='dr_event_edit'),
    path('dr-events/<int:pk>/activate/', views.DemandResponseEventActivateView.as_view(), name='dr_event_activate'),
    path('dr-events/<int:pk>/complete/', views.DemandResponseEventCompleteView.as_view(), name='dr_event_complete'),
    path('dr-events/<int:pk>/cancel/', views.DemandResponseEventCancelView.as_view(), name='dr_event_cancel'),
    path('dr-events/<int:pk>/delete/', views.DemandResponseEventDeleteView.as_view(), name='dr_event_delete'),

    # 14.3 Peak Shaving Suggestions
    path('peak-suggestions/', views.PeakShavingSuggestionListView.as_view(), name='peak_list'),
    path('peak-suggestions/scan/', views.PeakShavingSuggestionScanView.as_view(), name='peak_scan'),
    path('peak-suggestions/<int:pk>/', views.PeakShavingSuggestionDetailView.as_view(), name='peak_detail'),
    path('peak-suggestions/<int:pk>/ack/', views.PeakShavingSuggestionAckView.as_view(), name='peak_ack'),
    path('peak-suggestions/<int:pk>/dismiss/', views.PeakShavingSuggestionDismissView.as_view(), name='peak_dismiss'),

    # 14.4 Emission Factors
    path('emission-factors/', views.EmissionFactorListView.as_view(), name='factor_list'),
    path('emission-factors/new/', views.EmissionFactorCreateView.as_view(), name='factor_create'),
    path('emission-factors/<int:pk>/edit/', views.EmissionFactorEditView.as_view(), name='factor_edit'),
    path('emission-factors/<int:pk>/delete/', views.EmissionFactorDeleteView.as_view(), name='factor_delete'),

    # 14.4 Carbon Emissions
    path('emissions/', views.CarbonEmissionListView.as_view(), name='emission_list'),
    path('emissions/<int:pk>/', views.CarbonEmissionDetailView.as_view(), name='emission_detail'),
    path('emissions/period/<int:period_pk>/recompute/', views.CarbonEmissionRecomputeView.as_view(), name='emission_recompute'),

    # 14.4 Sustainability KPI
    path('sustainability/', views.SustainabilityKPIListView.as_view(), name='sustainability_list'),
    path('sustainability/<int:pk>/', views.SustainabilityKPIDetailView.as_view(), name='sustainability_detail'),
    path('sustainability/period/<int:period_pk>/generate/', views.SustainabilityKPIGenerateView.as_view(), name='sustainability_generate'),

    # 14.5 Benchmarks
    path('benchmarks/', views.BenchmarkSnapshotListView.as_view(), name='benchmark_list'),
    path('benchmarks/<int:pk>/', views.BenchmarkSnapshotDetailView.as_view(), name='benchmark_detail'),
    path('benchmarks/generate/', views.BenchmarkSnapshotGenerateView.as_view(), name='benchmark_generate'),

    # 14.5 Benchmark Comparison Reports
    path('benchmark-reports/', views.BenchmarkComparisonListView.as_view(), name='benchmark_report_list'),
    path('benchmark-reports/new/', views.BenchmarkComparisonCreateView.as_view(), name='benchmark_report_create'),
    path('benchmark-reports/<int:pk>/', views.BenchmarkComparisonDetailView.as_view(), name='benchmark_report_detail'),
    path('benchmark-reports/<int:pk>/delete/', views.BenchmarkComparisonDeleteView.as_view(), name='benchmark_report_delete'),
]
