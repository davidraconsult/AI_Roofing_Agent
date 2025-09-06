import os, json
from typing import List, Optional, Literal, Dict, Any
from math import radians, sin, cos, sqrt, atan2

import gspread
from google.oauth2.service_account import Credentials
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# ---------- Models ----------
class FindRequest(BaseModel):
    zip_code: str
    distributor_type: Optional[Literal["commercial","retail","all"]] = "all"

# ---------- Health / root ----------
@app.get("/")
def root():
    return {"ok": True, "service": "find-distributors"}

@app.get("/__health")
def __health():
    return {"ok": True}

@app.get("/healthz")
def healthz():
    return __health()

# ---------- Core ----------
def _get_gspread_client():
    key_content = os.getenv("SERVICE_ACCOUNT_KEY")
    sheet_id = os.getenv("SHEET_ID")
    if not key_content:
        raise RuntimeError("Missing SERVICE_ACCOUNT_KEY env/secret")
    if not sheet_id:
        raise RuntimeError("Missing SHEET_ID env/secret")
    try:
        key_dict = json.loads(key_content)
    except Exception as e:
        raise RuntimeError("SERVICE_ACCOUNT_KEY is not valid JSON") from e

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client, sheet_id

def _haversine_miles(a: tuple, b: tuple) -> float:
    # Radius of Earth in miles
    R = 3958.8
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    hav = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2 * atan2(sqrt(hav), sqrt(1 - hav))
    return R * c

def _sheet_names_for_type(dist_type: str) -> List[str]:
    dt = (dist_type or "all").lower()
    if dt == "commercial":
        return ["GAF Distributors - Commercial"]
    if dt == "retail":
        return ["GAF Distributors - HD", "GAF Distributors - Lowes"]
    return ["GAF Distributors - Commercial", "GAF Distributors - HD", "GAF Distributors - Lowes"]

@app.post("/")
def find_distributors(req: FindRequest):
    client, sheet_id = _get_gspread_client()
    ss = client.open_by_key(sheet_id)

    # Look up the zip centroid
    zip_ws = ss.worksheet("GA Zip Codes")
    zip_rows = zip_ws.get_all_records()
    target = None
    for row in zip_rows:
        if str(row.get("ZIP Code")) == str(req.zip_code):
            try:
                target = (float(row["Latitude"]), float(row["Longitude"]))
            except Exception:
                pass
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"Zip code {req.zip_code} not found")

    # Load distributor sheets
    all_recs: List[Dict[str, Any]] = []
    for name in _sheet_names_for_type(req.distributor_type or "all"):
        ws = ss.worksheet(name)
        all_recs.extend(ws.get_all_records())

    # Compute distances
    dist_list: List[Dict[str, Any]] = []
    for rec in all_recs:
        try:
            lat = float(rec.get("Latitude (N)"))
            lon = float(rec.get("Longitude (W)"))
            miles = _haversine_miles(target, (lat, lon))
            dist_list.append({
                "name": rec.get("Distributor Name"),
                "address": f"{rec.get('Street Number & Name', rec.get('Address'))}, {rec.get('City')}",
                "distance_miles": round(miles, 2)
            })
        except Exception:
            continue

    top_three = sorted(dist_list, key=lambda r: r["distance_miles"])[:3]
    return {"zip_code": req.zip_code, "distributor_type": req.distributor_type or "all", "results": top_three}
