#!/usr/bin/env python3
"""
Patches main.py for AI Roofing Agent save-bom service.

- Adds helpers: _slug(), _parse_city_state(), _seed_headers()
- Uses _slug() for job_id (no commas)
- Seeds headers for Summary/Geometry/Linears/Openings
- Summary: adds city/state/status/created_by; created_at in ET
- Master log: timestamp_local (ET) + city/state/status/created_by columns
"""
import re, sys, datetime, json
from pathlib import Path

SRC = Path("main.py")
if not SRC.exists():
    sys.exit("ERROR: main.py not found in current directory")

orig = SRC.read_text()
text = orig
changed = []

def ensure_import(line: str):
    global text, changed
    if re.search(rf'^\s*{re.escape(line.strip())}\s*$', text, re.M):
        return
    imports = list(re.finditer(r'^(?:from\s+\S+\s+import[^\n]*|import[^\n]*)\n', text, re.M))
    insert_at = imports[-1].end() if imports else 0
    text = text[:insert_at] + line.rstrip() + "\n" + text[insert_at:]
    changed.append(f"+ import: {line.strip()}")

def ensure_helper(name: str, code: str):
    global text, changed
    if re.search(rf'\bdef\s+{name}\s*\(', text):
        return
    m = re.search(r'^\s*app\s*=\s*FastAPI\(\)', text, re.M)
    insert_at = m.start() if m else 0
    text = text[:insert_at] + "\n" + code.rstrip() + "\n\n" + text[insert_at:]
    changed.append(f"+ helper: {name}()")

def insert_before(pattern: str, insert: str, label: str):
    global text, changed
    m = re.search(pattern, text)
    if not m:
        return
    context = text[max(0, m.start()-300):m.start()]
    if insert.strip() in context:
        return
    line_start = text.rfind("\n", 0, m.start()) + 1
    text_new = text[:line_start] + insert.rstrip() + "\n" + text[line_start:]
    if text_new != text:
        text = text_new
        changed.append(f"+ {label}")

def replace_block(start_pat: str, end_pat: str, new_block: str, label: str):
    global text, changed
    ms = re.search(start_pat, text, re.M)
    if not ms:
        return
    me = re.search(end_pat, text[ms.end():], re.M)
    if not me:
        return
    a = ms.start()
    b = ms.end() + me.start()
    text_new = text[:a] + new_block.rstrip() + text[b:]
    if text_new != text:
        text = text_new
        changed.append(f"~ {label}")

def patch_job_slug():
    global text, changed
    f = re.search(r'def\s+_create_job_artifacts\s*\(', text)
    if not f:
        return
    body = text[f.end(): f.end()+6000]
    m = re.search(r'^\s*job_slug\s*=\s*.*$', body, re.M)
    if not m:  # broader fallback
        m = re.search(r'^\s*(addr\s*=.*\n)?\s*(zipc\s*=.*\n)?\s*(base\s*=.*\n)?\s*job_slug\s*=\s*.*$', body, re.M)
    if not m:
        return
    indent = re.match(r'^(\s*)', m.group(0)).group(1)
    new_block = (
        f"{indent}addr = payload.get(\"job_address\", \"\") or \"\"\n"
        f"{indent}zipc = str(payload.get(\"zip_code\", \"\") or \"\").strip()\n"
        f"{indent}base = datetime.datetime.utcnow().strftime(\"%Y%m%d\") + (f\"-{{zipc}}\" if zipc else \"\")\n"
        f"{indent}job_slug = _slug(addr) or base\n"
    )
    body_new = body[:m.start()] + new_block + body[m.end():]
    text_new = text[:f.end()] + body_new + text[f.end()+len(body):]
    if text_new != text:
        text = text_new
        changed.append("~ job_slug -> _slug(addr)")

# --- ensure imports
ensure_import("import re")
ensure_import("from zoneinfo import ZoneInfo")

# --- helpers
ensure_helper("_slug", r'''
def _slug(text: str) -> str:
    """Remove commas/punct, collapse spaces/dashes to underscores."""
    if not text:
        return ""
    s = text.replace(",", " ")
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s-]+", "_", s).strip("_")
    return s
''')

ensure_helper("_parse_city_state", r'''
def _parse_city_state(addr: str) -> tuple[str, str]:
    """Parse "..., City, ST ZIP" → ("City","ST") best-effort."""
    if not addr:
        return "", ""
    m = re.search(r",\s*([^,]+?),\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\s*$", addr)
    if not m:
        return "", ""
    return m.group(1).strip(), m.group(2).strip()
''')

ensure_helper("_seed_headers", r'''
def _seed_headers(ws, headers: list[str]) -> None:
    """Ensure header row has the required headers (append missing)."""
    try:
        current = ws.row_values(1)
    except Exception:
        current = []
    have = [h.strip() for h in current if h and h.strip()]
    to_add = [h for h in headers if h not in have]
    if not to_add:
        return
    ws.update("A1", [have + to_add])
''')

