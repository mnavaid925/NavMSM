"""URL patterns for Module 8 — Inventory & Warehouse Management."""
from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),

    # 8.1  Warehouses / Zones / Bins / StockItems
    path('warehouses/', views.WarehouseListView.as_view(), name='warehouse_list'),
    path('warehouses/new/', views.WarehouseCreateView.as_view(), name='warehouse_create'),
    path('warehouses/<int:pk>/', views.WarehouseDetailView.as_view(), name='warehouse_detail'),
    path('warehouses/<int:pk>/edit/', views.WarehouseEditView.as_view(), name='warehouse_edit'),
    path('warehouses/<int:pk>/delete/', views.WarehouseDeleteView.as_view(), name='warehouse_delete'),

    path('zones/', views.WarehouseZoneListView.as_view(), name='zone_list'),
    path('zones/new/', views.WarehouseZoneCreateView.as_view(), name='zone_create'),
    path('zones/<int:pk>/edit/', views.WarehouseZoneEditView.as_view(), name='zone_edit'),
    path('zones/<int:pk>/delete/', views.WarehouseZoneDeleteView.as_view(), name='zone_delete'),

    path('bins/', views.StorageBinListView.as_view(), name='bin_list'),
    path('bins/new/', views.StorageBinCreateView.as_view(), name='bin_create'),
    path('bins/<int:pk>/edit/', views.StorageBinEditView.as_view(), name='bin_edit'),
    path('bins/<int:pk>/delete/', views.StorageBinDeleteView.as_view(), name='bin_delete'),

    path('stock/', views.StockItemListView.as_view(), name='stockitem_list'),

    # 8.2  GRN & Putaway
    path('grn/', views.GRNListView.as_view(), name='grn_list'),
    path('grn/new/', views.GRNCreateView.as_view(), name='grn_create'),
    path('grn/<int:pk>/', views.GRNDetailView.as_view(), name='grn_detail'),
    path('grn/<int:pk>/edit/', views.GRNEditView.as_view(), name='grn_edit'),
    path('grn/<int:pk>/delete/', views.GRNDeleteView.as_view(), name='grn_delete'),
    path('grn/<int:pk>/lines/new/', views.GRNLineCreateView.as_view(), name='grn_line_create'),
    path('grn/lines/<int:pk>/delete/', views.GRNLineDeleteView.as_view(), name='grn_line_delete'),
    path('grn/<int:pk>/receive/', views.GRNReceiveView.as_view(), name='grn_receive'),
    path('grn/<int:pk>/cancel/', views.GRNCancelView.as_view(), name='grn_cancel'),
    path('grn/putaway/<int:pk>/complete/', views.PutawayCompleteView.as_view(), name='putaway_complete'),

    # 8.3  Movements / Transfers / Adjustments
    path('movements/', views.StockMovementListView.as_view(), name='movement_list'),
    path('movements/new/', views.StockMovementCreateView.as_view(), name='movement_create'),
    path('movements/<int:pk>/', views.StockMovementDetailView.as_view(), name='movement_detail'),

    path('transfers/', views.TransferListView.as_view(), name='transfer_list'),
    path('transfers/new/', views.TransferCreateView.as_view(), name='transfer_create'),
    path('transfers/<int:pk>/', views.TransferDetailView.as_view(), name='transfer_detail'),
    path('transfers/<int:pk>/lines/new/', views.TransferLineCreateView.as_view(), name='transfer_line_create'),
    path('transfers/lines/<int:pk>/delete/', views.TransferLineDeleteView.as_view(), name='transfer_line_delete'),
    path('transfers/<int:pk>/ship/', views.TransferShipView.as_view(), name='transfer_ship'),
    path('transfers/<int:pk>/receive/', views.TransferReceiveView.as_view(), name='transfer_receive'),
    path('transfers/<int:pk>/cancel/', views.TransferCancelView.as_view(), name='transfer_cancel'),
    path('transfers/<int:pk>/delete/', views.TransferDeleteView.as_view(), name='transfer_delete'),

    path('adjustments/', views.AdjustmentListView.as_view(), name='adjustment_list'),
    path('adjustments/new/', views.AdjustmentCreateView.as_view(), name='adjustment_create'),
    path('adjustments/<int:pk>/', views.AdjustmentDetailView.as_view(), name='adjustment_detail'),
    path('adjustments/<int:pk>/lines/new/', views.AdjustmentLineCreateView.as_view(), name='adjustment_line_create'),
    path('adjustments/lines/<int:pk>/delete/', views.AdjustmentLineDeleteView.as_view(), name='adjustment_line_delete'),
    path('adjustments/<int:pk>/post/', views.AdjustmentPostView.as_view(), name='adjustment_post'),
    path('adjustments/<int:pk>/delete/', views.AdjustmentDeleteView.as_view(), name='adjustment_delete'),

    # 8.4  Cycle counting
    path('cycle-count/plans/', views.CycleCountPlanListView.as_view(), name='cc_plan_list'),
    path('cycle-count/plans/new/', views.CycleCountPlanCreateView.as_view(), name='cc_plan_create'),
    path('cycle-count/plans/<int:pk>/edit/', views.CycleCountPlanEditView.as_view(), name='cc_plan_edit'),
    path('cycle-count/plans/<int:pk>/delete/', views.CycleCountPlanDeleteView.as_view(), name='cc_plan_delete'),
    path('cycle-count/sheets/', views.CycleCountSheetListView.as_view(), name='cc_sheet_list'),
    path('cycle-count/sheets/new/', views.CycleCountSheetCreateView.as_view(), name='cc_sheet_create'),
    path('cycle-count/sheets/<int:pk>/', views.CycleCountSheetDetailView.as_view(), name='cc_sheet_detail'),
    path('cycle-count/sheets/<int:pk>/lines/new/', views.CycleCountLineCreateView.as_view(), name='cc_line_create'),
    path('cycle-count/lines/<int:pk>/delete/', views.CycleCountLineDeleteView.as_view(), name='cc_line_delete'),
    path('cycle-count/sheets/<int:pk>/start/', views.CycleCountStartView.as_view(), name='cc_sheet_start'),
    path('cycle-count/sheets/<int:pk>/reconcile/', views.CycleCountReconcileView.as_view(), name='cc_sheet_reconcile'),
    path('cycle-count/sheets/<int:pk>/delete/', views.CycleCountSheetDeleteView.as_view(), name='cc_sheet_delete'),

    # 8.5  Lots / Serials
    path('lots/', views.LotListView.as_view(), name='lot_list'),
    path('lots/new/', views.LotCreateView.as_view(), name='lot_create'),
    path('lots/<int:pk>/', views.LotDetailView.as_view(), name='lot_detail'),
    path('lots/<int:pk>/edit/', views.LotEditView.as_view(), name='lot_edit'),
    path('lots/<int:pk>/delete/', views.LotDeleteView.as_view(), name='lot_delete'),
    path('serials/', views.SerialListView.as_view(), name='serial_list'),
    path('serials/new/', views.SerialCreateView.as_view(), name='serial_create'),
    path('serials/<int:pk>/edit/', views.SerialEditView.as_view(), name='serial_edit'),
    path('serials/<int:pk>/delete/', views.SerialDeleteView.as_view(), name='serial_delete'),
]
