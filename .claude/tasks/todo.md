# Module 8 — Inventory & Warehouse Management — Implementation Plan

> **Status:** APPROVED 2026-05-03 — implementation in progress.
>
> **User decisions:**
> 1. Build all 5 sub-modules in one pass.
> 2. Include full pytest test suite.
> 3. `mes.ProductionReport` auto-emits `StockMovement` rows (signal-based).
> 4. Going with `Product.tracking_mode` enum (cleaner long-term).

## App layout (`apps/inventory/`)

```
apps/inventory/
├── __init__.py
├── apps.py
├── models.py
├── admin.py
├── forms.py
├── views.py
├── urls.py
├── signals.py
├── services/
│   ├── __init__.py
│   ├── grn.py             # GRN posting + putaway suggestions
│   ├── allocation.py      # FIFO/FEFO lot picking (pure)
│   ├── movements.py       # post_movement() — atomic stock txn writer
│   └── cycle_count.py     # ABC classification + variance math (pure)
├── migrations/__init__.py
├── management/
│   ├── __init__.py
│   └── commands/
│       ├── __init__.py
│       └── seed_inventory.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_services.py
    ├── test_signals.py
    ├── test_forms.py
    ├── test_views.py
    └── test_security.py
```

## Models (16 total)

### 8.1 Multi-Warehouse Inventory
- [ ] `Warehouse` — code unique per tenant, address, manager FK, is_active, default flag
- [ ] `WarehouseZone` — FK warehouse, code, zone_type (`receiving / storage / picking / shipping / quarantine`), unique per warehouse
- [ ] `StorageBin` — FK zone, code unique per warehouse, bin_type, capacity, is_blocked
- [ ] `StockItem` — `(tenant, product, bin, lot, serial)` unique row; `qty_on_hand`, `qty_reserved`, `qty_available` property. Auto-maintained by `post_movement()`.

### 8.2 Goods Receipt & Putaway
- [ ] `GoodsReceiptNote` — auto `GRN-00001`, supplier_name (free-text), optional FK `qms.IncomingInspection`, status `draft → received → putaway_pending → completed / cancelled`
- [ ] `GRNLine` — FK GRN + product, expected_qty, received_qty, lot_number, serial_number, FK to receiving zone
- [ ] `PutawayTask` — FK GRN line, suggested_bin, actual_bin, status `pending → in_progress → completed`, `strategy` enum (`fixed_bin / nearest_empty / abc_zone / directed`)

### 8.3 Inventory Movements & Transfers
- [ ] `StockMovement` — append-only ledger; `movement_type` (`receipt / issue / transfer / adjustment / production_in / production_out / scrap / cycle_count`), `from_bin` / `to_bin` (one nullable), `qty`, FK `lot`, FK `serial`, `reason`, `reference` text, optional FK `mes.ProductionReport`, optional FK `qms.IncomingInspection`
- [ ] `StockTransfer` — header for inter-warehouse moves; auto `TRF-00001`; status `draft → in_transit → received / cancelled`
- [ ] `StockTransferLine` — FK transfer + product + lot + serial, qty, source_bin, dest_bin
- [ ] `StockAdjustment` — header for variance corrections; auto `ADJ-00001`; reason required; admin-only
- [ ] `StockAdjustmentLine` — FK adjustment + bin + product + lot/serial, system_qty, actual_qty, variance

### 8.4 Cycle Counting & Physical Audit
- [ ] `CycleCountPlan` — frequency (`daily / weekly / monthly / quarterly`), abc_class filter, scope_warehouse FK
- [ ] `CycleCountSheet` — auto `CC-00001`, FK warehouse, status `draft → counting → reconciled / cancelled`
- [ ] `CycleCountLine` — FK bin + product + lot + serial, system_qty, counted_qty, variance, recount_required

