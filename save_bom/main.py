import os, json
from fastapi import FastAPI

app = FastAPI(title="save-bom")

def _safe_json(env_key: str):
    raw = os.getenv(env_key, "")
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}

CONF = _safe_json("CONFIG_JSON")
ENV = os.getenv("ENV_NAME", "dev")

@app.get("/")
def root():
    return {"ok": True, "service": "save-bom"}

@app.get("/healthz")
@app.get("/__health")
def healthz():
    envs = (CONF.get("envs") or {})
    tabs = (CONF.get("tabs") or {})
    active = envs.get(ENV, {})
    return {
        "env": ENV,
        "has_config_json": bool(CONF),
        "shared_drive_id": CONF.get("shared_drive_id"),
        "job_template_id": CONF.get("job_template_id"),
        "effective_ids": {
            "sheet_id": active.get("sheet_id"),
            "jobs_folder_id": active.get("jobs_folder_id")
        },
        "tabs": tabs
    }

# TODO: your existing POST endpoint stays as-is below
# from your_module import save_handler
# app.post("/save")(save_handler)
