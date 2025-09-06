from fastapi import FastAPI, Request
from typing import Any, Dict, List
import os, httpx
from google.oauth2.id_token import fetch_id_token
from google.auth.transport.requests import Request as GARequest

app = FastAPI()

SAVE_URL = os.environ.get("SAVE_BOM_URL")
SAVE_AUD = os.environ.get("SAVE_BOM_AUDIENCE", SAVE_URL)

def _id_token(aud: str) -> str:
    return fetch_id_token(GARequest(), aud)

def _get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

@app.post("/")
async def webhook(req: Request):
    body = await req.json()
    tag = _get(body, ["fulfillmentInfo", "tag"], "")
    params = _get(body, ["sessionInfo", "parameters"], {}) or {}

    if tag and tag != "save_bom":
        return {"fulfillment_response": {"messages": [{"text": {"text": [f"Unhandled tag: {tag}"]}}]}}

    if not SAVE_URL:
        return {"fulfillment_response": {"messages": [{"text": {"text": ["Server misconfig: SAVE_BOM_URL not set."]}}]}}

    bom_items = params.get("bom_items") or []
    job_address = params.get("job_address") or params.get("address") or params.get("zip-code") or "Unknown Job"

    if not bom_items:
        return {"fulfillment_response": {"messages": [{"text": {"text": [
            "I don’t have any BOM items to save yet."
        ]}}]}}

    payload = {"job_address": job_address, "bom_items": bom_items}

    headers = {"Content-Type": "application/json"}
    try:
        if SAVE_AUD:
            headers["Authorization"] = f"Bearer {_id_token(SAVE_AUD)}"
    except Exception:
        pass

    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(SAVE_URL, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"fulfillment_response": {"messages": [{"text": {"text": [f"Save failed: {e}"]}}]}}

    saved = data.get("saved") or 0
    msg = f"Saved {saved} item(s) to Generated BOMs for '{job_address}'."
    return {"fulfillment_response": {"messages": [{"text": {"text": [msg]}}]}}
