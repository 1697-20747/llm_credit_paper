#!/usr/bin/env python3
"""Get full list of FDIC financial fields and find the CAMELS ones."""
import json, ssl, os, urllib.request, urllib.parse

try:
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    ctx = ssl._create_unverified_context()

api_key = os.environ.get("FDIC_API_KEY", "")
headers = {"User-Agent": "CAMELS-Research-Tool/1.0"}
if api_key:
    headers["X-API-Key"] = api_key

def get(endpoint, params):
    url = f"https://banks.data.fdic.gov/api/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return json.loads(r.read().decode())

# Get full financial record for JPMorgan cert=628
fin = get("financials", {
    "filters":    "CERT:628 AND REPDTE:[20231201 TO 20231231]",
    "sort_by":    "REPDTE",
    "sort_order": "DESC",
    "limit":      1,
    "output":     "json"
})

fdata = fin.get("data", [])
if fdata:
    rec = fdata[0].get("data", fdata[0])
    print(f"Total fields: {len(rec)}")
    print()

    # Print all fields with values — looking for CAMELS metrics
    camels_keywords = ["RATIO", "ROE", "ROA", "NIM", "TIER", "CAPITAL",
                       "LEVER", "LCR", "NPL", "NONPERF", "CHARGEOFF",
                       "EFFICIEN", "DEPOSIT", "LOAN", "LIQUID", "ASSET",
                       "INCOME", "MARGIN", "RETURN", "EARNING"]

    print("=== LIKELY CAMELS METRICS ===")
    for k, v in sorted(rec.items()):
        if any(kw in k.upper() for kw in camels_keywords):
            if v not in (None, "", 0, "0"):
                print(f"  {k}: {v}")

    print()
    print("=== ALL FIELDS WITH NON-ZERO VALUES ===")
    for k, v in sorted(rec.items()):
        if v not in (None, "", 0, "0", 0.0):
            try:
                fv = float(v)
                if fv != 0:
                    print(f"  {k}: {v}")
            except (TypeError, ValueError):
                pass
