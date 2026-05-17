"""Module 20 - WFA URL patterns."""
from django.urls import path

from . import views

app_name = 'wfa'

urlpatterns = [
    path('', views.index_view, name='index'),

    # 20.1  Visual Workflow Designer ------------------------------------------
    path('categories/', views.category_list_view, name='category_list'),
    path('categories/new/', views.category_create_view, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit_view, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete_view, name='category_delete'),

    path('processes/', views.process_list_view, name='process_list'),
    path('processes/new/', views.process_create_view, name='process_create'),
    path('processes/<int:pk>/', views.process_detail_view, name='process_detail'),
    path('processes/<int:pk>/edit/', views.process_edit_view, name='process_edit'),
    path('processes/<int:pk>/delete/', views.process_delete_view, name='process_delete'),
    path('processes/<int:pk>/activate/', views.process_activate_view, name='process_activate'),
    path('processes/<int:pk>/archive/', views.process_archive_view, name='process_archive'),
    path('processes/<int:pk>/diagram/', views.process_diagram_view, name='process_diagram'),
    path('processes/<int:definition_pk>/nodes/new/', views.node_create_view, name='node_create'),
    path('nodes/<int:pk>/edit/', views.node_edit_view, name='node_edit'),
    path('nodes/<int:pk>/delete/', views.node_delete_view, name='node_delete'),
    path('processes/<int:definition_pk>/transitions/new/', views.transition_create_view, name='transition_create'),
    path('transitions/<int:pk>/delete/', views.transition_delete_view, name='transition_delete'),

    path('instances/', views.instance_list_view, name='instance_list'),
    path('instances/new/', views.instance_create_view, name='instance_create'),
    path('instances/<int:pk>/', views.instance_detail_view, name='instance_detail'),
    path('instances/<int:pk>/advance/', views.instance_advance_view, name='instance_advance'),
    path('instances/<int:pk>/cancel/', views.instance_cancel_view, name='instance_cancel'),
    path('instances/<int:pk>/delete/', views.instance_delete_view, name='instance_delete'),

    # 20.2  Approval Engine ---------------------------------------------------
    path('approvals/policies/', views.policy_list_view, name='policy_list'),
    path('approvals/policies/new/', views.policy_create_view, name='policy_create'),
    path('approvals/policies/<int:pk>/', views.policy_detail_view, name='policy_detail'),
    path('approvals/policies/<int:pk>/edit/', views.policy_edit_view, name='policy_edit'),
    path('approvals/policies/<int:pk>/delete/', views.policy_delete_view, name='policy_delete'),
    path('approvals/policies/<int:policy_pk>/levels/new/', views.level_create_view, name='level_create'),
    path('approvals/levels/<int:pk>/edit/', views.level_edit_view, name='level_edit'),
    path('approvals/levels/<int:pk>/delete/', views.level_delete_view, name='level_delete'),
    path('approvals/policies/<int:policy_pk>/escalations/new/', views.escalation_create_view, name='escalation_create'),
    path('approvals/escalations/<int:pk>/delete/', views.escalation_delete_view, name='escalation_delete'),

    path('approvals/requests/', views.request_list_view, name='request_list'),
    path('approvals/my/', views.my_requests_view, name='my_requests'),
    path('approvals/requests/new/', views.request_create_view, name='request_create'),
    path('approvals/requests/<int:pk>/', views.request_detail_view, name='request_detail'),
    path('approvals/requests/<int:pk>/approve/', views.request_approve_view, name='request_approve'),
    path('approvals/requests/<int:pk>/reject/', views.request_reject_view, name='request_reject'),
    path('approvals/requests/<int:pk>/delegate/', views.request_delegate_view, name='request_delegate'),
    path('approvals/requests/<int:pk>/escalate/', views.request_escalate_view, name='request_escalate'),
    path('approvals/requests/<int:pk>/recall/', views.request_recall_view, name='request_recall'),

    path('approvals/delegations/', views.delegation_list_view, name='delegation_list'),
    path('approvals/delegations/new/', views.delegation_create_view, name='delegation_create'),
    path('approvals/delegations/<int:pk>/edit/', views.delegation_edit_view, name='delegation_edit'),
    path('approvals/delegations/<int:pk>/delete/', views.delegation_delete_view, name='delegation_delete'),

    # 20.3  Notification & Escalation Matrix ----------------------------------
    path('notifications/channels/', views.channel_list_view, name='channel_list'),
    path('notifications/channels/new/', views.channel_create_view, name='channel_create'),
    path('notifications/channels/<int:pk>/edit/', views.channel_edit_view, name='channel_edit'),
    path('notifications/channels/<int:pk>/delete/', views.channel_delete_view, name='channel_delete'),

    path('notifications/templates/', views.template_list_view, name='template_list'),
    path('notifications/templates/new/', views.template_create_view, name='template_create'),
    path('notifications/templates/<int:pk>/edit/', views.template_edit_view, name='template_edit'),
    path('notifications/templates/<int:pk>/delete/', views.template_delete_view, name='template_delete'),

    path('notifications/rules/', views.rule_list_view, name='rule_list'),
    path('notifications/rules/new/', views.rule_create_view, name='rule_create'),
    path('notifications/rules/<int:pk>/edit/', views.rule_edit_view, name='rule_edit'),
    path('notifications/rules/<int:pk>/delete/', views.rule_delete_view, name='rule_delete'),

    path('notifications/', views.notification_list_view, name='notification_list'),
    path('notifications/<int:pk>/', views.notification_detail_view, name='notification_detail'),
    path('notifications/<int:pk>/dispatch/', views.notification_dispatch_view, name='notification_dispatch'),

    path('notifications/deliveries/', views.delivery_list_view, name='delivery_list'),
    path('notifications/sms/', views.sms_list_view, name='sms_list'),

    # 20.4  Integration Orchestration -----------------------------------------
    path('integrations/connectors/', views.connector_list_view, name='connector_list'),
    path('integrations/connectors/new/', views.connector_create_view, name='connector_create'),
    path('integrations/connectors/<int:pk>/', views.connector_detail_view, name='connector_detail'),
    path('integrations/connectors/<int:pk>/edit/', views.connector_edit_view, name='connector_edit'),
    path('integrations/connectors/<int:pk>/delete/', views.connector_delete_view, name='connector_delete'),
    path('integrations/connectors/<int:connector_pk>/endpoints/new/', views.endpoint_create_view, name='endpoint_create'),
    path('integrations/endpoints/<int:pk>/edit/', views.endpoint_edit_view, name='endpoint_edit'),
    path('integrations/endpoints/<int:pk>/delete/', views.endpoint_delete_view, name='endpoint_delete'),

    path('integrations/flows/', views.flow_list_view, name='flow_list'),
    path('integrations/flows/new/', views.flow_create_view, name='flow_create'),
    path('integrations/flows/<int:pk>/', views.flow_detail_view, name='flow_detail'),
    path('integrations/flows/<int:pk>/edit/', views.flow_edit_view, name='flow_edit'),
    path('integrations/flows/<int:pk>/delete/', views.flow_delete_view, name='flow_delete'),
    path('integrations/flows/<int:pk>/run/', views.flow_run_view, name='flow_run'),
    path('integrations/flows/<int:flow_pk>/steps/new/', views.step_create_view, name='step_create'),
    path('integrations/steps/<int:pk>/edit/', views.step_edit_view, name='step_edit'),
    path('integrations/steps/<int:pk>/delete/', views.step_delete_view, name='step_delete'),

    path('integrations/runs/', views.run_list_view, name='run_list'),
    path('integrations/runs/<int:pk>/', views.run_detail_view, name='run_detail'),
    path('integrations/outbox/', views.outbox_list_view, name='outbox_list'),

    # 20.5  Process Mining & Optimization -------------------------------------
    path('mining/bottlenecks/', views.bottleneck_list_view, name='bottleneck_list'),
    path('mining/bottlenecks/new/', views.bottleneck_create_view, name='bottleneck_create'),
    path('mining/bottlenecks/<int:pk>/', views.bottleneck_detail_view, name='bottleneck_detail'),
    path('mining/bottlenecks/<int:pk>/delete/', views.bottleneck_delete_view, name='bottleneck_delete'),

    path('mining/suggestions/', views.suggestion_list_view, name='suggestion_list'),
    path('mining/suggestions/new/', views.suggestion_create_view, name='suggestion_create'),
    path('mining/suggestions/<int:pk>/', views.suggestion_detail_view, name='suggestion_detail'),
    path('mining/suggestions/<int:pk>/ack/', views.suggestion_ack_view, name='suggestion_ack'),
    path('mining/suggestions/<int:pk>/dismiss/', views.suggestion_dismiss_view, name='suggestion_dismiss'),
    path('mining/suggestions/<int:pk>/apply/', views.suggestion_apply_view, name='suggestion_apply'),
    path('mining/suggestions/<int:pk>/delete/', views.suggestion_delete_view, name='suggestion_delete'),

    path('mining/cycle-time/', views.cycle_time_list_view, name='cycle_time_list'),
    path('mining/cycle-time/<int:pk>/', views.cycle_time_detail_view, name='cycle_time_detail'),
    path('mining/cycle-time/<int:pk>/delete/', views.cycle_time_delete_view, name='cycle_time_delete'),
]
