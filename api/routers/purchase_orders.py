from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.data import PURCHASE_ORDERS, SUPPLIERS
from api.models import LineItem, POStatus, PurchaseOrder

router = APIRouter(prefix="/purchase-orders", tags=["purchase_orders"])


@router.get("", response_model=list[PurchaseOrder])
def list_purchase_orders(
    supplier_id: int | None = None,
    status: POStatus | None = None,
    created_after: date | None = None,
    created_before: date | None = None,
    min_amount: float | None = Query(None, ge=0),
):
    results = PURCHASE_ORDERS
    if supplier_id is not None:
        results = [po for po in results if po.supplier_id == supplier_id]
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
def get_purchase_order(po_id: int):
    for po in PURCHASE_ORDERS:
        if po.id == po_id:
            return po
    raise HTTPException(status_code=404, detail=f"Purchase order {po_id} not found")


class CreatePORequest(BaseModel):
    supplier_id: int
    line_items: list[LineItem]
    currency: str = "USD"
    delivery_date: date | None = None


@router.post("", response_model=PurchaseOrder, status_code=201)
def create_purchase_order(req: CreatePORequest):
    if not any(s.id == req.supplier_id for s in SUPPLIERS):
        raise HTTPException(status_code=400, detail=f"Supplier {req.supplier_id} not found")

    total = sum(item.quantity * item.unit_price for item in req.line_items)
    new_id = max(po.id for po in PURCHASE_ORDERS) + 1

    po = PurchaseOrder(
        id=new_id,
        supplier_id=req.supplier_id,
        line_items=req.line_items,
        total_amount=total,
        currency=req.currency,
        status=POStatus.DRAFT,
        created_date=date.today(),
        delivery_date=req.delivery_date,
    )
    PURCHASE_ORDERS.append(po)
    return po


class UpdatePORequest(BaseModel):
    status: POStatus


@router.patch("/{po_id}", response_model=PurchaseOrder)
def update_purchase_order(po_id: int, req: UpdatePORequest):
    for i, po in enumerate(PURCHASE_ORDERS):
        if po.id == po_id:
            updated = po.model_copy(update={"status": req.status})
            PURCHASE_ORDERS[i] = updated
            return updated
    raise HTTPException(status_code=404, detail=f"Purchase order {po_id} not found")
