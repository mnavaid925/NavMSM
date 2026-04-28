from django.urls import path

from . import views

app_name = 'mes'

urlpatterns = [
    path('', views.MESIndexView.as_view(), name='index'),

    # ---- Operator Terminal ----
    path('terminal/', views.TerminalView.as_view(), name='terminal'),

    # ---- 6.1  Work Orders ----
    path('work-orders/', views.WorkOrderListView.as_view(), name='work_order_list'),
    path('work-orders/<int:pk>/', views.WorkOrderDetailView.as_view(), name='work_order_detail'),
    path('work-orders/<int:pk>/edit/', views.WorkOrderEditView.as_view(), name='work_order_edit'),
    path('work-orders/<int:pk>/delete/', views.WorkOrderDeleteView.as_view(), name='work_order_delete'),
    path('work-orders/<int:pk>/start/', views.WorkOrderStartView.as_view(), name='work_order_start'),
    path('work-orders/<int:pk>/hold/', views.WorkOrderHoldView.as_view(), name='work_order_hold'),
    path('work-orders/<int:pk>/complete/', views.WorkOrderCompleteView.as_view(), name='work_order_complete'),
    path('work-orders/<int:pk>/cancel/', views.WorkOrderCancelView.as_view(), name='work_order_cancel'),

    # ---- 6.1  Operations ----
    path('operations/<int:pk>/', views.OperationDetailView.as_view(), name='operation_detail'),
    path('operations/<int:pk>/start/', views.OperationStartView.as_view(), name='operation_start'),
    path('operations/<int:pk>/pause/', views.OperationPauseView.as_view(), name='operation_pause'),
    path('operations/<int:pk>/resume/', views.OperationResumeView.as_view(), name='operation_resume'),
    path('operations/<int:pk>/stop/', views.OperationStopView.as_view(), name='operation_stop'),

    # ---- 6.1  Dispatch (one-click from PPS ProductionOrder) ----
    path('dispatch/<int:production_order_pk>/', views.DispatchView.as_view(), name='dispatch'),

    # ---- 6.2  Operators + Clock In/Out ----
    path('operators/', views.OperatorListView.as_view(), name='operator_list'),
    path('operators/new/', views.OperatorCreateView.as_view(), name='operator_create'),
    path('operators/<int:pk>/', views.OperatorDetailView.as_view(), name='operator_detail'),
    path('operators/<int:pk>/edit/', views.OperatorEditView.as_view(), name='operator_edit'),
    path('operators/<int:pk>/delete/', views.OperatorDeleteView.as_view(), name='operator_delete'),
    path('operators/<int:pk>/clock-in/', views.OperatorClockInView.as_view(), name='operator_clock_in'),
    path('operators/<int:pk>/clock-out/', views.OperatorClockOutView.as_view(), name='operator_clock_out'),

    # ---- 6.2  Time Logs (read-only) ----
    path('time-logs/', views.TimeLogListView.as_view(), name='time_log_list'),

    # ---- 6.3  Production Reports ----
    path('reports/', views.ReportListView.as_view(), name='report_list'),
    path('reports/new/', views.ReportCreateView.as_view(), name='report_create'),
    path('reports/<int:pk>/', views.ReportDetailView.as_view(), name='report_detail'),
    path('reports/<int:pk>/delete/', views.ReportDeleteView.as_view(), name='report_delete'),

    # ---- 6.4  Andon Alerts ----
    path('andon/', views.AndonListView.as_view(), name='andon_list'),
    path('andon/new/', views.AndonCreateView.as_view(), name='andon_create'),
    path('andon/<int:pk>/', views.AndonDetailView.as_view(), name='andon_detail'),
    path('andon/<int:pk>/edit/', views.AndonEditView.as_view(), name='andon_edit'),
    path('andon/<int:pk>/acknowledge/', views.AndonAcknowledgeView.as_view(), name='andon_acknowledge'),
    path('andon/<int:pk>/resolve/', views.AndonResolveView.as_view(), name='andon_resolve'),
    path('andon/<int:pk>/cancel/', views.AndonCancelView.as_view(), name='andon_cancel'),
    path('andon/<int:pk>/delete/', views.AndonDeleteView.as_view(), name='andon_delete'),

    # ---- 6.5  Work Instructions ----
    path('instructions/', views.InstructionListView.as_view(), name='instruction_list'),
    path('instructions/new/', views.InstructionCreateView.as_view(), name='instruction_create'),
    path('instructions/<int:pk>/', views.InstructionDetailView.as_view(), name='instruction_detail'),
    path('instructions/<int:pk>/edit/', views.InstructionEditView.as_view(), name='instruction_edit'),
    path('instructions/<int:pk>/delete/', views.InstructionDeleteView.as_view(), name='instruction_delete'),
    path('instructions/<int:pk>/versions/new/', views.InstructionVersionCreateView.as_view(), name='instruction_version_create'),
    path('instructions/versions/<int:pk>/release/', views.InstructionVersionReleaseView.as_view(), name='instruction_version_release'),
    path('instructions/versions/<int:pk>/obsolete/', views.InstructionVersionObsoleteView.as_view(), name='instruction_version_obsolete'),
    path('instructions/versions/<int:pk>/download/', views.InstructionVersionDownloadView.as_view(), name='instruction_version_download'),
    path('instructions/<int:pk>/ack/', views.InstructionAcknowledgeView.as_view(), name='instruction_acknowledge'),
]
