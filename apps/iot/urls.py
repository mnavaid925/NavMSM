"""URL patterns for Module 15 - IoT & SCADA Integration.

Surface mirrors apps/utility/urls.py and apps/eam/urls.py conventions:
    <resource>_list / _create / _detail / _edit / _delete plus per-workflow
    POST endpoints (ingest / run / scan / acknowledge / resolve / recompute /
    snapshot / activate / archive).
"""
from django.urls import path

from . import views

app_name = 'iot'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),

    # ------------------------------------------------------------------
    # 15.1  Device Connectivity Hub
    # ------------------------------------------------------------------
    path('protocols/', views.DeviceProtocolListView.as_view(), name='protocol_list'),
    path('protocols/new/', views.DeviceProtocolCreateView.as_view(), name='protocol_create'),
    path('protocols/<int:pk>/edit/', views.DeviceProtocolEditView.as_view(), name='protocol_edit'),
    path('protocols/<int:pk>/delete/', views.DeviceProtocolDeleteView.as_view(), name='protocol_delete'),

    path('brokers/', views.DeviceBrokerListView.as_view(), name='broker_list'),
    path('brokers/new/', views.DeviceBrokerCreateView.as_view(), name='broker_create'),
    path('brokers/<int:pk>/', views.DeviceBrokerDetailView.as_view(), name='broker_detail'),
    path('brokers/<int:pk>/edit/', views.DeviceBrokerEditView.as_view(), name='broker_edit'),
    path('brokers/<int:pk>/delete/', views.DeviceBrokerDeleteView.as_view(), name='broker_delete'),
    path('brokers/<int:pk>/heartbeat/', views.DeviceBrokerHeartbeatView.as_view(), name='broker_heartbeat'),

    path('devices/', views.DeviceListView.as_view(), name='device_list'),
    path('devices/new/', views.DeviceCreateView.as_view(), name='device_create'),
    path('devices/<int:pk>/', views.DeviceDetailView.as_view(), name='device_detail'),
    path('devices/<int:pk>/edit/', views.DeviceEditView.as_view(), name='device_edit'),
    path('devices/<int:pk>/delete/', views.DeviceDeleteView.as_view(), name='device_delete'),
    path('devices/<int:pk>/retire/', views.DeviceRetireView.as_view(), name='device_retire'),
    path('devices/<int:pk>/reactivate/', views.DeviceReactivateView.as_view(), name='device_reactivate'),

    path('tags/', views.DeviceTagListView.as_view(), name='tag_list'),
    path('tags/new/', views.DeviceTagCreateView.as_view(), name='tag_create'),
    path('tags/<int:pk>/edit/', views.DeviceTagEditView.as_view(), name='tag_edit'),
    path('tags/<int:pk>/delete/', views.DeviceTagDeleteView.as_view(), name='tag_delete'),

    # ------------------------------------------------------------------
    # 15.2  Real-Time Data Acquisition
    # ------------------------------------------------------------------
    path('readings/', views.IoTReadingListView.as_view(), name='reading_list'),
    path('readings/new/', views.IoTReadingCreateView.as_view(), name='reading_create'),
    path('readings/<int:pk>/', views.IoTReadingDetailView.as_view(), name='reading_detail'),
    path('readings/<int:pk>/delete/', views.IoTReadingDeleteView.as_view(), name='reading_delete'),
    path('readings/ingest/', views.IoTReadingIngestView.as_view(), name='reading_ingest'),

    path('batches/', views.IoTReadingBatchListView.as_view(), name='batch_list'),
    path('batches/<int:pk>/', views.IoTReadingBatchDetailView.as_view(), name='batch_detail'),

    path('edge-processors/', views.EdgeProcessorListView.as_view(), name='edge_list'),
    path('edge-processors/new/', views.EdgeProcessorCreateView.as_view(), name='edge_create'),
    path('edge-processors/<int:pk>/edit/', views.EdgeProcessorEditView.as_view(), name='edge_edit'),
    path('edge-processors/<int:pk>/delete/', views.EdgeProcessorDeleteView.as_view(), name='edge_delete'),

    path('stream-metrics/', views.StreamMetricListView.as_view(), name='metric_list'),

    # ------------------------------------------------------------------
    # 15.3  Digital Twin Configuration
    # ------------------------------------------------------------------
    path('twins/', views.DigitalTwinListView.as_view(), name='twin_list'),
    path('twins/new/', views.DigitalTwinCreateView.as_view(), name='twin_create'),
    path('twins/<int:pk>/', views.DigitalTwinDetailView.as_view(), name='twin_detail'),
    path('twins/<int:pk>/edit/', views.DigitalTwinEditView.as_view(), name='twin_edit'),
    path('twins/<int:pk>/delete/', views.DigitalTwinDeleteView.as_view(), name='twin_delete'),
    path('twins/<int:pk>/activate/', views.DigitalTwinActivateView.as_view(), name='twin_activate'),
    path('twins/<int:pk>/archive/', views.DigitalTwinArchiveView.as_view(), name='twin_archive'),
    path('twins/<int:pk>/snapshot/', views.DigitalTwinSnapshotView.as_view(), name='twin_snapshot'),
    path('twins/<int:pk>/recompute/', views.DigitalTwinRecomputeView.as_view(), name='twin_recompute'),

    path('twins/<int:twin_pk>/attributes/new/', views.TwinAttributeCreateView.as_view(), name='twin_attribute_create'),
    path('twins/attributes/<int:pk>/edit/', views.TwinAttributeEditView.as_view(), name='twin_attribute_edit'),
    path('twins/attributes/<int:pk>/delete/', views.TwinAttributeDeleteView.as_view(), name='twin_attribute_delete'),

    path('twins/<int:twin_pk>/scenarios/new/', views.TwinScenarioCreateView.as_view(), name='twin_scenario_create'),
    path('twins/scenarios/<int:pk>/', views.TwinScenarioDetailView.as_view(), name='twin_scenario_detail'),
    path('twins/scenarios/<int:pk>/run/', views.TwinScenarioRunView.as_view(), name='twin_scenario_run'),
    path('twins/scenarios/<int:pk>/delete/', views.TwinScenarioDeleteView.as_view(), name='twin_scenario_delete'),

    # ------------------------------------------------------------------
    # 15.4  OEE Monitoring
    # ------------------------------------------------------------------
    path('oee/', views.OEEDashboardView.as_view(), name='oee_dashboard'),
    path('oee/periods/', views.OEEPeriodListView.as_view(), name='oee_period_list'),
    path('oee/periods/new/', views.OEEPeriodCreateView.as_view(), name='oee_period_create'),
    path('oee/periods/<int:pk>/', views.OEEPeriodDetailView.as_view(), name='oee_period_detail'),
    path('oee/periods/<int:pk>/edit/', views.OEEPeriodEditView.as_view(), name='oee_period_edit'),
    path('oee/periods/<int:pk>/delete/', views.OEEPeriodDeleteView.as_view(), name='oee_period_delete'),
    path('oee/periods/<int:pk>/recompute/', views.OEEPeriodRecomputeView.as_view(), name='oee_period_recompute'),

    path('oee/state-logs/', views.MachineStateLogListView.as_view(), name='state_log_list'),
    path('oee/state-logs/new/', views.MachineStateLogCreateView.as_view(), name='state_log_create'),
    path('oee/state-logs/<int:pk>/', views.MachineStateLogDetailView.as_view(), name='state_log_detail'),
    path('oee/state-logs/<int:pk>/delete/', views.MachineStateLogDeleteView.as_view(), name='state_log_delete'),

    path('oee/loss-reasons/', views.LossReasonListView.as_view(), name='loss_reason_list'),
    path('oee/loss-reasons/new/', views.LossReasonCreateView.as_view(), name='loss_reason_create'),
    path('oee/loss-reasons/<int:pk>/edit/', views.LossReasonEditView.as_view(), name='loss_reason_edit'),
    path('oee/loss-reasons/<int:pk>/delete/', views.LossReasonDeleteView.as_view(), name='loss_reason_delete'),

    # ------------------------------------------------------------------
    # 15.5  Alert & Anomaly Detection
    # ------------------------------------------------------------------
    path('alerts/rules/', views.AlertRuleListView.as_view(), name='rule_list'),
    path('alerts/rules/new/', views.AlertRuleCreateView.as_view(), name='rule_create'),
    path('alerts/rules/<int:pk>/', views.AlertRuleDetailView.as_view(), name='rule_detail'),
    path('alerts/rules/<int:pk>/edit/', views.AlertRuleEditView.as_view(), name='rule_edit'),
    path('alerts/rules/<int:pk>/delete/', views.AlertRuleDeleteView.as_view(), name='rule_delete'),
    path('alerts/rules/<int:pk>/activate/', views.AlertRuleActivateView.as_view(), name='rule_activate'),
    path('alerts/rules/<int:pk>/deactivate/', views.AlertRuleDeactivateView.as_view(), name='rule_deactivate'),

    path('alerts/detections/', views.AnomalyDetectionListView.as_view(), name='detection_list'),
    path('alerts/detections/<int:pk>/', views.AnomalyDetectionDetailView.as_view(), name='detection_detail'),
    path('alerts/detections/<int:pk>/acknowledge/', views.AnomalyDetectionAcknowledgeView.as_view(), name='detection_acknowledge'),
    path('alerts/detections/<int:pk>/resolve/', views.AnomalyDetectionResolveView.as_view(), name='detection_resolve'),
    path('alerts/detections/<int:pk>/false-positive/', views.AnomalyDetectionFalsePositiveView.as_view(), name='detection_false_positive'),

    path('alerts/notifications/', views.AlertNotificationListView.as_view(), name='notification_list'),
]
