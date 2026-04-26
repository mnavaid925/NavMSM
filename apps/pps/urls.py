from django.urls import path

from . import views

app_name = 'pps'

urlpatterns = [
    # Index / dashboard
    path('', views.PPSIndexView.as_view(), name='index'),

    # ---- 4.1  Demand Forecasts ----
    path('forecasts/', views.DemandForecastListView.as_view(), name='forecast_list'),
    path('forecasts/new/', views.DemandForecastCreateView.as_view(), name='forecast_create'),
    path('forecasts/<int:pk>/', views.DemandForecastDetailView.as_view(), name='forecast_detail'),
    path('forecasts/<int:pk>/edit/', views.DemandForecastEditView.as_view(), name='forecast_edit'),
    path('forecasts/<int:pk>/delete/', views.DemandForecastDeleteView.as_view(), name='forecast_delete'),

    # ---- 4.1  Master Production Schedule ----
    path('mps/', views.MPSListView.as_view(), name='mps_list'),
    path('mps/new/', views.MPSCreateView.as_view(), name='mps_create'),
    path('mps/<int:pk>/', views.MPSDetailView.as_view(), name='mps_detail'),
    path('mps/<int:pk>/edit/', views.MPSEditView.as_view(), name='mps_edit'),
    path('mps/<int:pk>/delete/', views.MPSDeleteView.as_view(), name='mps_delete'),
    path('mps/<int:pk>/submit/', views.MPSSubmitView.as_view(), name='mps_submit'),
    path('mps/<int:pk>/approve/', views.MPSApproveView.as_view(), name='mps_approve'),
    path('mps/<int:pk>/release/', views.MPSReleaseView.as_view(), name='mps_release'),
    path('mps/<int:pk>/obsolete/', views.MPSObsoleteView.as_view(), name='mps_obsolete'),
    # MPS lines (nested)
    path('mps/<int:mps_id>/lines/new/', views.MPSLineCreateView.as_view(), name='mps_line_create'),
    path('mps/lines/<int:pk>/edit/', views.MPSLineEditView.as_view(), name='mps_line_edit'),
    path('mps/lines/<int:pk>/delete/', views.MPSLineDeleteView.as_view(), name='mps_line_delete'),

    # ---- 4.2  Work Centers ----
    path('work-centers/', views.WorkCenterListView.as_view(), name='work_center_list'),
    path('work-centers/new/', views.WorkCenterCreateView.as_view(), name='work_center_create'),
    path('work-centers/<int:pk>/', views.WorkCenterDetailView.as_view(), name='work_center_detail'),
    path('work-centers/<int:pk>/edit/', views.WorkCenterEditView.as_view(), name='work_center_edit'),
    path('work-centers/<int:pk>/delete/', views.WorkCenterDeleteView.as_view(), name='work_center_delete'),

    # ---- 4.2  Capacity Calendars ----
    path('calendars/', views.CapacityCalendarListView.as_view(), name='calendar_list'),
    path('calendars/new/', views.CapacityCalendarCreateView.as_view(), name='calendar_create'),
    path('calendars/<int:pk>/edit/', views.CapacityCalendarEditView.as_view(), name='calendar_edit'),
    path('calendars/<int:pk>/delete/', views.CapacityCalendarDeleteView.as_view(), name='calendar_delete'),

    # ---- 4.2  Capacity Load Dashboard ----
    path('capacity/', views.CapacityDashboardView.as_view(), name='capacity_dashboard'),
    path('capacity/recompute/', views.CapacityRecomputeView.as_view(), name='capacity_recompute'),

    # ---- 4.3  Routings ----
    path('routings/', views.RoutingListView.as_view(), name='routing_list'),
    path('routings/new/', views.RoutingCreateView.as_view(), name='routing_create'),
    path('routings/<int:pk>/', views.RoutingDetailView.as_view(), name='routing_detail'),
    path('routings/<int:pk>/edit/', views.RoutingEditView.as_view(), name='routing_edit'),
    path('routings/<int:pk>/delete/', views.RoutingDeleteView.as_view(), name='routing_delete'),
    # Operations (nested under routing)
    path('routings/<int:routing_id>/operations/new/', views.RoutingOperationCreateView.as_view(), name='routing_op_create'),
    path('operations/<int:pk>/edit/', views.RoutingOperationEditView.as_view(), name='routing_op_edit'),
    path('operations/<int:pk>/delete/', views.RoutingOperationDeleteView.as_view(), name='routing_op_delete'),

    # ---- 4.3  Production Orders ----
    path('orders/', views.ProductionOrderListView.as_view(), name='order_list'),
    path('orders/gantt/', views.OrderGanttView.as_view(), name='order_gantt'),
    path('orders/new/', views.ProductionOrderCreateView.as_view(), name='order_create'),
    path('orders/<int:pk>/', views.ProductionOrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:pk>/edit/', views.ProductionOrderEditView.as_view(), name='order_edit'),
    path('orders/<int:pk>/delete/', views.ProductionOrderDeleteView.as_view(), name='order_delete'),
    path('orders/<int:pk>/release/', views.ProductionOrderReleaseView.as_view(), name='order_release'),
    path('orders/<int:pk>/start/', views.ProductionOrderStartView.as_view(), name='order_start'),
    path('orders/<int:pk>/complete/', views.ProductionOrderCompleteView.as_view(), name='order_complete'),
    path('orders/<int:pk>/cancel/', views.ProductionOrderCancelView.as_view(), name='order_cancel'),
    path('orders/<int:pk>/schedule/', views.ProductionOrderScheduleView.as_view(), name='order_schedule'),

    # ---- 4.4  Scenarios ----
    path('scenarios/', views.ScenarioListView.as_view(), name='scenario_list'),
    path('scenarios/new/', views.ScenarioCreateView.as_view(), name='scenario_create'),
    path('scenarios/<int:pk>/', views.ScenarioDetailView.as_view(), name='scenario_detail'),
    path('scenarios/<int:pk>/edit/', views.ScenarioEditView.as_view(), name='scenario_edit'),
    path('scenarios/<int:pk>/delete/', views.ScenarioDeleteView.as_view(), name='scenario_delete'),
    path('scenarios/<int:pk>/run/', views.ScenarioRunView.as_view(), name='scenario_run'),
    path('scenarios/<int:pk>/apply/', views.ScenarioApplyView.as_view(), name='scenario_apply'),
    path('scenarios/<int:pk>/discard/', views.ScenarioDiscardView.as_view(), name='scenario_discard'),
    # Scenario changes (nested)
    path('scenarios/<int:scenario_id>/changes/new/', views.ScenarioChangeCreateView.as_view(), name='scenario_change_create'),
    path('scenarios/changes/<int:pk>/edit/', views.ScenarioChangeEditView.as_view(), name='scenario_change_edit'),
    path('scenarios/changes/<int:pk>/delete/', views.ScenarioChangeDeleteView.as_view(), name='scenario_change_delete'),

    # ---- 4.5  Optimization ----
    path('optimizer/objectives/', views.OptimizationObjectiveListView.as_view(), name='objective_list'),
    path('optimizer/objectives/new/', views.OptimizationObjectiveCreateView.as_view(), name='objective_create'),
    path('optimizer/objectives/<int:pk>/edit/', views.OptimizationObjectiveEditView.as_view(), name='objective_edit'),
    path('optimizer/objectives/<int:pk>/delete/', views.OptimizationObjectiveDeleteView.as_view(), name='objective_delete'),
    path('optimizer/runs/', views.OptimizationRunListView.as_view(), name='run_list'),
    path('optimizer/runs/new/', views.OptimizationRunCreateView.as_view(), name='run_create'),
    path('optimizer/runs/<int:pk>/', views.OptimizationRunDetailView.as_view(), name='run_detail'),
    path('optimizer/runs/<int:pk>/delete/', views.OptimizationRunDeleteView.as_view(), name='run_delete'),
    path('optimizer/runs/<int:pk>/start/', views.OptimizationStartView.as_view(), name='run_start'),
    path('optimizer/runs/<int:pk>/apply/', views.OptimizationApplyView.as_view(), name='run_apply'),
    path('optimizer/runs/<int:pk>/discard/', views.OptimizationDiscardView.as_view(), name='run_discard'),
]
