# FastAPI Dialogflow CX webhook wrapper for "calculate-materials"
# - Accepts report_url (https) or report_gcs_uri (gs://)
# - Downloads bytes, posts as multipart/form-data (field "file") to your calculatematerials backend
# - Returns a CX-formatted message and stores bom_items (+ zip-code/job_address, if returned) in session

from fastapi import FastAPI, Request
from typing import Any, Dict, List
import os, httpx
from google.oauth2.id_token import fetch_id_token
from google.auth.transport.requests import Request as GARequest
from google.cloud import storage

app = FastAPI()

CM_URL = os.environ.get("CALCULATE_MATERIALS_URL")
CM_AUD = os.environ.get("CALCULATE_MATERIALS_AUDIENCE", CM_URL)

def _id_token(aud: str) -> str:
    return fetch_id_token(GARequest(), aud)

def _get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def _load_pdf_bytes(report_url: str = None, gcs_uri: str = None) -> bytes:
    if report_url:
        with httpx.Client(timeout=60.0) as client:
            r = client.get(report_url)
            r.raise_for_status()
            return r.content
    if gcs_uri and gcs_uri.startswith("gs://"):
        _, path = gcs_uri.split("gs://", 1)
        bucket_name, *rest = path.split("/", 1)
        blob_name = rest[0] if rest else ""
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(blob_name)
        return blob.download_as_bytes()
    raise ValueError("No valid report source provided (need https URL or gs:// URI).")

@app.post("/")
async def webhook(req: Request):
    body = await req.json()
    tag = _get(body, ["fulfillmentInfo", "tag"], "")
    params = _get(body, ["sessionInfo", "parameters"], {}) or {}

    # Only handle our tag
    if tag and tag != "calculate_materials":
        return {"fulfillment_response": {"messages": [{"text": {"text": [f"Unhandled tag: {tag}"]}}]}}
    if not CM_URL:
        return {"fulfillment_response": {"messages": [{"text": {"text": ["Server misconfig: CALCULATE_MATERIALS_URL not set."]}}]}}

    report_url = params.get("report_url") or params.get("pdf_url")
    report_gcs = params.get("report_gcs_uri")

    if not (report_url or report_gcs):
        return {"fulfillment_response": {"messages": [{"text": {"text": [
            "Please paste your GAF QuickMeasure PDF link (https or gs://)."
        ]}}]}}

    # Download PDF
    try:
        pdf_bytes = _load_pdf_bytes(report_url=report_url, gcs_uri=report_gcs)
    except Exception as e:
        return {"fulfillment_response": {"messages": [{"text": {"text": [f"Couldn’t read the PDF: {e}"]}}]}}

    # Send multipart/form-data to backend
    files = {"file": ("quickmeasure.pdf", pdf_bytes, "application/pdf")}
    headers = {}
    try:
        if CM_AUD:
            headers["Authorization"] = f"Bearer {_id_token(CM_AUD)}"
    except Exception:
        # running locally without metadata server
        pass

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(CM_URL, files=files, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"fulfillment_response": {"messages": [{"text": {"text": [f"Error creating BOM: {e}"]}}]}}

    # Parse response
    items = None
    job_zip = None
    job_addr = None

    if isinstance(data, dict):
        items = data.get("calculated_bom") or data.get("bom")
        # NEW: capture job info if backend returns it
        job_zip = data.get("zip_code") or data.get("job_zip")
        job_addr = data.get("job_address") or data.get("address")

    if not items and isinstance(data, list):
        items = data

    if not items:
        return {"fulfillment_response": {"messages": [{"text": {"text": [
            "I couldn’t create a BOM from that PDF. Can you confirm the file?"
        ]}}]}}

    # Build user-facing message
    lines = ["Here’s your draft Bill of Materials:"]
    for it in items:
        name = it.get("Product") or it.get("product") or it.get("name") or "Item"
        qty  = it.get("Quantity") or it.get("qty") or it.get("quantity")
        unit = it.get("Unit") or it.get("unit") or ""
        color = it.get("Color") or it.get("color")
        label = f"• {name}"
        if color: label += f" ({color})"
        if qty is not None: label += f": {qty} {unit}".rstrip()
        lines.append(label)

    # Session params for downstream pages
    session_params: Dict[str, Any] = {"bom_items": items}
    if job_zip:  session_params["zip-code"] = str(job_zip)
    if job_addr: session_params["job_address"] = job_addr

    return {
        "fulfillment_response": {"messages": [{"text": {"text": ["\n".join(lines)]}}]},
        "sessionInfo": {"parameters": session_params}
    }
