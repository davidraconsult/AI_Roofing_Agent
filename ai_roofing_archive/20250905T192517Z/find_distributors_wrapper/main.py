# FastAPI Dialogflow CX webhook wrapper for "find-distributors"
# Aligns with the upstream API documented as expecting {"zip_code": "<5-digit>"}
from fastapi import FastAPI, Request
from typing import Dict, Any, List
import os, httpx
from google.oauth2.id_token import fetch_id_token
from google.auth.transport.requests import Request as GARequest

app = FastAPI()

FD_URL = os.environ.get("FIND_DISTRIBUTORS_URL")
FD_AUD = os.environ.get("FIND_DISTRIBUTORS_AUDIENCE", FD_URL)

def _id_token(aud: str) -> str:
    return fetch_id_token(GARequest(), aud)

def _param(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

@app.post("/")
async def webhook(req: Request):
    body = await req.json()
    tag = _param(body, ["fulfillmentInfo", "tag"], "")
    params = _param(body, ["sessionInfo", "parameters"], {}) or {}
    zip_code = params.get("zip-code") or params.get("zip") or params.get("zipcode")

    if tag and tag != "find_distributors":
        return {"fulfillment_response": {"messages": [{"text": {"text": [f"Unhandled tag: {tag}"]}}]}}

    if not FD_URL:
        return {"fulfillment_response": {"messages": [{"text": {"text": ["Server misconfig: FIND_DISTRIBUTORS_URL not set."]}}]}}

    if not zip_code:
        return {"fulfillment_response": {"messages": [{"text": {"text": ["What’s the job ZIP code?"]}}]}}

    headers = {"Content-Type": "application/json"}
    try:
        if FD_AUD:
            headers["Authorization"] = f"Bearer {_id_token(FD_AUD)}"
    except Exception:
        pass

    payload = {"zip_code": str(zip_code)}  # per function doc
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(FD_URL, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"fulfillment_response": {"messages": [{"text": {"text": [f"Error finding distributors: {e}"]}}]}}

    rows = data if isinstance(data, list) else data.get("results", [])
    if not rows:
        return {"fulfillment_response": {"messages": [{"text": {"text": [f"No nearby distributors found for {zip_code}."]}}]}}

    lines = [f"Here are the 3 closest distributors for {zip_code}:"]
    chips, out_params = [], {}
    for i, r in enumerate(rows[:3], start=1):
        name = r.get("name") or "Distributor"
        address = r.get("address") or ""
        miles = r.get("distance_miles") or r.get("miles")
        lines.append(f"{i}) {name} — {address}" + (f" — {float(miles):.2f} mi" if isinstance(miles, (int,float,str)) else ""))
        chips.append(name)
        out_params.update({
            f"dist_{i}_name": name,
            f"dist_{i}_address": address,
            f"dist_{i}_miles": miles
        })

    return {
        "fulfillment_response": {
            "messages": [
                {"text": {"text": ["\n".join(lines)]}},
                {"payload": {"chips": chips}}
            ]
        },
        "sessionInfo": {"parameters": out_params}
    }
