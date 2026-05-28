from fastapi import APIRouter, HTTPException, Query

from api.data import SUPPLIERS
from api.models import Supplier, SupplierCategory, SupplierStatus

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=list[Supplier])
def list_suppliers(
    category: SupplierCategory | None = None,
    status: SupplierStatus | None = None,
    min_rating: float | None = Query(None, ge=1, le=5),
):
    """List all suppliers, optionally filtered by category, status, or minimum rating."""
    results = SUPPLIERS
    if category:
        results = [s for s in results if s.category == category]
    if status:
        results = [s for s in results if s.status == status]
    if min_rating is not None:
        results = [s for s in results if s.rating >= min_rating]
    return results


@router.get("/{supplier_id}", response_model=Supplier)
def get_supplier(supplier_id: int):
    """Get a single supplier by ID. Returns 404 if not found."""
    for s in SUPPLIERS:
        if s.id == supplier_id:
            return s
    raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
