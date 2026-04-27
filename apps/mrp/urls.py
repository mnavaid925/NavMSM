from django.urls import path

from . import views

app_name = 'mrp'

urlpatterns = [
    path('', views.MRPIndexView.as_view(), name='index'),

    # ---- 5.1  Forecast Models ----
    path('forecast-models/', views.ForecastModelListView.as_view(), name='forecast_model_list'),
    path('forecast-models/new/', views.ForecastModelCreateView.as_view(), name='forecast_model_create'),
    path('forecast-models/<int:pk>/', views.ForecastModelDetailView.as_view(), name='forecast_model_detail'),
    path('forecast-models/<int:pk>/edit/', views.ForecastModelEditView.as_view(), name='forecast_model_edit'),
    path('forecast-models/<int:pk>/delete/', views.ForecastModelDeleteView.as_view(), name='forecast_model_delete'),
    path('forecast-models/<int:pk>/run/', views.ForecastModelRunView.as_view(), name='forecast_model_run'),

    # ---- 5.1  Seasonality Profiles ----
    path('seasonality/', views.SeasonalityListView.as_view(), name='seasonality_list'),
    path('seasonality/new/', views.SeasonalityCreateView.as_view(), name='seasonality_create'),
    path('seasonality/<int:pk>/edit/', views.SeasonalityEditView.as_view(), name='seasonality_edit'),
    path('seasonality/<int:pk>/delete/', views.SeasonalityDeleteView.as_view(), name='seasonality_delete'),

    # ---- 5.1  Forecast Runs ----
    path('forecast-runs/', views.ForecastRunListView.as_view(), name='forecast_run_list'),
    path('forecast-runs/<int:pk>/', views.ForecastRunDetailView.as_view(), name='forecast_run_detail'),
    path('forecast-runs/<int:pk>/delete/', views.ForecastRunDeleteView.as_view(), name='forecast_run_delete'),

    # ---- 5.2  Inventory Snapshots ----
    path('inventory/', views.InventoryListView.as_view(), name='inventory_list'),
    path('inventory/new/', views.InventoryCreateView.as_view(), name='inventory_create'),
    path('inventory/<int:pk>/', views.InventoryDetailView.as_view(), name='inventory_detail'),
    path('inventory/<int:pk>/edit/', views.InventoryEditView.as_view(), name='inventory_edit'),
    path('inventory/<int:pk>/delete/', views.InventoryDeleteView.as_view(), name='inventory_delete'),

    # ---- 5.2  Scheduled Receipts ----
    path('receipts/', views.ReceiptListView.as_view(), name='receipt_list'),
    path('receipts/new/', views.ReceiptCreateView.as_view(), name='receipt_create'),
    path('receipts/<int:pk>/edit/', views.ReceiptEditView.as_view(), name='receipt_edit'),
    path('receipts/<int:pk>/delete/', views.ReceiptDeleteView.as_view(), name='receipt_delete'),

    # ---- 5.2  MRP Calculations ----
    path('calculations/', views.CalculationListView.as_view(), name='calculation_list'),
    path('calculations/<int:pk>/', views.CalculationDetailView.as_view(), name='calculation_detail'),
    path('calculations/<int:pk>/delete/', views.CalculationDeleteView.as_view(), name='calculation_delete'),

    # ---- 5.5  MRP Runs ----
    path('runs/', views.RunListView.as_view(), name='run_list'),
    path('runs/new/', views.RunCreateView.as_view(), name='run_create'),
    path('runs/<int:pk>/', views.RunDetailView.as_view(), name='run_detail'),
    path('runs/<int:pk>/start/', views.RunStartView.as_view(), name='run_start'),
    path('runs/<int:pk>/apply/', views.RunApplyView.as_view(), name='run_apply'),
    path('runs/<int:pk>/discard/', views.RunDiscardView.as_view(), name='run_discard'),
    path('runs/<int:pk>/delete/', views.RunDeleteView.as_view(), name='run_delete'),

    # ---- 5.3  Purchase Requisitions ----
    path('requisitions/', views.PRListView.as_view(), name='pr_list'),
    path('requisitions/<int:pk>/', views.PRDetailView.as_view(), name='pr_detail'),
    path('requisitions/<int:pk>/edit/', views.PREditView.as_view(), name='pr_edit'),
    path('requisitions/<int:pk>/approve/', views.PRApproveView.as_view(), name='pr_approve'),
    path('requisitions/<int:pk>/cancel/', views.PRCancelView.as_view(), name='pr_cancel'),
    path('requisitions/<int:pk>/delete/', views.PRDeleteView.as_view(), name='pr_delete'),

    # ---- 5.4  Exceptions ----
    path('exceptions/', views.ExceptionListView.as_view(), name='exception_list'),
    path('exceptions/<int:pk>/', views.ExceptionDetailView.as_view(), name='exception_detail'),
    path('exceptions/<int:pk>/acknowledge/', views.ExceptionAckView.as_view(), name='exception_acknowledge'),
    path('exceptions/<int:pk>/resolve/', views.ExceptionResolveView.as_view(), name='exception_resolve'),
    path('exceptions/<int:pk>/ignore/', views.ExceptionIgnoreView.as_view(), name='exception_ignore'),
    path('exceptions/<int:pk>/delete/', views.ExceptionDeleteView.as_view(), name='exception_delete'),
]
