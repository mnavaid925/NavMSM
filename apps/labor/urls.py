"""URL patterns for Module 11 - Labor & Workforce Management."""
from django.urls import path

from . import views

app_name = 'labor'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),

    # 11.1 Departments
    path('departments/', views.DepartmentListView.as_view(), name='department_list'),
    path('departments/new/', views.DepartmentCreateView.as_view(), name='department_create'),
    path('departments/<int:pk>/edit/', views.DepartmentEditView.as_view(), name='department_edit'),
    path('departments/<int:pk>/delete/', views.DepartmentDeleteView.as_view(), name='department_delete'),

    # 11.1 Positions
    path('positions/', views.PositionListView.as_view(), name='position_list'),
    path('positions/new/', views.PositionCreateView.as_view(), name='position_create'),
    path('positions/<int:pk>/edit/', views.PositionEditView.as_view(), name='position_edit'),
    path('positions/<int:pk>/delete/', views.PositionDeleteView.as_view(), name='position_delete'),

    # 11.1 Employees
    path('employees/', views.EmployeeListView.as_view(), name='employee_list'),
    path('employees/new/', views.EmployeeCreateView.as_view(), name='employee_create'),
    path('employees/<int:pk>/', views.EmployeeDetailView.as_view(), name='employee_detail'),
    path('employees/<int:pk>/edit/', views.EmployeeEditView.as_view(), name='employee_edit'),
    path('employees/<int:pk>/delete/', views.EmployeeDeleteView.as_view(), name='employee_delete'),
    path('employees/<int:pk>/terminate/', views.EmployeeTerminateView.as_view(), name='employee_terminate'),
    path('employees/<int:pk>/reactivate/', views.EmployeeReactivateView.as_view(), name='employee_reactivate'),

    # 11.1 Skills + Skills Matrix
    path('skills/', views.SkillListView.as_view(), name='skill_list'),
    path('skills/new/', views.SkillCreateView.as_view(), name='skill_create'),
    path('skills/<int:pk>/edit/', views.SkillEditView.as_view(), name='skill_edit'),
    path('skills/<int:pk>/delete/', views.SkillDeleteView.as_view(), name='skill_delete'),
    path('skills-matrix/', views.SkillsMatrixView.as_view(), name='skills_matrix'),
    path('employees/<int:pk>/skills/new/', views.EmployeeSkillCreateView.as_view(), name='employee_skill_create'),
    path('employee-skills/<int:pk>/delete/', views.EmployeeSkillDeleteView.as_view(), name='employee_skill_delete'),

    # 11.1 Certifications
    path('certifications/', views.CertificationListView.as_view(), name='certification_list'),
    path('certifications/new/', views.CertificationCreateView.as_view(), name='certification_create'),
    path('certifications/<int:pk>/edit/', views.CertificationEditView.as_view(), name='certification_edit'),
    path('certifications/<int:pk>/delete/', views.CertificationDeleteView.as_view(), name='certification_delete'),
    path('employees/<int:pk>/certifications/new/', views.EmployeeCertificationCreateView.as_view(), name='employee_certification_create'),
    path('employee-certifications/<int:pk>/delete/', views.EmployeeCertificationDeleteView.as_view(), name='employee_certification_delete'),

    # 11.1 Documents
    path('employees/<int:pk>/documents/new/', views.EmployeeDocumentCreateView.as_view(), name='employee_document_create'),
    path('employee-documents/<int:pk>/delete/', views.EmployeeDocumentDeleteView.as_view(), name='employee_document_delete'),

    # 11.2 Shifts
    path('shifts/', views.ShiftListView.as_view(), name='shift_list'),
    path('shifts/new/', views.ShiftCreateView.as_view(), name='shift_create'),
    path('shifts/<int:pk>/edit/', views.ShiftEditView.as_view(), name='shift_edit'),
    path('shifts/<int:pk>/delete/', views.ShiftDeleteView.as_view(), name='shift_delete'),

    # 11.2 Shift Rosters
    path('shift-rosters/', views.ShiftRosterListView.as_view(), name='roster_list'),
    path('shift-rosters/new/', views.ShiftRosterCreateView.as_view(), name='roster_create'),
    path('shift-rosters/<int:pk>/edit/', views.ShiftRosterEditView.as_view(), name='roster_edit'),
    path('shift-rosters/<int:pk>/delete/', views.ShiftRosterDeleteView.as_view(), name='roster_delete'),

    # 11.2 Attendance
    path('attendance/', views.AttendanceListView.as_view(), name='attendance_list'),
    path('attendance/new/', views.AttendanceCreateView.as_view(), name='attendance_create'),
    path('attendance/<int:pk>/edit/', views.AttendanceEditView.as_view(), name='attendance_edit'),
    path('attendance/<int:pk>/delete/', views.AttendanceDeleteView.as_view(), name='attendance_delete'),

    # 11.2 Leave Types
    path('leave-types/', views.LeaveTypeListView.as_view(), name='leave_type_list'),
    path('leave-types/new/', views.LeaveTypeCreateView.as_view(), name='leave_type_create'),
    path('leave-types/<int:pk>/edit/', views.LeaveTypeEditView.as_view(), name='leave_type_edit'),
    path('leave-types/<int:pk>/delete/', views.LeaveTypeDeleteView.as_view(), name='leave_type_delete'),

    # 11.2 Leave Requests
    path('leave-requests/', views.LeaveRequestListView.as_view(), name='leave_request_list'),
    path('leave-requests/new/', views.LeaveRequestCreateView.as_view(), name='leave_request_create'),
    path('leave-requests/<int:pk>/', views.LeaveRequestDetailView.as_view(), name='leave_request_detail'),
    path('leave-requests/<int:pk>/edit/', views.LeaveRequestEditView.as_view(), name='leave_request_edit'),
    path('leave-requests/<int:pk>/delete/', views.LeaveRequestDeleteView.as_view(), name='leave_request_delete'),
    path('leave-requests/<int:pk>/submit/', views.LeaveRequestSubmitView.as_view(), name='leave_request_submit'),
    path('leave-requests/<int:pk>/approve/', views.LeaveRequestApproveView.as_view(), name='leave_request_approve'),
    path('leave-requests/<int:pk>/reject/', views.LeaveRequestRejectView.as_view(), name='leave_request_reject'),
    path('leave-requests/<int:pk>/cancel/', views.LeaveRequestCancelView.as_view(), name='leave_request_cancel'),

    # 11.2 Holidays
    path('holidays/', views.HolidayListView.as_view(), name='holiday_list'),
    path('holidays/new/', views.HolidayCreateView.as_view(), name='holiday_create'),
    path('holidays/<int:pk>/edit/', views.HolidayEditView.as_view(), name='holiday_edit'),
    path('holidays/<int:pk>/delete/', views.HolidayDeleteView.as_view(), name='holiday_delete'),

    # 11.3 Cost Centers
    path('cost-centers/', views.CostCenterListView.as_view(), name='cost_center_list'),
    path('cost-centers/new/', views.CostCenterCreateView.as_view(), name='cost_center_create'),
    path('cost-centers/<int:pk>/edit/', views.CostCenterEditView.as_view(), name='cost_center_edit'),
    path('cost-centers/<int:pk>/delete/', views.CostCenterDeleteView.as_view(), name='cost_center_delete'),

    # 11.3 Labor Rates
    path('labor-rates/', views.LaborRateListView.as_view(), name='labor_rate_list'),
    path('labor-rates/new/', views.LaborRateCreateView.as_view(), name='labor_rate_create'),
    path('labor-rates/<int:pk>/edit/', views.LaborRateEditView.as_view(), name='labor_rate_edit'),
    path('labor-rates/<int:pk>/delete/', views.LaborRateDeleteView.as_view(), name='labor_rate_delete'),

    # 11.3 Labor Bookings
    path('labor-bookings/', views.LaborBookingListView.as_view(), name='labor_booking_list'),
    path('labor-bookings/new/', views.LaborBookingCreateView.as_view(), name='labor_booking_create'),
    path('labor-bookings/summary/', views.LaborBookingSummaryView.as_view(), name='labor_booking_summary'),
    path('labor-bookings/<int:pk>/', views.LaborBookingDetailView.as_view(), name='labor_booking_detail'),
    path('labor-bookings/<int:pk>/delete/', views.LaborBookingDeleteView.as_view(), name='labor_booking_delete'),

    # 11.4 Training Programs
    path('training-programs/', views.TrainingProgramListView.as_view(), name='program_list'),
    path('training-programs/new/', views.TrainingProgramCreateView.as_view(), name='program_create'),
    path('training-programs/<int:pk>/edit/', views.TrainingProgramEditView.as_view(), name='program_edit'),
    path('training-programs/<int:pk>/delete/', views.TrainingProgramDeleteView.as_view(), name='program_delete'),

    # 11.4 Training Plans
    path('training-plans/', views.TrainingPlanListView.as_view(), name='plan_list'),
    path('training-plans/new/', views.TrainingPlanCreateView.as_view(), name='plan_create'),
    path('training-plans/<int:pk>/edit/', views.TrainingPlanEditView.as_view(), name='plan_edit'),
    path('training-plans/<int:pk>/delete/', views.TrainingPlanDeleteView.as_view(), name='plan_delete'),
    path('training-plans/<int:pk>/start/', views.TrainingPlanStartView.as_view(), name='plan_start'),
    path('training-plans/<int:pk>/complete/', views.TrainingPlanCompleteView.as_view(), name='plan_complete'),
    path('training-plans/<int:pk>/waive/', views.TrainingPlanWaiveView.as_view(), name='plan_waive'),

    # 11.4 Training Sessions
    path('training-sessions/', views.TrainingSessionListView.as_view(), name='session_list'),
    path('training-sessions/new/', views.TrainingSessionCreateView.as_view(), name='session_create'),
    path('training-sessions/<int:pk>/', views.TrainingSessionDetailView.as_view(), name='session_detail'),
    path('training-sessions/<int:pk>/edit/', views.TrainingSessionEditView.as_view(), name='session_edit'),
    path('training-sessions/<int:pk>/delete/', views.TrainingSessionDeleteView.as_view(), name='session_delete'),
    path('training-sessions/<int:pk>/attendance/new/', views.TrainingAttendanceCreateView.as_view(), name='session_attendance_create'),
    path('training-attendance/<int:pk>/delete/', views.TrainingAttendanceDeleteView.as_view(), name='session_attendance_delete'),

    # 11.4 Competency Assessments
    path('competency-assessments/', views.AssessmentListView.as_view(), name='assessment_list'),
    path('competency-assessments/new/', views.AssessmentCreateView.as_view(), name='assessment_create'),
    path('competency-assessments/<int:pk>/', views.AssessmentDetailView.as_view(), name='assessment_detail'),
    path('competency-assessments/<int:pk>/edit/', views.AssessmentEditView.as_view(), name='assessment_edit'),
    path('competency-assessments/<int:pk>/delete/', views.AssessmentDeleteView.as_view(), name='assessment_delete'),
    path('competency-assessments/<int:pk>/complete/', views.AssessmentCompleteView.as_view(), name='assessment_complete'),
    path('competency-assessments/<int:pk>/results/new/', views.CompetencyResultCreateView.as_view(), name='assessment_result_create'),
    path('competency-results/<int:pk>/delete/', views.CompetencyResultDeleteView.as_view(), name='assessment_result_delete'),

    # 11.5 Incentive Schemes
    path('incentive-schemes/', views.SchemeListView.as_view(), name='scheme_list'),
    path('incentive-schemes/new/', views.SchemeCreateView.as_view(), name='scheme_create'),
    path('incentive-schemes/<int:pk>/', views.SchemeDetailView.as_view(), name='scheme_detail'),
    path('incentive-schemes/<int:pk>/edit/', views.SchemeEditView.as_view(), name='scheme_edit'),
    path('incentive-schemes/<int:pk>/delete/', views.SchemeDeleteView.as_view(), name='scheme_delete'),
    path('incentive-schemes/<int:pk>/rates/new/', views.PieceRateCreateView.as_view(), name='scheme_rate_create'),
    path('piece-rates/<int:pk>/delete/', views.PieceRateDeleteView.as_view(), name='scheme_rate_delete'),

    # 11.5 Periods
    path('incentive-periods/', views.PeriodListView.as_view(), name='period_list'),
    path('incentive-periods/new/', views.PeriodCreateView.as_view(), name='period_create'),
    path('incentive-periods/<int:pk>/edit/', views.PeriodEditView.as_view(), name='period_edit'),
    path('incentive-periods/<int:pk>/delete/', views.PeriodDeleteView.as_view(), name='period_delete'),
    path('incentive-periods/<int:pk>/lock/', views.PeriodLockView.as_view(), name='period_lock'),
    path('incentive-periods/<int:pk>/pay/', views.PeriodPayView.as_view(), name='period_pay'),

    # 11.5 Runs
    path('incentive-runs/', views.RunListView.as_view(), name='run_list'),
    path('incentive-runs/new/', views.RunCreateView.as_view(), name='run_create'),
    path('incentive-runs/<int:pk>/', views.RunDetailView.as_view(), name='run_detail'),
    path('incentive-runs/<int:pk>/run/', views.RunRunView.as_view(), name='run_run'),
    path('incentive-runs/<int:pk>/discard/', views.RunDiscardView.as_view(), name='run_discard'),
    path('incentive-runs/<int:pk>/delete/', views.RunDeleteView.as_view(), name='run_delete'),
]