# --- job_slug use slug
patch_job_slug()

# --- seed tab headers
insert_before(r'_upsert_row_by_header\(\s*sh\.worksheet\("Summary"\)',
              '_seed_headers(sh.worksheet("Summary"), ["job_id","created_at","job_address","city","state","zip_code","system_id","shingle_color","waste_pct_final","distributor_type","report_url","archive_json_gcs","archive_bom_csv_gcs","status","created_by"])',
              "seed Summary headers")
insert_before(r'_upsert_row_by_header\(\s*sh\.worksheet\("Geometry"\)',
              '_seed_headers(sh.worksheet("Geometry"), ["total_area_sqft","facets_count","perimeter_lf","predominant_pitch","avg_pitch"])',
              "seed Geometry headers")
insert_before(r'_upsert_row_by_header\(\s*sh\.worksheet\("Linears"\)',
              '_seed_headers(sh.worksheet("Linears"), ["eaves_lf","rakes_lf","ridges_lf","hips_lf","valleys_lf","wall_flash_lf","step_flash_lf","drip_edge_eaves_lf","drip_edge_rakes_lf","starter_lf"])',
              "seed Linears headers")
insert_before(r'_upsert_row_by_header\(\s*sh\.worksheet\("Openings"\)',
              '_seed_headers(sh.worksheet("Openings"), ["pipe_vent_small_qty","pipe_vent_large_qty","attic_fan_qty","skylight_qty","chimney_small_qty","chimney_large_qty"])',
              "seed Openings headers")

# --- Summary: compute locals & replace dict
insert_before(r'^\s*summary\s*=\s*\{',
              '    city, state = _parse_city_state(payload.get("job_address",""))\n'
              '    created_by = payload.get("created_by","")\n'
              '    status = payload.get("status","")\n'
              '    created_at_local = datetime.datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")',
              "compute city/state & created_at_local")

replace_block(r'^\s*summary\s*=\s*\{[^\n]*\n',
              r'^\s*\}\s*$',
              r'''    summary = {
        "job_id": job_id,
        "created_at": created_at_local,
        "job_address": payload.get("job_address",""),
        "city": city,
        "state": state,
        "zip_code": str(payload.get("zip_code","") or ""),
        "system_id": (payload.get("selections") or {}).get("system_id",{}).get("value",""),
        "shingle_color": (payload.get("selections") or {}).get("shingle_color",{}).get("value",""),
        "waste_pct_final": payload.get("waste_pct_final",""),
        "distributor_type": payload.get("distributor_type",""),
        "report_url": payload.get("report_url",""),
        "archive_json_gcs": payload.get("archive_json_gcs",""),
        "archive_bom_csv_gcs": payload.get("archive_bom_csv_gcs",""),
        "status": status,
        "created_by": created_by
    }
''',
              "Summary dict")

# --- Master: headers -> timestamp_local, plus new cols
text = re.sub(
    r'ws\.update\([^\n]*\[\[.*?\]\]\)',
    'ws.update("A1", [["timestamp_local","job_address","city","state","zip_code","system_id","shingle_color","waste_pct_final","distributor_type","report_url","items_json","status","created_by"]])',
    text, flags=re.S)
changed.append("~ Master headers -> timestamp_local + extra cols")

# Master timestamp -> ET local
text = re.sub(
    r'ts\s*=\s*datetime\.[^\n]+',
    'ts = datetime.datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")',
    text)
changed.append("~ Master ts -> ET local")

# Master row -> new order
text = re.sub(
    r'row\s*=\s*\[\s*.*?\n\s*\]',
    (
        'row = [\n'
        '    ts,\n'
        '    payload.get("job_address",""),\n'
        '    _parse_city_state(payload.get("job_address",""))[0],\n'
        '    _parse_city_state(payload.get("job_address",""))[1],\n'
        '    str(payload.get("zip_code","") or ""),\n'
        '    (payload.get("selections") or {}).get("system_id",{}).get("value",""),\n'
        '    (payload.get("selections") or {}).get("shingle_color",{}).get("value",""),\n'
        '    payload.get("waste_pct_final",""),\n'
        '    payload.get("distributor_type",""),\n'
        '    payload.get("report_url",""),\n'
        '    json.dumps(payload.get("bom_items") or payload.get("calculated_bom") or []),\n'
        '    payload.get("status",""),\n'
        '    payload.get("created_by","")\n'
        ']'
    ),
    text, flags=re.S)
changed.append("~ Master row -> extended cols")

# --- write file
if text != orig:
    backup = SRC.with_suffix(".py.bak-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    backup.write_text(orig)
    SRC.write_text(text)
    print("Patched main.py ✅")
    print("Backup:", backup.name)
    print("Changes:")
    for c in changed:
        print(" -", c)
else:
    print("No changes made (already patched?)")
