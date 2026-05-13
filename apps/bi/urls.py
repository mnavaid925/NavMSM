"""URL conf for Module 16 - Business Intelligence & Analytics."""
from django.urls import path

from . import views


app_name = 'bi'


urlpatterns = [
    # Dashboard
    path('', views.IndexView.as_view(), name='index'),

    # 16.1  KPI Definitions
    path('kpi/definitions/', views.KPIDefinitionListView.as_view(), name='kpi_definition_list'),
    path('kpi/definitions/new/', views.KPIDefinitionCreateView.as_view(), name='kpi_definition_create'),
    path('kpi/definitions/<int:pk>/', views.KPIDefinitionDetailView.as_view(), name='kpi_definition_detail'),
    path('kpi/definitions/<int:pk>/edit/', views.KPIDefinitionEditView.as_view(), name='kpi_definition_edit'),
    path('kpi/definitions/<int:pk>/delete/', views.KPIDefinitionDeleteView.as_view(), name='kpi_definition_delete'),
    path('kpi/definitions/<int:pk>/refresh/', views.KPIDefinitionRefreshView.as_view(), name='kpi_definition_refresh'),
    path('kpi/snapshots/', views.KPISnapshotListView.as_view(), name='kpi_snapshot_list'),

    # 16.1  Dashboards + widgets
    path('dashboards/', views.KPIDashboardListView.as_view(), name='dashboard_list'),
    path('dashboards/new/', views.KPIDashboardCreateView.as_view(), name='dashboard_create'),
    path('dashboards/<int:pk>/', views.KPIDashboardDetailView.as_view(), name='dashboard_detail'),
    path('dashboards/<int:pk>/edit/', views.KPIDashboardEditView.as_view(), name='dashboard_edit'),
    path('dashboards/<int:pk>/delete/', views.KPIDashboardDeleteView.as_view(), name='dashboard_delete'),
    path('dashboards/<int:pk>/refresh/', views.KPIDashboardRefreshView.as_view(), name='dashboard_refresh'),
    path('dashboards/<int:dashboard_pk>/widgets/new/', views.KPIWidgetCreateView.as_view(), name='widget_create'),
    path('widgets/<int:pk>/edit/', views.KPIWidgetEditView.as_view(), name='widget_edit'),
    path('widgets/<int:pk>/delete/', views.KPIWidgetDeleteView.as_view(), name='widget_delete'),

    # 16.2  Report data sources
    path('reports/data-sources/', views.ReportDataSourceListView.as_view(), name='data_source_list'),
    path('reports/data-sources/new/', views.ReportDataSourceCreateView.as_view(), name='data_source_create'),
    path('reports/data-sources/<int:pk>/edit/', views.ReportDataSourceEditView.as_view(), name='data_source_edit'),
    path('reports/data-sources/<int:pk>/delete/', views.ReportDataSourceDeleteView.as_view(), name='data_source_delete'),

    # 16.2  Reports
    path('reports/', views.ReportDefinitionListView.as_view(), name='report_list'),
    path('reports/new/', views.ReportDefinitionCreateView.as_view(), name='report_create'),
    path('reports/<int:pk>/', views.ReportDefinitionDetailView.as_view(), name='report_detail'),
    path('reports/<int:pk>/edit/', views.ReportDefinitionEditView.as_view(), name='report_edit'),
    path('reports/<int:pk>/delete/', views.ReportDefinitionDeleteView.as_view(), name='report_delete'),
    path('reports/<int:pk>/run/', views.ReportRunNowView.as_view(), name='report_run_now'),
    path('reports/<int:report_pk>/fields/new/', views.ReportFieldCreateView.as_view(), name='report_field_create'),
    path('reports/fields/<int:pk>/delete/', views.ReportFieldDeleteView.as_view(), name='report_field_delete'),
    path('reports/<int:report_pk>/filters/new/', views.ReportFilterCreateView.as_view(), name='report_filter_create'),
    path('reports/filters/<int:pk>/delete/', views.ReportFilterDeleteView.as_view(), name='report_filter_delete'),

    # 16.2  Runs
    path('reports/runs/', views.ReportRunListView.as_view(), name='report_run_list'),
    path('reports/runs/<int:pk>/', views.ReportRunDetailView.as_view(), name='report_run_detail'),

    # 16.3  Predictive
    path('predictive/models/', views.PredictiveModelListView.as_view(), name='predictive_model_list'),
    path('predictive/models/new/', views.PredictiveModelCreateView.as_view(), name='predictive_model_create'),
    path('predictive/models/<int:pk>/', views.PredictiveModelDetailView.as_view(), name='predictive_model_detail'),
    path('predictive/models/<int:pk>/edit/', views.PredictiveModelEditView.as_view(), name='predictive_model_edit'),
    path('predictive/models/<int:pk>/delete/', views.PredictiveModelDeleteView.as_view(), name='predictive_model_delete'),
    path('predictive/models/<int:pk>/run/', views.PredictionRunNowView.as_view(), name='prediction_run_now'),
    path('predictive/runs/', views.PredictionRunListView.as_view(), name='prediction_run_list'),
    path('predictive/runs/<int:pk>/', views.PredictionRunDetailView.as_view(), name='prediction_run_detail'),
    path('predictive/runs/<int:pk>/cancel/', views.PredictionRunCancelView.as_view(), name='prediction_run_cancel'),
    path('predictive/trends/', views.TrendAnalysisListView.as_view(), name='trend_list'),

    # 16.4  Data warehouse
    path('marts/', views.DataMartListView.as_view(), name='mart_list'),
    path('marts/new/', views.DataMartCreateView.as_view(), name='mart_create'),
    path('marts/<int:pk>/', views.DataMartDetailView.as_view(), name='mart_detail'),
    path('marts/<int:pk>/edit/', views.DataMartEditView.as_view(), name='mart_edit'),
    path('marts/<int:pk>/delete/', views.DataMartDeleteView.as_view(), name='mart_delete'),
    path('marts/<int:pk>/refresh/', views.DataMartRefreshView.as_view(), name='mart_refresh'),
    path('marts/<int:mart_pk>/columns/new/', views.DataMartColumnCreateView.as_view(), name='mart_column_create'),
    path('marts/columns/<int:pk>/delete/', views.DataMartColumnDeleteView.as_view(), name='mart_column_delete'),

    # 16.5  Distribution
    path('schedules/', views.ReportScheduleListView.as_view(), name='schedule_list'),
    path('schedules/new/', views.ReportScheduleCreateView.as_view(), name='schedule_create'),
    path('schedules/<int:pk>/', views.ReportScheduleDetailView.as_view(), name='schedule_detail'),
    path('schedules/<int:pk>/edit/', views.ReportScheduleEditView.as_view(), name='schedule_edit'),
    path('schedules/<int:pk>/delete/', views.ReportScheduleDeleteView.as_view(), name='schedule_delete'),
    path('schedules/<int:pk>/run/', views.ReportScheduleRunNowView.as_view(), name='schedule_run_now'),
    path('schedules/<int:pk>/disable/', views.ReportScheduleDisableView.as_view(), name='schedule_disable'),
    path('schedules/<int:pk>/pause/', views.ReportSchedulePauseView.as_view(), name='schedule_pause'),
    path('schedules/<int:pk>/resume/', views.ReportScheduleResumeView.as_view(), name='schedule_resume'),
    path('schedules/<int:schedule_pk>/recipients/new/', views.ReportRecipientCreateView.as_view(), name='recipient_create'),
    path('schedules/recipients/<int:pk>/delete/', views.ReportRecipientDeleteView.as_view(), name='recipient_delete'),

    path('deliveries/', views.ReportDeliveryListView.as_view(), name='delivery_list'),
    path('deliveries/<int:pk>/', views.ReportDeliveryDetailView.as_view(), name='delivery_detail'),
    path('exports/', views.ReportExportListView.as_view(), name='export_list'),
    path('exports/<int:pk>/download/', views.ReportExportDownloadView.as_view(), name='export_download'),
]
