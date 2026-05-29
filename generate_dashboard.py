#!/usr/bin/env python3
"""
generate_dashboard.py
=====================
Generates CAMELS benchmark dashboards for a bank analysis.

Produces three files per run:
  output/<bank>/<year>/dashboard.html           — global peer comparison
  output/<bank>/<year>/dashboard_regional.html  — regional peer comparison
  output/<bank>/<year>/dashboard_dark.html      — dark mode global

Changes:
  - RWA key normalised (rwa_bn in audit → rwa in benchmark index)
  - Regional peer dashboard as separate HTML page
  - Distribution charts: bank marker + peer median marker + period label
  - Toggle between recent/all-time distributions

Usage:
    python generate_dashboard.py --audit output/.../audit.json
    python generate_dashboard.py --bank "Lloyds Banking Group" --year 2025
"""

import json
import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT   = Path(__file__).resolve().parent
BENCHMARK_PATH = PROJECT_ROOT / "processed" / "benchmark_index.json"
OUTPUT_ROOT    = PROJECT_ROOT / "output"
PROCESSED_DIR  = PROJECT_ROOT / "processed" / "financials"

# ─────────────────────────────────────────────────────────────────────────────
# Region detection
# ─────────────────────────────────────────────────────────────────────────────
BANK_REGIONS = {
    "UK": [
        "lloyds", "barclays", "natwest", "rbs", "hsbc", "standard chartered",
        "standard_chartered", "nationwide", "virgin money", "metro bank",
        "close brothers", "paragon", "aldermore",
    ],
    "EU": [
        "deutsche", "bnp", "unicredit", "santander", "societe", "intesa",
        "bbva", "ing", "abn", "credit agricole", "commerzbank", "rabobank",
        "nordea", "danske", "handelsbanken", "swedbank", "seb",
    ],
    "US": [
        "jpmorgan", "bank of america", "citigroup", "wells fargo", "goldman",
        "morgan stanley", "us bancorp", "truist", "pnc", "capital one",
        "regions", "huntington", "keycorp", "comerica", "fifth third",
        "zions", "charles schwab", "state street", "bank of new york",
        "american express",
    ],
    "AU": [
        "commonwealth bank", "cba", "anz", "westpac", "nab",
        "national australia",
    ],
}

def detect_region(bank_name: str) -> str:
    bl = bank_name.lower()
    for region, banks in BANK_REGIONS.items():
        if any(b in bl for b in banks):
            return region
    return "global"

# ─────────────────────────────────────────────────────────────────────────────
# Metric labels — rwa_bn in audit maps to rwa in benchmark index
# ─────────────────────────────────────────────────────────────────────────────
METRIC_LABELS = {
    "cet1_ratio":          ("CET1 Ratio",            "%",  "rwa"),
    "tier1_ratio":         ("Tier 1 Ratio",           "%",  None),
    "total_capital_ratio": ("Total Capital Ratio",    "%",  None),
    "leverage_ratio":      ("Leverage Ratio",         "%",  None),
    "rote":                ("RoTE",                   "%",  None),
    "roe":                 ("RoE",                    "%",  None),
    "nim":                 ("Net Interest Margin",    "%",  None),
    "lcr":                 ("LCR",                    "%",  None),
    "nsfr":                ("NSFR",                   "%",  None),
    "cost_income":         ("Cost:Income Ratio",      "%",  None),
    "stage3_pct":          ("Stage 3 / NPL Ratio",    "%",  None),
    # rwa_bn is the key in audit JSON; maps to "rwa" in benchmark index
    "rwa_bn":              ("Risk-Weighted Assets",   "bn", "rwa"),
}

# Map from audit metric key → benchmark index key (when different)
BENCHMARK_KEY_MAP = {
    "rwa_bn": "rwa",
}