### 8.5 Lot / Serial / Batch Tracking
- [ ] `Lot` — `(tenant, product, lot_number)` unique; manufactured_date, expiry_date, supplier, COA reference, status (`active / quarantine / expired / consumed`)
- [ ] `SerialNumber` — `(tenant, product, serial_number)` unique; status `available / reserved / shipped / scrapped`; FK current StockItem (set by movement signals)

## Cross-module integration

- [ ] `apps.plm.Product` migration: add `tracking_mode` field (`none / lot / serial / lot_and_serial`) — default `none`
- [ ] `apps/inventory/signals.py` listens on `mes.ProductionReport.post_save` → emits `StockMovement(production_in)` for `good_qty`. Skip silently if product has no default warehouse/bin (don't break MES floor).
- [ ] `apps/inventory/signals.py` listens on `mes.ProductionReport.post_delete` → emits reversing movement
- [ ] `apps.qms.IncomingInspection`: keep one-way coupling — GRN can optionally reference an IQC inspection; QMS itself unchanged

## RBAC

| Surface | Required role |
|---|---|
| Dashboard, list pages, detail pages | Authenticated tenant user |
| File a GRN, complete a putaway task, count a cycle-count line, post a transfer | Tenant user (operator) |
| Warehouse / zone / bin CRUD, stock adjustment posting, putaway strategy edits, cycle count plan CRUD, manual lot creation, transfer cancel, GRN cancel | Tenant admin |

## Audit signals
- `pre_save` + `post_save` on `GoodsReceiptNote`, `StockTransfer`, `CycleCountSheet`, `Warehouse`
- `post_save` on `StockAdjustment` (creation only)

## Seed data (idempotent, per tenant)
- 2 warehouses (`MAIN`, `SEC`) × 3 zones each × 4 bins each = 24 bins
- 8 `StockItem` rows for finished-goods + 4 components
- 1 completed GRN with 3 lines + putaway tasks
- 6 movement rows spanning 3 movement types
- 1 cycle count sheet with 4 lines (1 with variance)
- 4 lots (one expiring in 15 days), 6 serial numbers on a finished good

## Tests target ≥70 tests
- `test_models.py` — unique_together, validators, str repr, computed `qty_available`
- `test_services.py` — `post_movement` atomicity, FIFO/FEFO allocation, ABC math, putaway strategies
- `test_signals.py` — MES `ProductionReport` → auto `StockMovement`; reverse on delete; audit log emission
- `test_forms.py` — manual unique_together, decimal bounds
- `test_views.py` — full CRUD smoke + workflow transitions
- `test_security.py` — RBAC matrix; multi-tenant IDOR; CSRF

## README updates (mandatory same session)
- Strike #8 in Roadmap → ✅ shipped
- Add `apps/inventory/` block to Project Structure
- Add ~30 routes to Screenshots/UI Tour
- Add Module 8 narrative section
- Add Module 8 line to Seeded Demo Data
- Add `seed_inventory` to Management Commands table
- Update intro paragraph (Phase 1 includes Module 8)
- Update Highlights bullet

## Deferred (out of scope)
- Procurement integration — Module 9 will replace `supplier_name` free-text
- Real-time barcode/RFID hardware integration
- WMS slot optimization (genetic / ILP)
- Wave / batch picking

## Commit discipline
- ONE FILE PER COMMIT, PowerShell `;` syntax
- README update in same batch
- Hand all snippets at the end — user runs commits themselves

## Implementation order
1. Scaffold (`__init__.py`, `apps.py`, `migrations/__init__.py`, `management/__init__.py`)
2. PLM `tracking_mode` migration
3. `models.py` (largest file)
4. `admin.py`
5. `services/` (4 files)
6. `signals.py`
7. `forms.py`
8. `views.py`
9. `urls.py`
10. Settings + root URL include
11. Migrations + manual migration check
12. Templates (~30+ files)
13. Sidebar partial update
14. `seed_inventory` command + orchestrator wiring
15. Tests (7 files)
16. README updates
17. Hand commit snippets to user
