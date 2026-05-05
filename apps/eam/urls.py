"""URL patterns for Module 10 - Equipment & Asset Management."""
from django.urls import path

from . import views

app_name = 'eam'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),

    # 10.1  Asset Categories
    path('categories/', views.AssetCategoryListView.as_view(), name='category_list'),
    path('categories/new/', views.AssetCategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:pk>/edit/', views.AssetCategoryEditView.as_view(), name='category_edit'),
    path('categories/<int:pk>/delete/', views.AssetCategoryDeleteView.as_view(), name='category_delete'),

    # 10.1  Assets
    path('assets/', views.AssetListView.as_view(), name='asset_list'),
    path('assets/new/', views.AssetCreateView.as_view(), name='asset_create'),
    path('assets/<int:pk>/', views.AssetDetailView.as_view(), name='asset_detail'),
    path('assets/<int:pk>/edit/', views.AssetEditView.as_view(), name='asset_edit'),
    path('assets/<int:pk>/delete/', views.AssetDeleteView.as_view(), name='asset_delete'),
    path('assets/<int:pk>/retire/', views.AssetRetireView.as_view(), name='asset_retire'),
    path('assets/<int:pk>/reactivate/', views.AssetReactivateView.as_view(), name='asset_reactivate'),

    # 10.1  Spare parts (inline)
    path('assets/<int:pk>/spares/new/', views.AssetSparePartCreateView.as_view(), name='asset_spare_create'),
    path('spares/<int:pk>/delete/', views.AssetSparePartDeleteView.as_view(), name='asset_spare_delete'),

    # 10.1  Meter readings
    path('assets/<int:pk>/readings/new/', views.AssetMeterReadingCreateView.as_view(), name='asset_reading_create'),
    path('meter-readings/', views.AssetMeterReadingListView.as_view(), name='meter_reading_list'),

    # 10.1  Documents
    path('assets/<int:pk>/documents/new/', views.AssetDocumentCreateView.as_view(), name='asset_document_create'),
    path('documents/<int:pk>/delete/', views.AssetDocumentDeleteView.as_view(), name='asset_document_delete'),

    # 10.2  Maintenance Plans
    path('pm-plans/', views.PMPlanListView.as_view(), name='pmplan_list'),
    path('pm-plans/new/', views.PMPlanCreateView.as_view(), name='pmplan_create'),
    path('pm-plans/<int:pk>/', views.PMPlanDetailView.as_view(), name='pmplan_detail'),
    path('pm-plans/<int:pk>/edit/', views.PMPlanEditView.as_view(), name='pmplan_edit'),
    path('pm-plans/<int:pk>/delete/', views.PMPlanDeleteView.as_view(), name='pmplan_delete'),
    path('pm-plans/<int:pk>/tasks/new/', views.PMTaskCreateView.as_view(), name='pmtask_create'),
    path('pm-tasks/<int:pk>/delete/', views.PMTaskDeleteView.as_view(), name='pmtask_delete'),
    path('pm-plans/<int:pk>/generate/', views.PMPlanGenerateView.as_view(), name='pmplan_generate'),

    # 10.2  PM Schedules
    path('pm-schedules/', views.PMScheduleListView.as_view(), name='pmschedule_list'),
    path('pm-schedules/new/', views.PMScheduleCreateView.as_view(), name='pmschedule_create'),
    path('pm-schedules/<int:pk>/', views.PMScheduleDetailView.as_view(), name='pmschedule_detail'),
    path('pm-schedules/<int:pk>/start/', views.PMScheduleStartView.as_view(), name='pmschedule_start'),
    path('pm-schedules/<int:pk>/complete/', views.PMScheduleCompleteView.as_view(), name='pmschedule_complete'),
    path('pm-schedules/<int:pk>/skip/', views.PMScheduleSkipView.as_view(), name='pmschedule_skip'),
    path('pm-schedules/<int:pk>/tasks/new/', views.PMTaskCompletionCreateView.as_view(), name='pmschedule_task_create'),

    # 10.3  Predictive Maintenance
    path('monitoring-points/', views.ConditionPointListView.as_view(), name='condition_point_list'),
    path('monitoring-points/new/', views.ConditionPointCreateView.as_view(), name='condition_point_create'),
    path('monitoring-points/<int:pk>/', views.ConditionPointDetailView.as_view(), name='condition_point_detail'),
    path('monitoring-points/<int:pk>/edit/', views.ConditionPointEditView.as_view(), name='condition_point_edit'),
    path('monitoring-points/<int:pk>/delete/', views.ConditionPointDeleteView.as_view(), name='condition_point_delete'),
    path('monitoring-points/<int:pk>/readings/new/', views.ConditionReadingCreateView.as_view(), name='condition_reading_create'),
    path('readings/', views.ConditionReadingListView.as_view(), name='condition_reading_list'),
    path('readings/new/', views.ConditionReadingCreateView.as_view(), name='condition_reading_create_top'),

    path('predictions/', views.FailurePredictionListView.as_view(), name='prediction_list'),
    path('predictions/<int:pk>/', views.FailurePredictionDetailView.as_view(), name='prediction_detail'),
    path('predictions/<int:pk>/investigate/', views.FailurePredictionInvestigateView.as_view(), name='prediction_investigate'),
    path('predictions/<int:pk>/resolve/', views.FailurePredictionResolveView.as_view(), name='prediction_resolve'),

    # 10.4  Maintenance Work Orders
    path('mwo/', views.MWOListView.as_view(), name='mwo_list'),
    path('mwo/new/', views.MWOCreateView.as_view(), name='mwo_create'),
    path('mwo/<int:pk>/', views.MWODetailView.as_view(), name='mwo_detail'),
    path('mwo/<int:pk>/edit/', views.MWOEditView.as_view(), name='mwo_edit'),
    path('mwo/<int:pk>/delete/', views.MWODeleteView.as_view(), name='mwo_delete'),
    path('mwo/<int:pk>/schedule/', views.MWOScheduleView.as_view(), name='mwo_schedule'),
    path('mwo/<int:pk>/start/', views.MWOStartView.as_view(), name='mwo_start'),
    path('mwo/<int:pk>/hold/', views.MWOHoldView.as_view(), name='mwo_hold'),
    path('mwo/<int:pk>/resume/', views.MWOResumeView.as_view(), name='mwo_resume'),
    path('mwo/<int:pk>/complete/', views.MWOCompleteView.as_view(), name='mwo_complete'),
    path('mwo/<int:pk>/cancel/', views.MWOCancelView.as_view(), name='mwo_cancel'),
    path('mwo/<int:pk>/labor/new/', views.MWOLaborLogCreateView.as_view(), name='mwo_labor_create'),
    path('mwo/<int:pk>/material/new/', views.MWOMaterialLogCreateView.as_view(), name='mwo_material_create'),

    # 10.4  Downtime
    path('downtime/', views.DowntimeListView.as_view(), name='downtime_list'),
    path('downtime/new/', views.DowntimeCreateView.as_view(), name='downtime_create'),
    path('downtime/<int:pk>/delete/', views.DowntimeDeleteView.as_view(), name='downtime_delete'),

    # 10.5  Tools & Dies
    path('tools/', views.ToolListView.as_view(), name='tool_list'),
    path('tools/new/', views.ToolCreateView.as_view(), name='tool_create'),
    path('tools/<int:pk>/', views.ToolDetailView.as_view(), name='tool_detail'),
    path('tools/<int:pk>/edit/', views.ToolEditView.as_view(), name='tool_edit'),
    path('tools/<int:pk>/delete/', views.ToolDeleteView.as_view(), name='tool_delete'),
    path('tools/<int:pk>/retire/', views.ToolRetireView.as_view(), name='tool_retire'),
    path('tools/<int:pk>/reactivate/', views.ToolReactivateView.as_view(), name='tool_reactivate'),
    path('tools/<int:pk>/usage/new/', views.ToolUsageLogCreateView.as_view(), name='tool_usage_create'),
    path('tools/<int:pk>/maintenance/new/', views.ToolMaintenanceRecordCreateView.as_view(), name='tool_maintenance_create'),
    path('tools/<int:pk>/cavities/new/', views.MoldCavityCreateView.as_view(), name='tool_cavity_create'),
    path('tool-maintenance/', views.ToolMaintenanceListView.as_view(), name='tool_maintenance_list'),
]
