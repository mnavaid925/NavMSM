from django.urls import path

from . import views

app_name = 'qms'

urlpatterns = [
    path('', views.QMSIndexView.as_view(), name='index'),

    # ---- 7.1  IQC Plans ----
    path('iqc/plans/', views.IQCPlanListView.as_view(), name='iqc_plan_list'),
    path('iqc/plans/new/', views.IQCPlanCreateView.as_view(), name='iqc_plan_create'),
    path('iqc/plans/<int:pk>/', views.IQCPlanDetailView.as_view(), name='iqc_plan_detail'),
    path('iqc/plans/<int:pk>/edit/', views.IQCPlanEditView.as_view(), name='iqc_plan_edit'),
    path('iqc/plans/<int:pk>/delete/', views.IQCPlanDeleteView.as_view(), name='iqc_plan_delete'),
    path('iqc/plans/<int:plan_id>/characteristics/new/', views.IQCCharacteristicCreateView.as_view(), name='iqc_characteristic_create'),
    path('iqc/characteristics/<int:pk>/delete/', views.IQCCharacteristicDeleteView.as_view(), name='iqc_characteristic_delete'),

    # ---- 7.1  IQC Inspections ----
    path('iqc/inspections/', views.IQCInspectionListView.as_view(), name='iqc_inspection_list'),
    path('iqc/inspections/new/', views.IQCInspectionCreateView.as_view(), name='iqc_inspection_create'),
    path('iqc/inspections/<int:pk>/', views.IQCInspectionDetailView.as_view(), name='iqc_inspection_detail'),
    path('iqc/inspections/<int:pk>/edit/', views.IQCInspectionEditView.as_view(), name='iqc_inspection_edit'),
    path('iqc/inspections/<int:pk>/delete/', views.IQCInspectionDeleteView.as_view(), name='iqc_inspection_delete'),
    path('iqc/inspections/<int:pk>/start/', views.IQCInspectionStartView.as_view(), name='iqc_inspection_start'),
    path('iqc/inspections/<int:pk>/accept/', views.IQCInspectionAcceptView.as_view(), name='iqc_inspection_accept'),
    path('iqc/inspections/<int:pk>/reject/', views.IQCInspectionRejectView.as_view(), name='iqc_inspection_reject'),
    path('iqc/inspections/<int:pk>/deviation/', views.IQCInspectionDeviationView.as_view(), name='iqc_inspection_deviation'),
    path('iqc/inspections/<int:inspection_id>/measurements/new/', views.IQCMeasurementCreateView.as_view(), name='iqc_measurement_create'),

    # ---- 7.2  IPQC Plans ----
    path('ipqc/plans/', views.IPQCPlanListView.as_view(), name='ipqc_plan_list'),
    path('ipqc/plans/new/', views.IPQCPlanCreateView.as_view(), name='ipqc_plan_create'),
    path('ipqc/plans/<int:pk>/', views.IPQCPlanDetailView.as_view(), name='ipqc_plan_detail'),
    path('ipqc/plans/<int:pk>/edit/', views.IPQCPlanEditView.as_view(), name='ipqc_plan_edit'),
    path('ipqc/plans/<int:pk>/delete/', views.IPQCPlanDeleteView.as_view(), name='ipqc_plan_delete'),

    # ---- 7.2  IPQC Inspections ----
    path('ipqc/inspections/', views.IPQCInspectionListView.as_view(), name='ipqc_inspection_list'),
    path('ipqc/inspections/new/', views.IPQCInspectionCreateView.as_view(), name='ipqc_inspection_create'),
    path('ipqc/inspections/<int:pk>/', views.IPQCInspectionDetailView.as_view(), name='ipqc_inspection_detail'),
    path('ipqc/inspections/<int:pk>/edit/', views.IPQCInspectionEditView.as_view(), name='ipqc_inspection_edit'),
    path('ipqc/inspections/<int:pk>/delete/', views.IPQCInspectionDeleteView.as_view(), name='ipqc_inspection_delete'),

    # ---- 7.2  SPC Charts ----
    path('ipqc/charts/', views.SPCChartListView.as_view(), name='spc_chart_list'),
    path('ipqc/charts/<int:pk>/', views.SPCChartDetailView.as_view(), name='spc_chart_detail'),
    path('ipqc/charts/<int:pk>/recompute/', views.SPCChartRecomputeView.as_view(), name='spc_chart_recompute'),

    # ---- 7.3  FQC Plans ----
    path('fqc/plans/', views.FQCPlanListView.as_view(), name='fqc_plan_list'),
    path('fqc/plans/new/', views.FQCPlanCreateView.as_view(), name='fqc_plan_create'),
    path('fqc/plans/<int:pk>/', views.FQCPlanDetailView.as_view(), name='fqc_plan_detail'),
    path('fqc/plans/<int:pk>/edit/', views.FQCPlanEditView.as_view(), name='fqc_plan_edit'),
    path('fqc/plans/<int:pk>/delete/', views.FQCPlanDeleteView.as_view(), name='fqc_plan_delete'),
    path('fqc/plans/<int:plan_id>/specs/new/', views.FQCSpecCreateView.as_view(), name='fqc_spec_create'),
    path('fqc/specs/<int:pk>/delete/', views.FQCSpecDeleteView.as_view(), name='fqc_spec_delete'),

    # ---- 7.3  FQC Inspections ----
    path('fqc/inspections/', views.FQCInspectionListView.as_view(), name='fqc_inspection_list'),
    path('fqc/inspections/new/', views.FQCInspectionCreateView.as_view(), name='fqc_inspection_create'),
    path('fqc/inspections/<int:pk>/', views.FQCInspectionDetailView.as_view(), name='fqc_inspection_detail'),
    path('fqc/inspections/<int:pk>/edit/', views.FQCInspectionEditView.as_view(), name='fqc_inspection_edit'),
    path('fqc/inspections/<int:pk>/delete/', views.FQCInspectionDeleteView.as_view(), name='fqc_inspection_delete'),
    path('fqc/inspections/<int:pk>/start/', views.FQCInspectionStartView.as_view(), name='fqc_inspection_start'),
    path('fqc/inspections/<int:pk>/pass/', views.FQCInspectionPassView.as_view(), name='fqc_inspection_pass'),
    path('fqc/inspections/<int:pk>/fail/', views.FQCInspectionFailView.as_view(), name='fqc_inspection_fail'),
    path('fqc/inspections/<int:pk>/deviation/', views.FQCInspectionDeviationView.as_view(), name='fqc_inspection_deviation'),
    path('fqc/inspections/<int:inspection_id>/results/new/', views.FQCResultCreateView.as_view(), name='fqc_result_create'),

    # ---- 7.3  CoA ----
    path('fqc/inspections/<int:pk>/coa/', views.CoAGenerateView.as_view(), name='coa_render'),
    path('fqc/inspections/<int:pk>/coa/release/', views.CoAReleaseView.as_view(), name='coa_release'),

    # ---- 7.4  NCR ----
    path('ncr/', views.NCRListView.as_view(), name='ncr_list'),
    path('ncr/new/', views.NCRCreateView.as_view(), name='ncr_create'),
    path('ncr/<int:pk>/', views.NCRDetailView.as_view(), name='ncr_detail'),
    path('ncr/<int:pk>/edit/', views.NCREditView.as_view(), name='ncr_edit'),
    path('ncr/<int:pk>/delete/', views.NCRDeleteView.as_view(), name='ncr_delete'),
    path('ncr/<int:pk>/investigate/', views.NCRInvestigateView.as_view(), name='ncr_investigate'),
    path('ncr/<int:pk>/await-capa/', views.NCRAwaitCAPAView.as_view(), name='ncr_await_capa'),
    path('ncr/<int:pk>/resolve/', views.NCRResolveView.as_view(), name='ncr_resolve'),
    path('ncr/<int:pk>/close/', views.NCRCloseView.as_view(), name='ncr_close'),
    path('ncr/<int:pk>/cancel/', views.NCRCancelView.as_view(), name='ncr_cancel'),
    path('ncr/<int:pk>/rca/edit/', views.NCRRCAEditView.as_view(), name='ncr_rca_edit'),

    # ---- 7.4  Corrective / Preventive Actions ----
    path('ncr/<int:ncr_id>/ca/new/', views.CACreateView.as_view(), name='ca_create'),
    path('ncr/ca/<int:pk>/edit/', views.CAEditView.as_view(), name='ca_edit'),
    path('ncr/ca/<int:pk>/delete/', views.CADeleteView.as_view(), name='ca_delete'),
    path('ncr/ca/<int:pk>/complete/', views.CACompleteView.as_view(), name='ca_complete'),
    path('ncr/<int:ncr_id>/pa/new/', views.PACreateView.as_view(), name='pa_create'),
    path('ncr/pa/<int:pk>/edit/', views.PAEditView.as_view(), name='pa_edit'),
    path('ncr/pa/<int:pk>/delete/', views.PADeleteView.as_view(), name='pa_delete'),
    path('ncr/pa/<int:pk>/complete/', views.PACompleteView.as_view(), name='pa_complete'),

    # ---- 7.4  NCR Attachments ----
    path('ncr/<int:ncr_id>/attachments/new/', views.NCRAttachmentCreateView.as_view(), name='ncr_attachment_create'),
    path('ncr/attachments/<int:pk>/delete/', views.NCRAttachmentDeleteView.as_view(), name='ncr_attachment_delete'),
    path('ncr/attachments/<int:pk>/download/', views.NCRAttachmentDownloadView.as_view(), name='ncr_attachment_download'),

    # ---- 7.5  Equipment ----
    path('equipment/', views.EquipmentListView.as_view(), name='equipment_list'),
    path('equipment/new/', views.EquipmentCreateView.as_view(), name='equipment_create'),
    path('equipment/<int:pk>/', views.EquipmentDetailView.as_view(), name='equipment_detail'),
    path('equipment/<int:pk>/edit/', views.EquipmentEditView.as_view(), name='equipment_edit'),
    path('equipment/<int:pk>/delete/', views.EquipmentDeleteView.as_view(), name='equipment_delete'),
    path('equipment/<int:pk>/retire/', views.EquipmentRetireView.as_view(), name='equipment_retire'),

    # ---- 7.5  Calibration Records ----
    path('calibrations/', views.CalibrationListView.as_view(), name='calibration_list'),
    path('calibrations/new/', views.CalibrationCreateView.as_view(), name='calibration_create'),
    path('calibrations/<int:pk>/', views.CalibrationDetailView.as_view(), name='calibration_detail'),
    path('calibrations/<int:pk>/edit/', views.CalibrationEditView.as_view(), name='calibration_edit'),
    path('calibrations/<int:pk>/delete/', views.CalibrationDeleteView.as_view(), name='calibration_delete'),
    path('calibrations/<int:pk>/certificate/', views.CalibrationCertificateDownloadView.as_view(), name='calibration_certificate_download'),
    path('calibrations/<int:record_id>/checks/new/', views.ToleranceCheckCreateView.as_view(), name='tolerance_check_create'),

    # ---- 7.5  Calibration Standards ----
    path('calibration-standards/', views.CalibrationStandardListView.as_view(), name='standard_list'),
    path('calibration-standards/new/', views.CalibrationStandardCreateView.as_view(), name='standard_create'),
    path('calibration-standards/<int:pk>/edit/', views.CalibrationStandardEditView.as_view(), name='standard_edit'),
    path('calibration-standards/<int:pk>/delete/', views.CalibrationStandardDeleteView.as_view(), name='standard_delete'),
]
