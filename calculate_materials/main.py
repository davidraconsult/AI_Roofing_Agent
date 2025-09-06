import os, json
from fastapi import FastAPI, Request

app = FastAPI(title="calculate-materials")

@app.get("/")
def root():
    return {"ok": True, "service": "calculate-materials"}

def _safe_json(env_key: str):
    raw = os.getenv(env_key, "")
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}

CALC = _safe_json("CALC_CONFIG_JSON")
DEFAULTS = (CALC.get("defaults") or {})
TABS = (CALC.get("tabs") or {})
CAT_SHEET_ID = CALC.get("catalog_rules_sheet_id")

@app.get("/healthz")
@app.get("/__health")  # alias to avoid any edge caching / reserved-path oddities
def healthz():
    env = os.getenv("ENV_NAME", "dev")
    return {
        "env": env,
        "has_calc_config": bool(CALC),
        "catalog_rules_sheet_id": CAT_SHEET_ID,
        "tabs": TABS
    }

@app.post("/calculate")
async def calculate(req: Request):
    payload = await req.json()
    selections = payload.get("selections") or {}
    sys_sel = selections.get("system_id", {})
    color_sel = selections.get("shingle_color", {})

    system_id = sys_sel.get("value") or DEFAULTS.get("system_id") or "hdz_basic_static"
    shingle_color = color_sel.get("value") or DEFAULTS.get("shingle_color") or "Charcoal"
    waste_qc = DEFAULTS.get("waste_qc_pct", 3.0)

    geometry = payload.get("geometry") or {}
    linears = payload.get("linears") or {}
    openings = payload.get("openings") or {}

    ventilation_raw = [{"key": k, "value": v, "source": "input"} for k, v in openings.items()]

    return {
        "job_address": payload.get("job_address"),
        "zip_code": payload.get("zip_code"),
        "selections": {
            "system_id": {"value": system_id, "source": sys_sel.get("source","default")},
            "shingle_color": {"value": shingle_color, "source": color_sel.get("source","default")}
        },
        "geometry": geometry,
        "linears": linears,
        "openings": openings,
        "ventilation_raw": ventilation_raw,
        "bom_items": [],
        "waste_pct_final": float(waste_qc)
    }
