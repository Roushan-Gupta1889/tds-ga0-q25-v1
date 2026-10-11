import json
import math
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()


# ---------------------------------------------------------------- CORS
# Added to EVERY response (even when the request has no Origin header,
# and even on errors), so the checker always sees Access-Control-Allow-Origin: *
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": request.headers.get(
            "access-control-request-headers", "*"
        ),
        "Access-Control-Max-Age": "86400",
    }
    if request.method == "OPTIONS":  # preflight
        return Response(status_code=204, headers=headers)
    try:
        response = await call_next(request)
    except Exception as exc:  # keep CORS headers on crashes too
        response = JSONResponse({"detail": f"Server error: {exc}"}, status_code=500)
    for k, v in headers.items():
        response.headers[k] = v
    return response


# ---------------------------------------------------------------- data
_DATA = None


def _load():
    """Load the telemetry JSON that sits next to this file (any *.json)."""
    global _DATA
    if _DATA is not None:
        return _DATA
    files = sorted(Path(__file__).parent.glob("*.json"))
    if not files:
        raise HTTPException(500, "Telemetry JSON not found. Put q-vercel-latency.json inside api/")
    raw = json.loads(files[0].read_text())
    records = []
    if isinstance(raw, list):
        records = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, list):
                for r in val:
                    if isinstance(r, dict):
                        r = dict(r)
                        r.setdefault("region", key)
                        records.append(r)
    _DATA = records
    return _DATA


def _num(rec, preferred, contains):
    """Get a numeric field by preferred names, else by substring match."""
    for k in preferred:
        if k in rec and rec[k] is not None:
            return float(rec[k])
    for k, v in rec.items():
        if contains in k.lower() and isinstance(v, (int, float)):
            return float(v)
    return None


def _percentile(values, p):
    """Linear-interpolation percentile (same as numpy.percentile default)."""
    s = sorted(values)
    if not s:
        return None
    k = (len(s) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def compute(records, regions, threshold):
    out = {}
    for region in regions:
        rows = [r for r in records if str(r.get("region", "")).lower() == region.lower()]
        lat = [v for v in (_num(r, ("latency_ms", "latency"), "latency") for r in rows) if v is not None]
        up = [v for v in (_num(r, ("uptime_pct", "uptime", "uptime_percent"), "uptime") for r in rows) if v is not None]
        out[region] = {
            "avg_latency": sum(lat) / len(lat) if lat else None,
            "p95_latency": _percentile(lat, 95),
            "avg_uptime": sum(up) / len(up) if up else None,
            "breaches": sum(1 for v in lat if v > threshold),
        }
    return out


# ---------------------------------------------------------------- routes
class Query(BaseModel):
    regions: List[str]
    threshold_ms: float


@app.get("/")
def health():
    return {"status": "ok", "usage": "POST /api/latency with {regions: [...], threshold_ms: 180}"}


@app.post("/")
@app.post("/api")
@app.post("/api/latency")
def latency(q: Query):
    result = compute(_load(), q.regions, q.threshold_ms)
    # per-region keys at top level, and also nested under "regions"
    return {**result, "regions": result}
