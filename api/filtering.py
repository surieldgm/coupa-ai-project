"""Shared supplier filtering logic for all resource endpoints."""


def filter_by_supplier(collection, supplier_id: int | None):
    """Filter a collection of resources by supplier_id.

    - If supplier_id is None → return all items (no filtering)
    - If supplier_id doesn't match any items → return empty list
    - If supplier_id matches → return only those items
    """
    if supplier_id is None:
        return collection
    return [item for item in collection if item.supplier_id == supplier_id]
