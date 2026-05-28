from datetime import date

from fastapi import APIRouter, HTTPException, Query

from api.data import PURCHASE_ORDERS
from api.filtering import filter_by_supplier
from api.models import POStatus, PurchaseOrder

router = APIRouter(prefix="/purchase-orders", tags=["purchase_orders"])


@router.get("", response_model=list[PurchaseOrder])
def list_purchase_orders(
    supplier_id: int | None = None,
    status: POStatus | None = None,
    created_after: date | None = None,
    created_before: date | None = None,
    min_amount: float | None = Query(None, ge=0),
):
    """List all purchase orders, optionally filtered by supplier, status, date range, or amount."""
    results = filter_by_supplier(PURCHASE_ORDERS, supplier_id)
    if status:
        results = [po for po in results if po.status == status]
    if created_after:
        results = [po for po in results if po.created_date >= created_after]
    if created_before:
        results = [po for po in results if po.created_date <= created_before]
    if min_amount is not None:
        results = [po for po in results if po.total_amount >= min_amount]
    return results


@router.get("/{po_id}", response_model=PurchaseOrder)
def get_purchase_order(po_id: int, supplier_id: int | None = None):
    """Get a single purchase order by ID. Returns 404 if not found or doesn't belong to the given supplier."""
    results = filter_by_supplier(PURCHASE_ORDERS, supplier_id)
    po = next((p for p in results if p.id == po_id), None)
    if po is None:
        raise HTTPException(status_code=404, detail=f"Purchase order {po_id} not found")
    return po



@router.post("/{po_id}/acknowledge", response_model=PurchaseOrder)
def acknowledge_purchase_order(po_id: int, supplier_id: int | None = None):
    """Supplier acknowledges a submitted PO. Transitions status from 'submitted' to 'acknowledged'."""
    for i, po in enumerate(PURCHASE_ORDERS):
        if po.id == po_id:
            if supplier_id is not None and po.supplier_id != supplier_id:
                break
            if po.status != POStatus.SUBMITTED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot acknowledge PO {po_id}: status is '{po.status.value}', must be 'submitted'",
                )
            updated = po.model_copy(update={"status": POStatus.ACKNOWLEDGED})
            PURCHASE_ORDERS[i] = updated
            return updated
    raise HTTPException(status_code=404, detail=f"Purchase order {po_id} not found")
