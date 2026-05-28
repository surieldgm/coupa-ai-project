from fastapi import APIRouter, HTTPException, Query

from api.data import CATALOG_ITEMS
from api.filtering import filter_by_supplier
from api.models import CatalogItem

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=list[CatalogItem])
def search_catalog(
    query: str | None = Query(None, description="Search name and description"),
    category: str | None = None,
    supplier_id: int | None = None,
    max_price: float | None = Query(None, ge=0),
    in_stock: bool | None = None,
):
    """Search catalog items by keyword, category, supplier, price, or availability."""
    results = filter_by_supplier(CATALOG_ITEMS, supplier_id)
    if query:
        q = query.lower()
        results = [
            item for item in results
            if q in item.name.lower() or q in item.description.lower()
        ]
    if category:
        results = [item for item in results if item.category == category]
    if max_price is not None:
        results = [item for item in results if item.unit_price <= max_price]
    if in_stock is not None:
        results = [item for item in results if item.in_stock == in_stock]
    return results


@router.get("/{item_id}", response_model=CatalogItem)
def get_catalog_item(item_id: int, supplier_id: int | None = None):
    """Get a single catalog item by ID. Returns 404 if not found or doesn't belong to the given supplier."""
    results = filter_by_supplier(CATALOG_ITEMS, supplier_id)
    item = next((i for i in results if i.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Catalog item {item_id} not found")
    return item
