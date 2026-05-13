"""Module 17 - Sales & Customer Order Management - signal handlers.

17.1 has no cross-module signals - they are introduced in:
    17.2  SalesOrder.status='confirmed' -> draft pps.ProductionOrder
                                            (per-line is_make_to_order flag)
    17.4  Shipment.status='delivered'   -> inventory.StockMovement(shipment_out)
          Shipment.pre_delete            -> reverse the shipment_out movements
    17.4  SalesInvoice.status='paid'     -> Customer.credit_used denorm down

This module is loaded by SalesConfig.ready() so the file must exist even
when empty.
"""
