# Sales module — D-01 → D-15 remediation plan

Source: defects surfaced from the manual test plan at [.claude/manual-tests/sales-manual-test.md](.claude/manual-tests/sales-manual-test.md).

## Strategy

- No DB schema changes (no migrations). Every fix is logic-only or template-only.
- One fix can span multiple files; one file = one commit per CLAUDE.md.
- README.md must be updated in the same session.

## Defect-to-file matrix

| ID | File(s) | Approach |
|---|---|---|
| D-01 line_no corruption | `apps/sales/models.py` | Change `SalesOrderLine.save()` guard to `if self._state.adding and not self.line_no` so the bump only happens on first insert. |
| D-02 unique_together 500 | `apps/sales/forms.py` | Add `clean()` to `CustomerCategoryForm` (tenant+name+parent) and `PriceListItemForm` (price_list+product+min_qty) to raise `forms.ValidationError` with a friendly message. |
| D-03 over-shipping | `apps/sales/forms.py` | Add `clean()` to `ShipmentLineForm` that caps `qty_to_ship` at `order_line.qty_ordered - order_line.qty_shipped + (instance.qty_to_ship if editing else 0)`. |
| D-04 PL effective_to | `apps/sales/forms.py` | Add `clean()` to `PriceListForm` and `PriceListItemForm` to require `to >= from` when both set. |
| D-05 invoice due_date | `apps/sales/forms.py` | Add `clean()` to `SalesInvoiceForm` requiring `due_date >= invoice_date`. |
| D-06 POD validator | `apps/sales/forms.py` | Replace `_validate_pod_image` with two validators: signature (5 MB cap) + photo (25 MB cap); wire `clean_received_by_signature` to the new signature validator. |
| D-07 draft→paid bypass | `apps/sales/services/invoicing.py` + `apps/sales/views.py` | `mark_invoice_paid` now rejects status not in (`issued`, `overdue`). Add new `issue_invoice(invoice, performed_by)` service that flips status AND atomically adds grand_total to customer.credit_used via conditional UPDATE WHERE status='draft'. Update `invoice_issue_view` to call it. |
| D-08 subtotal naming | `apps/sales/models.py` | Add `help_text` to `SalesOrder.subtotal` + `SalesInvoice.subtotal` explaining "gross / pre-discount" semantics. |
| D-09 doc delete order | `apps/sales/views.py` | Wrap row delete in `transaction.atomic()`, schedule `obj.file.delete(save=False)` via `transaction.on_commit(...)`. |
| D-10 toggle_active button | `apps/sales/views.py` | Refuse toggle when status is `on_hold` or `blacklisted`; show error toast directing user to use the Edit form for those transitions. |
| D-11 submit with zero lines | `apps/sales/services/workflow.py` | `submit_sales_order` raises ValueError if `sales_order.lines.count() == 0`. |
| D-12 numbering race | `apps/sales/models.py` | Replace duplicated auto-code blocks in 9 models with calls to existing `services.numbering.next_code()`. Behaviour identical; less drift. |
| D-13 credit_used drift | `apps/sales/signals.py` + `apps/sales/services/invoicing.py` | Remove the non-idempotent `_invoice_paid_drop_credit_used` signal. Both increment (issue) and decrement (paid) now live in service functions inside a `transaction.atomic()` block, guarded by a conditional UPDATE WHERE status='X' so they only run on actual transitions. |
| D-14 missing Delete in list Actions | 4 list templates | Add a status-gated Delete button (POST form, `confirm()` JS) next to the Edit button in each Actions column. |
| D-15 multiple is_default PriceList | `apps/sales/forms.py` | Override `PriceListForm.save()` to clear `is_default=False` on every other PriceList in the tenant when the current row toggles `is_default=True`. |

## Commit order (one file per commit)

1. `apps/sales/services/numbering.py` — no change (already exists; reuse only).
2. `apps/sales/models.py` — D-01, D-08, D-12, D-15 helper.
3. `apps/sales/forms.py` — D-02, D-03, D-04, D-05, D-06, D-15 save override.
4. `apps/sales/services/invoicing.py` — D-07, D-13 service ops.
5. `apps/sales/services/workflow.py` — D-11.
6. `apps/sales/signals.py` — D-13 signal removal.
7. `apps/sales/views.py` — D-07 wire, D-09 atomic, D-10 guard.
8. `templates/sales/shipments/list.html` — D-14.
9. `templates/sales/invoices/list.html` — D-14.
10. `templates/sales/categories/list.html` — D-14.
11. `templates/sales/pricelists/list.html` — D-14.
12. `README.md` — defect remediation log entry.

## Verification

- `python manage.py check` returns no errors.
- `python manage.py makemigrations sales --dry-run` reports "No changes detected".
- Spot-check: create a SO line, edit line #1 — line_no remains 1 (not 4).
- Spot-check: try mark-paid on a draft invoice — error toast instead of silent transition.

## Review section (filled after implementation)

- Notes on any deviation from the plan or unexpected issues are appended here.
