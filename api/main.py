from fastapi import FastAPI

from api.routers import analytics, catalog, contracts, invoices, purchase_orders, suppliers

app = FastAPI(
    title="Procurement API",
    description="Mock procurement system API for the AI Engineering evaluation.",
    version="1.0.0",
)

app.include_router(suppliers.router)
app.include_router(purchase_orders.router)
app.include_router(invoices.router)
app.include_router(contracts.router)
app.include_router(catalog.router)
app.include_router(analytics.router)


@app.get("/")
def root():
    return {
        "service": "Procurement API",
        "version": "1.0.0",
        "docs": "/docs",
    }
