"""URL patterns for Module 12 - Cost Management & Accounting."""
from django.urls import path

from . import views

app_name = 'cost'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),

    # 12.1 Standard Cost Versions
    path('standard-versions/', views.StandardCostVersionListView.as_view(), name='version_list'),
    path('standard-versions/new/', views.StandardCostVersionCreateView.as_view(), name='version_create'),
    path('standard-versions/<int:pk>/', views.StandardCostVersionDetailView.as_view(), name='version_detail'),
    path('standard-versions/<int:pk>/edit/', views.StandardCostVersionEditView.as_view(), name='version_edit'),
    path('standard-versions/<int:pk>/delete/', views.StandardCostVersionDeleteView.as_view(), name='version_delete'),
    path('standard-versions/<int:pk>/approve/', views.StandardCostVersionApproveView.as_view(), name='version_approve'),
    path('standard-versions/<int:pk>/activate/', views.StandardCostVersionActivateView.as_view(), name='version_activate'),
    path('standard-versions/<int:pk>/archive/', views.StandardCostVersionArchiveView.as_view(), name='version_archive'),
    path('standard-versions/<int:pk>/recompute/', views.StandardCostVersionRecomputeView.as_view(), name='version_recompute'),
    path('standard-versions/compare/', views.StandardCostCompareView.as_view(), name='version_compare'),

    # 12.1 Standard Cost rows
    path('standard-costs/', views.StandardCostListView.as_view(), name='standard_cost_list'),
    path('standard-versions/<int:version_pk>/costs/new/', views.StandardCostCreateView.as_view(), name='standard_cost_create'),
    path('standard-costs/<int:pk>/edit/', views.StandardCostEditView.as_view(), name='standard_cost_edit'),
    path('standard-costs/<int:pk>/delete/', views.StandardCostDeleteView.as_view(), name='standard_cost_delete'),

    # 12.2 Actual Costs
    path('actual-costs/', views.ActualCostListView.as_view(), name='actual_cost_list'),
    path('actual-costs/<int:pk>/', views.ActualCostDetailView.as_view(), name='actual_cost_detail'),
    path('actual-costs/<int:po_pk>/recompute/', views.ActualCostRecomputeView.as_view(), name='actual_cost_recompute'),

    # 12.2 Variances
    path('variances/', views.CostVarianceListView.as_view(), name='variance_list'),
    path('variances/new/', views.CostVarianceCreateView.as_view(), name='variance_create'),
    path('variances/<int:pk>/', views.CostVarianceDetailView.as_view(), name='variance_detail'),
    path('variances/<int:pk>/edit/', views.CostVarianceEditView.as_view(), name='variance_edit'),
    path('variances/<int:pk>/delete/', views.CostVarianceDeleteView.as_view(), name='variance_delete'),
    path('variances/<int:pk>/recompute/', views.CostVarianceRecomputeView.as_view(), name='variance_recompute'),

    # 12.3 Jobs / WIP
    path('jobs/', views.JobCostListView.as_view(), name='job_list'),
    path('jobs/new/', views.JobCostCreateView.as_view(), name='job_create'),
    path('jobs/<int:pk>/', views.JobCostDetailView.as_view(), name='job_detail'),
    path('jobs/<int:pk>/close/', views.JobCloseView.as_view(), name='job_close'),
    path('jobs/<int:pk>/delete/', views.JobCostDeleteView.as_view(), name='job_delete'),
    path('wip-entries/', views.WIPEntryListView.as_view(), name='wip_list'),
    path('wip-entries/new/', views.WIPEntryCreateView.as_view(), name='wip_create'),
    path('wip-entries/<int:pk>/', views.WIPEntryDetailView.as_view(), name='wip_detail'),
    path('wip-entries/<int:pk>/delete/', views.WIPEntryDeleteView.as_view(), name='wip_delete'),

    # 12.4 Cost Drivers
    path('cost-drivers/', views.CostDriverListView.as_view(), name='driver_list'),
    path('cost-drivers/new/', views.CostDriverCreateView.as_view(), name='driver_create'),
    path('cost-drivers/<int:pk>/edit/', views.CostDriverEditView.as_view(), name='driver_edit'),
    path('cost-drivers/<int:pk>/delete/', views.CostDriverDeleteView.as_view(), name='driver_delete'),

    # 12.4 Pools
    path('overhead-pools/', views.OverheadPoolListView.as_view(), name='pool_list'),
    path('overhead-pools/new/', views.OverheadPoolCreateView.as_view(), name='pool_create'),
    path('overhead-pools/<int:pk>/edit/', views.OverheadPoolEditView.as_view(), name='pool_edit'),
    path('overhead-pools/<int:pk>/delete/', views.OverheadPoolDeleteView.as_view(), name='pool_delete'),

    # 12.4 Rates
    path('overhead-rates/', views.OverheadRateListView.as_view(), name='rate_list'),
    path('overhead-rates/new/', views.OverheadRateCreateView.as_view(), name='rate_create'),
    path('overhead-rates/<int:pk>/edit/', views.OverheadRateEditView.as_view(), name='rate_edit'),
    path('overhead-rates/<int:pk>/delete/', views.OverheadRateDeleteView.as_view(), name='rate_delete'),

    # 12.4 Driver Actuals
    path('driver-actuals/', views.DriverActualsListView.as_view(), name='driver_actuals_list'),
    path('driver-actuals/new/', views.DriverActualsCreateView.as_view(), name='driver_actuals_create'),
    path('driver-actuals/<int:pk>/edit/', views.DriverActualsEditView.as_view(), name='driver_actuals_edit'),
    path('driver-actuals/<int:pk>/delete/', views.DriverActualsDeleteView.as_view(), name='driver_actuals_delete'),

    # 12.4 Allocations
    path('overhead-allocations/', views.OverheadAllocationListView.as_view(), name='allocation_list'),
    path('overhead-allocations/<int:pk>/', views.OverheadAllocationDetailView.as_view(), name='allocation_detail'),
    path('overhead-allocations/apply/', views.OverheadApplyView.as_view(), name='allocation_apply'),
    path('overhead-allocations/<int:pk>/reverse/', views.OverheadReverseView.as_view(), name='allocation_reverse'),

    # 12.5 Periods
    path('periods/', views.PeriodListView.as_view(), name='period_list'),
    path('periods/new/', views.PeriodCreateView.as_view(), name='period_create'),
    path('periods/<int:pk>/', views.PeriodDetailView.as_view(), name='period_detail'),
    path('periods/<int:pk>/edit/', views.PeriodEditView.as_view(), name='period_edit'),
    path('periods/<int:pk>/delete/', views.PeriodDeleteView.as_view(), name='period_delete'),
    path('periods/<int:pk>/lock/', views.PeriodLockView.as_view(), name='period_lock'),
    path('periods/<int:pk>/close/', views.PeriodCloseView.as_view(), name='period_close'),

    # 12.5 COGM
    path('cogm/', views.COGMReportListView.as_view(), name='cogm_list'),
    path('cogm/<int:pk>/', views.COGMReportDetailView.as_view(), name='cogm_detail'),
    path('cogm/<int:period_pk>/generate/', views.COGMGenerateView.as_view(), name='cogm_generate'),

    # 12.5 Gross Margin
    path('gross-margin/', views.GrossMarginListView.as_view(), name='margin_list'),
    path('gross-margin/<int:pk>/', views.GrossMarginDetailView.as_view(), name='margin_detail'),
    path('gross-margin/<int:period_pk>/generate/', views.GrossMarginGenerateView.as_view(), name='margin_generate'),

    # 12.5 Plant P&L
    path('plant-pnl/', views.PlantPnLListView.as_view(), name='pnl_list'),
    path('plant-pnl/<int:pk>/', views.PlantPnLDetailView.as_view(), name='pnl_detail'),
    path('plant-pnl/generate/', views.PlantPnLGenerateView.as_view(), name='pnl_generate'),
]
