from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from api.data import CONTRACTS
from api.models import Contract, ContractStatus

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("", response_model=list[Contract])
def list_contracts(
    supplier_id: int | None = None,
    status: ContractStatus | None = None,
    expiring_within_days: int | None = Query(
        None, ge=1, description="Contracts expiring within N days from today"
    ),
):
    results = CONTRACTS
    if supplier_id is not None:
        results = [c for c in results if c.supplier_id == supplier_id]
    if status:
        results = [c for c in results if c.status == status]
    if expiring_within_days is not None:
        cutoff = date.today() + timedelta(days=expiring_within_days)
        results = [c for c in results if c.end_date <= cutoff and c.status != ContractStatus.EXPIRED]
    return results


@router.get("/{contract_id}", response_model=Contract)
def get_contract(contract_id: int):
    for c in CONTRACTS:
        if c.id == contract_id:
            return c
    raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")