# ─────────────────────────────────────────────────────────────────────────────
# Rating downgrade trigger thresholds
# ─────────────────────────────────────────────────────────────────────────────
RATING_TRIGGERS = {
    "cet1_ratio": {
        "higher_better": True,
        "thresholds": [
            {"level": "MDA trigger",    "value": 11.0, "color": "#f59e0b"},
            {"level": "Regulatory min", "value": 8.0,  "color": "#ef4444"},
            {"level": "Pillar 1 min",   "value": 4.5,  "color": "#991b1b"},
        ],
        "downgrade_zone": 11.5, "watch_zone": 13.0,
        "description": "CET1 below 11% triggers MDA restrictions; below 8% regulatory intervention likely",
    },
    "leverage_ratio": {
        "higher_better": True,
        "thresholds": [
            {"level": "UK/EU min",  "value": 3.25, "color": "#ef4444"},
            {"level": "Basel min",  "value": 3.0,  "color": "#991b1b"},
        ],
        "downgrade_zone": 4.0, "watch_zone": 5.0,
        "description": "Leverage ratio below 3.25% triggers PRA supervisory action",
    },
    "lcr": {
        "higher_better": True,
        "thresholds": [
            {"level": "Regulatory min", "value": 100.0, "color": "#ef4444"},
        ],
        "downgrade_zone": 110.0, "watch_zone": 130.0,
        "description": "LCR below 100% triggers regulatory breach",
    },
    "nsfr": {
        "higher_better": True,
        "thresholds": [
            {"level": "Regulatory min", "value": 100.0, "color": "#ef4444"},
        ],
        "downgrade_zone": 105.0, "watch_zone": 115.0,
        "description": "NSFR below 100% triggers regulatory breach",
    },
    "rote": {
        "higher_better": True,
        "thresholds": [
            {"level": "Cost of equity", "value": 10.0, "color": "#f59e0b"},
            {"level": "Breakeven",      "value": 0.0,  "color": "#ef4444"},
        ],
        "downgrade_zone": 8.0, "watch_zone": 12.0,
        "description": "RoTE below cost of equity signals value destruction",
    },
    "nim": {
        "higher_better": True,
        "thresholds": [
            {"level": "Structural concern", "value": 1.0, "color": "#f59e0b"},
        ],
        "downgrade_zone": 1.5, "watch_zone": 2.0,
        "description": "NIM compression below 1.5% signals earnings under structural pressure",
    },
    "cost_income": {
        "higher_better": False,
        "thresholds": [
            {"level": "Efficiency concern", "value": 70.0, "color": "#f59e0b"},
            {"level": "Critical level",     "value": 80.0, "color": "#ef4444"},
        ],
        "downgrade_zone": 75.0, "watch_zone": 65.0,
        "description": "Cost:income above 70% signals poor efficiency",
    },
    "stage3_pct": {
        "higher_better": False,
        "thresholds": [
            {"level": "Elevated risk",    "value": 3.0,  "color": "#f59e0b"},
            {"level": "Significant risk", "value": 5.0,  "color": "#ef4444"},
            {"level": "Crisis level",     "value": 10.0, "color": "#991b1b"},
        ],
        "downgrade_zone": 4.0, "watch_zone": 2.5,
        "description": "NPL ratio above 3% signals elevated credit quality deterioration",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_benchmark() -> dict:
    if not BENCHMARK_PATH.exists():
        return {}
    with open(BENCHMARK_PATH) as f:
        return json.load(f)


def load_audit(p: Path) -> dict:
    with open(p) as f:
        return json.load(f)


def get_historical_metrics(bank_name: str, current_year: int) -> dict:
    history = {}
    if not PROCESSED_DIR.exists():
        return history
    bank_lower = bank_name.lower().replace(" ", "_").replace("'", "")
    for jp in PROCESSED_DIR.glob("*.json"):
        try:
            with open(jp) as f:
                doc = json.load(f)
            meta     = doc.get("metadata", {})
            doc_bank = meta.get("bank_name", "").lower().replace(" ", "_").replace("'","")
            if not any(p in doc_bank for p in bank_lower.split("_")[:2]):
                continue
            year = meta.get("reporting_year")
            if not year or year == str(current_year):
                continue
            year = int(year)
            km   = doc.get("key_metrics", {})
            flat = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in km.items()}
            if flat:
                history[year] = flat
        except Exception:
            pass
    return history


def get_decile(value: float, dist: dict) -> int:
    for i, t in enumerate(dist.get("deciles", [])):
        if value <= t:
            return i + 1
    return 10


def get_percentile(value: float, dist: dict) -> float:
    deciles = dist.get("deciles", [])
    mn = dist.get("min", 0)
    for i, t in enumerate(deciles):
        if value <= t:
            prev = deciles[i-1] if i > 0 else mn
            return i * 10.0 + ((value - prev) / max(t - prev, 1e-9)) * 10.0
    return 99.0


def assess_trend(history: dict, metric: str, value: float, year: int) -> dict:
    # Also check rwa key alias
    alt = "rwa" if metric == "rwa_bn" else None
    pts = []
    for y in sorted(history):
        v = history[y].get(metric) or (history[y].get(alt) if alt else None)
        if v is not None:
            pts.append((y, v))
    pts.append((year, value))
    pts.sort(key=lambda x: x[0])
    result = {"values": pts, "change_1y": None, "change_5y": None, "direction": "flat"}
    if len(pts) >= 2:
        result["change_1y"] = round(pts[-1][1] - pts[-2][1], 2)
    if len(pts) >= 6:
        result["change_5y"] = round(pts[-1][1] - pts[-min(6,len(pts))][1], 2)
    ch = result["change_1y"]
    if ch is not None:
        result["direction"] = "flat" if abs(ch) < 0.1 else ("improving" if ch > 0 else "deteriorating")
    return result


def assess_proximity(metric: str, value: float, trend: dict) -> dict:
    if metric not in RATING_TRIGGERS:
        return {"status": "comfortable"}
    cfg = RATING_TRIGGERS[metric]
    hb  = cfg["higher_better"]
    ts  = cfg["thresholds"]
    nearest = min(ts, key=lambda t: abs(value - t["value"]))
    nd      = abs(value - nearest["value"])
    if hb:
        status = ("breach" if value <= ts[-1]["value"] else
                  "downgrade_risk" if value <= cfg["downgrade_zone"] else
                  "watch" if value <= cfg["watch_zone"] else "comfortable")
    else:
        status = ("breach" if value >= ts[-1]["value"] else
                  "downgrade_risk" if value >= cfg["downgrade_zone"] else
                  "watch" if value >= cfg["watch_zone"] else "comfortable")
    ch = trend.get("change_1y")
    proj = None
    if ch and ch != 0:
        yrs = (nearest["value"] - value) / ch
        if 0 < yrs <= 5:
            proj = round(yrs, 1)
    return {"status": status, "nearest": nearest, "dist": round(nd,2),
            "projection": proj, "description": cfg["description"]}


def make_hist(d: dict) -> tuple:
    if not d:
        return [], []
    lo  = d.get("min", 0)
    hi  = d.get("max", 100)
    stp = (hi - lo) / 20 if hi > lo else 1
    bins = [round(lo + i * stp, 2) for i in range(21)]
    dec  = d.get("deciles", [])
    counts = []
    for i in range(len(bins) - 1):
        blo, bhi = bins[i], bins[i+1]
        c = sum(1 for j, dv in enumerate(dec)
                if blo <= dv <= bhi or ((dec[j-1] if j>0 else lo) <= blo and dv >= bhi))
        counts.append(max(c, 0.5))
    return bins, counts


def build_chart_configs(metrics: dict, benchmark: dict, history: dict,
                        year: int, region_key: str | None = None) -> list:
    """
    Build chart config list.
    region_key: e.g. 'region_UK' — if set, uses regional dist instead of global.
    """
    configs = []
    for audit_key, (label, unit, _) in METRIC_LABELS.items():
        raw = metrics.get(audit_key)
        if raw is None:
            continue
        value = raw.get("value") if isinstance(raw, dict) else raw
        if value is None:
            continue

        # Benchmark lookup — normalise rwa_bn → rwa
        bm_key = BENCHMARK_KEY_MAP.get(audit_key, audit_key)
        bm     = benchmark.get(bm_key, {})

        # Choose distribution: regional if available, else global recent/all
        if region_key and bm.get(region_key):
            dist         = bm[region_key]
            use_recent   = False
            period_label = f"{region_key.replace('region_','')} peers (n={dist.get('count',0)})"
        else:
            use_recent   = bool(bm.get("recent") and bm["recent"].get("count",0) >= 5)
            dist         = bm.get("recent") if use_recent else bm.get("all", {})
            n            = dist.get("count", 0) if dist else 0
            period_label = (f"Recent 3yr (n={n})" if use_recent else f"All-time (n={n})")

        all_dist         = bm.get("all", {})
        all_period_label = f"All-time (n={all_dist.get('count',0)})" if all_dist else "n/a"

        trend  = assess_trend(history, audit_key, value, year)
        prox   = assess_proximity(audit_key, value, trend)
        decile = get_decile(value, dist) if dist else 5
        pct    = get_percentile(value, dist) if dist else 50.0

        bins,  counts  = make_hist(dist)
        abins, acounts = make_hist(all_dist)

        triggers = [{"value": t["value"], "label": t["level"], "color": t["color"]}
                    for t in RATING_TRIGGERS.get(audit_key, {}).get("thresholds", [])]

        configs.append({
            "key":          audit_key,
            "label":        label,
            "unit":         unit,
            "value":        value,
            "bins":         bins,
            "counts":       counts,
            "abins":        abins,
            "acounts":      acounts,
            "median":       dist.get("median", 0) if dist else 0,
            "all_median":   all_dist.get("median", 0) if all_dist else 0,
            "p10":          dist.get("p10", 0) if dist else 0,
            "p90":          dist.get("p90", 0) if dist else 0,
            "period_label": period_label,
            "all_period_label": all_period_label,
            "use_recent":   use_recent,
            "decile":       decile,
            "pct_rank":     round(pct, 1),
            "triggers":     triggers,
            "hist_series":  [{"year": y, "value": v} for y, v in trend["values"]],
            "direction":    trend["direction"],
            "change_1y":    trend["change_1y"],
            "change_5y":    trend["change_5y"],
            "prox_status":  prox["status"],
            "prox_dist":    prox.get("dist"),
            "prox_trigger": prox.get("nearest", {}).get("level", ""),
            "prox_years":   prox.get("projection"),
        })
    return configs


# ─────────────────────────────────────────────────────────────────────────────
# HTML generation  (shared CSS + JS, parameterised header)
# ─────────────────────────────────────────────────────────────────────────────

_SHARED_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;700&display=swap');
:root{
  --bg:#f8f7f4;--surface:#fff;--surface2:#f2f0ec;--border:#e2ddd6;
  --text:#1a1816;--text2:#6b6560;--text3:#9c9490;
  --accent:#1a3a5c;--accent2:#2d6a9f;
  --green:#059669;--amber:#d97706;--red:#dc2626;--darkred:#7f1d1d;
  --shadow:0 1px 3px rgba(0,0,0,.08),0 4px 12px rgba(0,0,0,.04);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.5}
.header{background:var(--accent);color:#fff;padding:28px 40px 24px;position:relative;overflow:hidden}
.header::after{content:'';position:absolute;right:-60px;top:-60px;width:300px;height:300px;border-radius:50%;background:rgba(255,255,255,.04);pointer-events:none}
.header-top{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
.bank-name{font-size:26px;font-weight:700;letter-spacing:-.5px;line-height:1.2}
.bank-meta{font-family:'DM Mono',monospace;font-size:11px;color:rgba(255,255,255,.6);margin-top:6px;letter-spacing:.5px;text-transform:uppercase}
.header-badge{font-family:'DM Mono',monospace;font-size:10px;padding:4px 10px;border-radius:4px;background:rgba(255,255,255,.12);color:rgba(255,255,255,.8);border:1px solid rgba(255,255,255,.15);white-space:nowrap}
.tabs{background:var(--accent);padding:0 40px;display:flex;gap:0;border-top:1px solid rgba(255,255,255,.1)}
.tab{padding:10px 16px;font-size:11px;font-weight:500;color:rgba(255,255,255,.5);cursor:pointer;border-bottom:2px solid transparent;text-transform:uppercase;letter-spacing:.5px;transition:all .15s}
.tab:hover{color:rgba(255,255,255,.8)}
.tab.active{color:#fff;border-bottom-color:#60a5fa}
.page{padding:28px 40px;max-width:1600px;margin:0 auto}
.nav-links{background:rgba(255,255,255,.08);padding:8px 40px;display:flex;gap:12px;font-size:11px}
.nav-link{color:rgba(255,255,255,.6);text-decoration:none;font-family:'DM Mono',monospace;padding:3px 8px;border-radius:3px;border:1px solid rgba(255,255,255,.15)}
.nav-link:hover,.nav-link.current{color:#fff;background:rgba(255,255,255,.12)}
.summary-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:28px}
.summary-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 16px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.summary-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--status-color,var(--accent2));border-radius:8px 8px 0 0}
.summary-label{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.summary-value{font-family:'DM Mono',monospace;font-size:22px;font-weight:500;color:var(--text);line-height:1;margin-bottom:6px}
.summary-unit{font-size:12px;color:var(--text2)}
.summary-meta{display:flex;align-items:center;gap:6px;margin-top:6px}
.decile-badge{font-family:'DM Mono',monospace;font-size:9px;padding:2px 6px;border-radius:3px;background:var(--surface2);color:var(--text2);border:1px solid var(--border)}
.metrics-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(480px,1fr));gap:16px}
.metric-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px;box-shadow:var(--shadow)}
.metric-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px}
.metric-title{font-size:13px;font-weight:600;color:var(--text)}
.metric-value-large{font-family:'DM Mono',monospace;font-size:28px;font-weight:400;color:var(--text);line-height:1}
.metric-unit-large{font-size:14px;color:var(--text2);margin-left:2px}
.status-pill{font-size:10px;font-weight:600;padding:3px 8px;border-radius:20px;text-transform:uppercase;letter-spacing:.5px}
.status-comfortable{background:#d1fae5;color:#065f46}
.status-watch{background:#fef3c7;color:#92400e}
.status-downgrade_risk{background:#fee2e2;color:#7f1d1d}
.status-breach{background:#7f1d1d;color:#fff}
.dist-canvas{width:100%;height:100px;display:block}
.period-label{display:inline-block;font-family:'DM Mono',monospace;font-size:9px;padding:2px 7px;border-radius:3px;background:#eef2f7;color:#4a6080;border:1px solid #c8d4e3;margin-bottom:6px}
.dist-legend{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px;font-size:10px;color:var(--text2);align-items:center}
.legend-item{display:flex;align-items:center;gap:4px}
.legend-line{width:16px;height:2px;border-radius:1px;display:inline-block}
.legend-dash{width:16px;height:0;border-top:2px dashed;display:inline-block}
.trend-section{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}
.trend-item{text-align:center}
.trend-label{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px}
.trend-val{font-family:'DM Mono',monospace;font-size:13px;font-weight:500}
.tab-panel{display:none}
.tab-panel.active{display:block}
.alert-banner{padding:12px 16px;border-radius:8px;margin-bottom:12px;display:flex;align-items:flex-start;gap:10px;font-size:12px}
.alert-icon{font-size:16px;flex-shrink:0}
.alert-red{background:#fee2e2;border:1px solid #fca5a5;color:#7f1d1d}
.alert-amber{background:#fef3c7;border:1px solid #fcd34d;color:#78350f}
.footer{text-align:center;padding:28px;color:var(--text3);font-size:10px;font-family:'DM Mono',monospace;letter-spacing:.3px;border-top:1px solid var(--border);margin-top:40px}
.toggle-btn{font-size:9px;padding:2px 7px;border-radius:3px;border:1px solid var(--border);background:var(--surface2);color:var(--text2);cursor:pointer;font-family:'DM Mono',monospace;margin-left:6px}
.toggle-btn:hover{background:var(--border)}
"""

_SHARED_JS = """
function showTab(name,el){
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  el.classList.add('active');
  if(name==='distribution') renderDistCharts();
  if(name==='trends')       renderTrendCharts();
  if(name==='triggers')     renderTriggers();
}
function ordinal(n){const s=['th','st','nd','rd'],v=n%100;return n+(s[(v-20)%10]||s[v]||s[0]);}
function trendArrow(dir,ch){
  if(ch==null)return'';
  const sign=ch>0?'+':'';
  const col=dir==='improving'?'#059669':dir==='deteriorating'?'#dc2626':'#9c9490';
  const arr=dir==='improving'?'↑':dir==='deteriorating'?'↓':'→';
  return `<span style="font-size:11px;color:${col}">${arr} ${sign}${ch.toFixed(1)}</span>`;
}
function statusColor(s){return{comfortable:'#10b981',watch:'#f59e0b',downgrade_risk:'#ef4444',breach:'#7f1d1d'}[s]||'#94a3b8';}

function renderOverview(){
  const grid=document.getElementById('summary-grid');
  const alerts=document.getElementById('alert-container');
  let ah='';
  CHARTS.forEach(c=>{
    const sc=statusColor(c.prox_status);
    const div=document.createElement('div');
    div.className='summary-card';
    div.style.setProperty('--status-color',sc);
    div.innerHTML=`
      <div class="summary-label">${c.label}</div>
      <div class="summary-value">${c.value}<span class="summary-unit">${c.unit}</span></div>
      <div class="summary-meta">
        <span class="decile-badge">${ordinal(c.decile)} decile</span>
        ${trendArrow(c.direction,c.change_1y)}
      </div>`;
    grid.appendChild(div);
    if(c.prox_status==='downgrade_risk'||c.prox_status==='breach'){
      const cls=c.prox_status==='breach'?'alert-red':'alert-amber';
      const icon=c.prox_status==='breach'?'🚨':'⚠️';
      let msg=`<strong>${c.label} (${c.value}${c.unit})</strong> — ${c.prox_trigger}`;
      if(c.prox_dist) msg+=`. Distance: <strong>${c.prox_dist}${c.unit}</strong>`;
      if(c.prox_years) msg+=`. At current trend: <strong>~${c.prox_years}yr</strong> to trigger`;
      ah+=`<div class="alert-banner ${cls}"><span class="alert-icon">${icon}</span><div>${msg}</div></div>`;
    }
  });
  alerts.innerHTML=ah;
}

function renderDistCharts(){
  const grid=document.getElementById('dist-grid');
  if(grid.children.length>0)return;
  CHARTS.forEach(c=>{
    const card=document.createElement('div');
    card.className='metric-card';
    const hasBoth=c.abins&&c.abins.length>0&&c.bins&&c.bins.length>0;
    const toggleHtml=hasBoth
      ?`<button class="toggle-btn" id="toggle-${c.key}" onclick="togglePeriod('${c.key}')">${c.use_recent?'Show all-time':'Show recent'}</button>`:'';
    card.innerHTML=`
      <div class="metric-header">
        <div>
          <div class="metric-title">${c.label}</div>
          <div style="margin-top:4px">
            <span class="metric-value-large">${c.value}</span>
            <span class="metric-unit-large">${c.unit}</span>
          </div>
        </div>
        <div style="text-align:right">
          <span class="status-pill status-${c.prox_status}">${c.prox_status.replace('_',' ')}</span>
          <div style="margin-top:6px;font-size:11px;color:#6b6560">${ordinal(c.decile)} decile</div>
          <div style="font-size:10px;color:#9c9490">${c.pct_rank.toFixed(0)}th percentile</div>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
        <span class="period-label" id="period-label-${c.key}">${c.period_label}</span>
        ${toggleHtml}
      </div>
      <canvas class="dist-canvas" id="canvas-${c.key}" height="100"></canvas>
      <div class="dist-legend" id="legend-${c.key}">
        <div class="legend-item">
          <span class="legend-line" style="background:#1a3a5c;height:3px"></span>
          <span style="color:#1a3a5c;font-weight:600">${BANK} (${c.value}${c.unit})</span>
        </div>
        <div class="legend-item">
          <span class="legend-dash" style="border-color:#64748b"></span>
          <span>Peer median (${c.median}${c.unit})</span>
        </div>
        ${c.triggers.map(t=>`
        <div class="legend-item">
          <span class="legend-dash" style="border-color:${t.color}"></span>
          <span style="color:${t.color}">${t.label} (${t.value}${c.unit})</span>
        </div>`).join('')}
      </div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:#9c9490;margin-top:4px">
        <span>p10: ${c.p10}${c.unit}</span>
        <span>median: ${c.median}${c.unit}</span>
        <span>p90: ${c.p90}${c.unit}</span>
      </div>
      <div class="trend-section">
        <div class="trend-item">
          <div class="trend-label">Current</div>
          <div class="trend-val">${c.value}${c.unit}</div>
        </div>
        <div class="trend-item">
          <div class="trend-label">1Y Change</div>
          <div class="trend-val" style="color:${c.change_1y==null?'#9c9490':c.change_1y>0?'#059669':'#dc2626'}">
            ${c.change_1y!=null?(c.change_1y>0?'+':'')+c.change_1y.toFixed(1)+c.unit:'—'}
          </div>
        </div>
        <div class="trend-item">
          <div class="trend-label">5Y Change</div>
          <div class="trend-val" style="color:${c.change_5y==null?'#9c9490':c.change_5y>0?'#059669':'#dc2626'}">
            ${c.change_5y!=null?(c.change_5y>0?'+':'')+c.change_5y.toFixed(1)+c.unit:'—'}
          </div>
        </div>
      </div>`;
    grid.appendChild(card);
    drawDistChart(c,`canvas-${c.key}`,false);
  });
}

function togglePeriod(key){
  const c=CHARTS.find(x=>x.key===key);
  if(!c)return;
  const btn=document.getElementById(`toggle-${key}`);
  const lbl=document.getElementById(`period-label-${key}`);
  const showAll=btn.textContent.includes('all-time');
  if(showAll){lbl.textContent=c.all_period_label;btn.textContent='Show recent';drawDistChart(c,`canvas-${key}`,true);}
  else{lbl.textContent=c.period_label;btn.textContent='Show all-time';drawDistChart(c,`canvas-${key}`,false);}
}

function drawDistChart(c,canvasId,useAll){
  const canvas=document.getElementById(canvasId);
  if(!canvas)return;
  const ctx=canvas.getContext('2d');
  const W=canvas.offsetWidth||440;
  const H=100;
  canvas.width=W;canvas.height=H;
  ctx.clearRect(0,0,W,H);
  const bins=useAll?c.abins:c.bins;
  const counts=useAll?c.acounts:c.counts;
  const median=useAll?c.all_median:c.median;
  if(!bins||bins.length<2)return;
  const lo=bins[0],hi=bins[bins.length-1],range=hi-lo||1;
  const maxCount=Math.max(...counts,1);
  const barW=W/(bins.length-1);
  const axisY=H-18,topPad=22;
  // grid
  ctx.strokeStyle='#f0ede8';ctx.lineWidth=1;
  [0.25,0.5,0.75].forEach(f=>{
    const y=axisY-f*(axisY-topPad);
    ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();
  });
  // bars
  counts.forEach((cnt,i)=>{
    const x=i*barW;
    const bh=(cnt/maxCount)*(axisY-topPad);
    ctx.fillStyle='#d4dae3';
    ctx.fillRect(x,axisY-bh,barW-1,bh);
  });
  // trigger lines
  (c.triggers||[]).forEach(t=>{
    const px=((t.value-lo)/range)*W;
    if(px<0||px>W)return;
    ctx.save();
    ctx.strokeStyle=t.color;ctx.lineWidth=1.5;ctx.setLineDash([3,3]);
    ctx.beginPath();ctx.moveTo(px,topPad);ctx.lineTo(px,axisY);ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle=t.color;ctx.font='8px DM Mono,monospace';
    const lx=px>W-52?px-50:px+2;
    ctx.fillText(t.label,lx,topPad+9);
    ctx.restore();
  });
  // peer median marker
  const mx=((median-lo)/range)*W;
  if(mx>=0&&mx<=W){
    ctx.save();
    ctx.strokeStyle='#64748b';ctx.lineWidth=1.5;ctx.setLineDash([5,4]);
    ctx.beginPath();ctx.moveTo(mx,topPad);ctx.lineTo(mx,axisY);ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle='#64748b';
    ctx.beginPath();ctx.moveTo(mx,axisY+2);ctx.lineTo(mx-4,axisY+9);ctx.lineTo(mx+4,axisY+9);ctx.closePath();ctx.fill();
    ctx.font='8px DM Mono,monospace';ctx.textAlign='center';
    ctx.fillText('median',mx,axisY+17);
    ctx.textAlign='left';ctx.restore();
  }
  // bank marker
  const vx=((c.value-lo)/range)*W;
  if(vx>=0&&vx<=W){
    ctx.save();
    ctx.strokeStyle='#1a3a5c';ctx.lineWidth=2.5;
    ctx.beginPath();ctx.moveTo(vx,topPad);ctx.lineTo(vx,axisY);ctx.stroke();
    ctx.fillStyle='#1a3a5c';
    ctx.beginPath();ctx.moveTo(vx,axisY+2);ctx.lineTo(vx-5,axisY+7);ctx.lineTo(vx,axisY+12);ctx.lineTo(vx+5,axisY+7);ctx.closePath();ctx.fill();
    ctx.font='bold 9px DM Mono,monospace';
    const nameLabel=BANK.split(' ').map(w=>w[0]).join('')+' '+c.value+c.unit;
    const lw=ctx.measureText(nameLabel).width;
    const lx=vx+lw>W-4?vx-lw-4:vx+4;
    ctx.fillText(nameLabel,lx,topPad-4);
    ctx.restore();
  }
  // x axis
  ctx.fillStyle='#9c9490';ctx.font='9px DM Mono,monospace';
  ctx.textAlign='left'; ctx.fillText(lo.toFixed(1),0,H);
  ctx.textAlign='center';ctx.fillText(((lo+hi)/2).toFixed(1),W/2,H);
  ctx.textAlign='right'; ctx.fillText(hi.toFixed(1),W,H);
  ctx.textAlign='left';
}

function renderTrendCharts(){
  const grid=document.getElementById('trend-grid');
  if(grid.children.length>0)return;
  CHARTS.forEach(c=>{
    const hasHist=c.hist_series&&c.hist_series.length>1;
    const card=document.createElement('div');
    card.className='metric-card';
    const histRows=hasHist
      ?c.hist_series.map(p=>{
          const cur=p.year===YEAR;
          return `<span style="font-family:'DM Mono',monospace;font-size:11px;${cur?'font-weight:700;color:#1a3a5c':'color:#6b6560'}">${p.year}: ${p.value}${c.unit}</span>`;
        }).join(' &nbsp;·&nbsp; ')
      :'<span style="color:#9c9490">No historical data in dataset yet</span>';
    card.innerHTML=`
      <div class="metric-header">
        <div>
          <div class="metric-title">${c.label}</div>
          <div style="margin-top:4px">
            <span class="metric-value-large">${c.value}</span>
            <span class="metric-unit-large">${c.unit}</span>
          </div>
        </div>
        <div style="text-align:right;font-size:11px;color:#6b6560">
          <div>1Y: ${c.change_1y!=null?(c.change_1y>0?'+':'')+c.change_1y.toFixed(1)+c.unit:'—'}</div>
          <div style="margin-top:2px">5Y: ${c.change_5y!=null?(c.change_5y>0?'+':'')+c.change_5y.toFixed(1)+c.unit:'—'}</div>
        </div>
      </div>
      <canvas id="tcanvas-${c.key}" height="60" style="width:100%;display:block"></canvas>
      <div style="margin-top:8px;line-height:1.8">${histRows}</div>`;
    grid.appendChild(card);
    if(hasHist) drawTrendChart(c,`tcanvas-${c.key}`);
  });
}

function drawTrendChart(c,id){
  const canvas=document.getElementById(id);
  if(!canvas||!c.hist_series||c.hist_series.length<2)return;
  const W=canvas.offsetWidth||440,H=60;
  canvas.width=W;canvas.height=H;
  const ctx=canvas.getContext('2d');
  const vals=c.hist_series.map(p=>p.value);
  const minV=Math.min(...vals)*0.95,maxV=Math.max(...vals)*1.05;
  const pad=8;
  (c.triggers||[]).forEach(t=>{
    if(t.value<minV||t.value>maxV)return;
    const ty=H-pad-((t.value-minV)/(maxV-minV))*(H-pad*2);
    ctx.strokeStyle=t.color;ctx.lineWidth=1;ctx.setLineDash([3,3]);
    ctx.beginPath();ctx.moveTo(0,ty);ctx.lineTo(W,ty);ctx.stroke();
    ctx.setLineDash([]);
  });
  ctx.strokeStyle='#1a3a5c';ctx.lineWidth=2;
  ctx.beginPath();
  c.hist_series.forEach((p,i)=>{
    const x=(i/(c.hist_series.length-1))*(W-20)+10;
    const y=H-pad-((p.value-minV)/(maxV-minV||1))*(H-pad*2);
    i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
  });
  ctx.stroke();
  c.hist_series.forEach((p,i)=>{
    const x=(i/(c.hist_series.length-1))*(W-20)+10;
    const y=H-pad-((p.value-minV)/(maxV-minV||1))*(H-pad*2);
    ctx.fillStyle=p.year===YEAR?'#1a3a5c':'#94a3b8';
    ctx.beginPath();ctx.arc(x,y,p.year===YEAR?4:2.5,0,Math.PI*2);ctx.fill();
    ctx.fillStyle='#9c9490';ctx.font='8px DM Mono,monospace';
    ctx.textAlign='center';ctx.fillText(p.year,x,H);ctx.textAlign='left';
  });
}

function renderTriggers(){
  const container=document.getElementById('trigger-list');
  if(container.children.length>0)return;
  const order=['breach','downgrade_risk','watch','comfortable'];
  const sorted=[...CHARTS].sort((a,b)=>order.indexOf(a.prox_status)-order.indexOf(b.prox_status));
  sorted.forEach(c=>{
    const card=document.createElement('div');
    card.style.cssText='background:#fff;border:1px solid #e2ddd6;border-radius:10px;padding:18px 20px;margin-bottom:12px';
    const trigRows=(c.triggers||[]).map(t=>{
      const dist=Math.abs(c.value-t.value).toFixed(2);
      const dir=c.value>t.value?'above':'below';
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid #f2f0ec;font-size:11px">
        <span style="color:#6b6560">${t.label}</span>
        <span style="font-family:'DM Mono',monospace;color:${t.color};font-weight:600">${t.value}${c.unit}</span>
        <span style="color:#9c9490">${dist}${c.unit} ${dir}</span>
      </div>`;
    }).join('');
    const projHtml=c.prox_years
      ?`<div style="margin-top:8px;padding:8px 10px;background:#fee2e2;border-radius:5px;font-size:11px;color:#7f1d1d;font-weight:600">
          ⚡ At current trajectory: ~${c.prox_years} year(s) to ${c.prox_trigger}
        </div>`:'';
    card.innerHTML=`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <div>
          <div style="font-weight:600;font-size:13px">${c.label}</div>
          <div style="font-family:'DM Mono',monospace;font-size:20px;margin-top:2px">${c.value}${c.unit}</div>
        </div>
        <span class="status-pill status-${c.prox_status}">${c.prox_status.replace('_',' ')}</span>
      </div>
      ${trigRows}${projHtml}
      <div style="margin-top:8px;font-size:11px;color:#6b6560">
        ${c.prox_dist?`Distance to nearest trigger: <strong>${c.prox_dist}${c.unit}</strong>`:''}
      </div>`;
    container.appendChild(card);
  });
}
renderOverview();
"""


def generate_html(bank: str, year: int, chart_configs: list,
                  subtitle: str, nav_links: str, footer_peer_note: str) -> str:
    """Generate a full dashboard HTML page from pre-built chart configs."""
    import json as _j
    chart_data_js = _j.dumps(chart_configs)
    bank_js       = _j.dumps(bank)
    generated     = datetime.now().strftime("%d %B %Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{bank} — CAMELS Dashboard {year} · {subtitle}</title>
<style>{_SHARED_CSS}</style>
</head>
<body>
<div class="header">
  <div class="header-top">
    <div>
      <div class="bank-name">{bank}</div>
      <div class="bank-meta">CAMELS Dashboard · {subtitle} · {year} · {generated}</div>
    </div>
    <div class="header-badge">CAMELS Analytics v1.0</div>
  </div>
</div>
<div class="nav-links">{nav_links}</div>
<div class="tabs">
  <div class="tab active" onclick="showTab('overview',this)">Overview</div>
  <div class="tab" onclick="showTab('distribution',this)">Peer Distribution</div>
  <div class="tab" onclick="showTab('trends',this)">Trends</div>
  <div class="tab" onclick="showTab('triggers',this)">Downgrade Triggers</div>
</div>
<div class="page">
  <div class="tab-panel active" id="tab-overview">
    <div id="alert-container"></div>
    <div class="summary-grid" id="summary-grid"></div>
  </div>
  <div class="tab-panel" id="tab-distribution">
    <div class="metrics-grid" id="dist-grid"></div>
  </div>
  <div class="tab-panel" id="tab-trends">
    <div class="metrics-grid" id="trend-grid"></div>
  </div>
  <div class="tab-panel" id="tab-triggers">
    <div id="trigger-list"></div>
  </div>
</div>
<div class="footer">
  {bank} · {year} · {footer_peer_note} ·
  Thresholds: Basel III / PRA / ECB · For analytical use only
</div>
<script>
const CHARTS = {chart_data_js};
const BANK   = {bank_js};
const YEAR   = {year};
{_SHARED_JS}
</script>
</body>
</html>"""


def generate_dark_html(html: str) -> str:
    dark = ("--bg:#0f1117;--surface:#1a1d27;--surface2:#22263a;--border:#2d3148;"
            "--text:#e8eaf6;--text2:#8b8fa8;--text3:#5c6080;--accent:#0d1f3c;--accent2:#1e40af;"
            "--green:#10b981;--amber:#f59e0b;--red:#ef4444;--darkred:#7f1d1d;"
            "--shadow:0 1px 3px rgba(0,0,0,.4),0 4px 12px rgba(0,0,0,.3);")
    return html.replace("--bg:#f8f7f4;", dark)


def export_png(html_path: Path, png_path: Path) -> bool:
    for cmd in [
        ["python3", "-m", "playwright", "screenshot", "--full-page",
         str(html_path), str(png_path)],
        ["chromium", "--headless", f"--screenshot={png_path}",
         "--window-size=1440,900", str(html_path)],
        ["google-chrome", "--headless", "--disable-gpu",
         f"--screenshot={png_path}", "--window-size=1440,900", str(html_path)],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=30)
            if r.returncode == 0 and png_path.exists():
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", default=None)
    parser.add_argument("--bank",  default=None)
    parser.add_argument("--year",  default=None)
    args = parser.parse_args()

    if args.audit:
        audit_path = Path(args.audit)
        if not audit_path.is_absolute():
            audit_path = PROJECT_ROOT / audit_path
        audit   = load_audit(audit_path)
        bank    = audit["bank"]
        year    = int(audit["year"])
        metrics = audit.get("metrics", {})
    elif args.bank and args.year:
        bank  = args.bank
        year  = int(args.year)
        safe  = bank.replace(" ", "_")
        files = sorted(OUTPUT_ROOT.glob(f"{safe}_{year}_*_audit.json"))
        if not files:
            print("No audit file found — run test_analysis.py first")
            return
        audit   = load_audit(files[-1])
        metrics = audit.get("metrics", {})
    else:
        parser.print_help()
        return

    print(f"\nGenerating dashboards: {bank} {year}")
    benchmark = load_benchmark()
    history   = get_historical_metrics(bank, year)
    region    = detect_region(bank)
    region_key = f"region_{region}" if region != "global" else None
    print(f"  Region detected: {region}")
    print(f"  Historical years: {len(history)}")

    safe_bank = bank.replace(" ", "_").replace("/", "_")
    out_dir   = OUTPUT_ROOT / safe_bank / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Nav links (relative paths) ─────────────────────────────────────────
    global_nav = (
        '<a class="nav-link current" href="dashboard.html">🌍 Global Peers</a>'
        + (f'<a class="nav-link" href="dashboard_regional.html">🏴 {region} Peers</a>'
           if region_key else '')
    )
    regional_nav = (
        f'<a class="nav-link" href="dashboard.html">🌍 Global Peers</a>'
        f'<a class="nav-link current" href="dashboard_regional.html">🏴 {region} Peers</a>'
    )

    # ── Global dashboard ───────────────────────────────────────────────────
    print("  Building global dashboard...", end=" ", flush=True)
    global_configs = build_chart_configs(metrics, benchmark, history, year,
                                         region_key=None)
    global_html = generate_html(
        bank, year, global_configs,
        subtitle="Global Peers",
        nav_links=global_nav,
        footer_peer_note="Peer population: EBA EU-wide Transparency + FDIC Call Reports + Annual Reports (global)"
    )
    html_path = out_dir / "dashboard.html"
    html_path.write_text(global_html, encoding="utf-8")
    print("✅")

    # Dark mode
    dark_path = out_dir / "dashboard_dark.html"
    dark_path.write_text(generate_dark_html(global_html), encoding="utf-8")

    # ── Regional dashboard ─────────────────────────────────────────────────
    if region_key:
        # Check at least one metric has regional data
        has_regional = any(
            benchmark.get(BENCHMARK_KEY_MAP.get(k, k), {}).get(region_key)
            for k in METRIC_LABELS
        )
        if has_regional:
            print(f"  Building {region} regional dashboard...", end=" ", flush=True)
            regional_configs = build_chart_configs(metrics, benchmark, history, year,
                                                   region_key=region_key)
            regional_html = generate_html(
                bank, year, regional_configs,
                subtitle=f"{region} Regional Peers",
                nav_links=regional_nav,
                footer_peer_note=f"Peer population: {region} regional peers from benchmark index"
            )
            regional_path = out_dir / "dashboard_regional.html"
            regional_path.write_text(regional_html, encoding="utf-8")
            print("✅")
        else:
            print(f"  ⚠️  No regional data for {region} in benchmark index yet")
            print(f"     Run: .venv/bin/python scripts/build_benchmark_index.py --include-eba --include-fdic")
            regional_path = None
    else:
        regional_path = None

    # ── PNG export ─────────────────────────────────────────────────────────
    print("  Exporting dark PNG...", end=" ", flush=True)
    png_path = out_dir / "dashboard_dark.png"
    if export_png(dark_path, png_path):
        print(f"✅ ({png_path.stat().st_size//1024}KB)")
    else:
        print("⚠️  (install playwright: pip install playwright && playwright install chromium)")

    print(f"\n{'='*60}")
    print(f" Global dashboard  : {html_path}")
    if regional_path:
        print(f" Regional dashboard: {regional_path}")
    print(f" Dark HTML         : {dark_path}")
    if png_path.exists():
        print(f" Dark PNG          : {png_path}")
    print(f"\n open {html_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
