import logging

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.webhook import router as webhook_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="AI Agent Convo — WhatsApp Clinic Assistant")

app.include_router(webhook_router)
app.include_router(admin_router)


@app.get("/health")
def health():
    return {"status": "ok"}
