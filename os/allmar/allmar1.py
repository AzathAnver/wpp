import requests, csv, json
import pandas as pd
from dotenv import load_dotenv
import os
import sys

# Define output file path
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\allmar\output\output.txt"

# Open the output file
output_file = open(OUTPUT_FILE_PATH, "w", encoding="utf-8")

# Optional: Keep printing to console AND file
_original_print = print
def print(*args, **kwargs):
    _original_print(*args, **kwargs)
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    output_file.write(sep.join(map(str, args)) + end)
    output_file.flush()

# --- Setup environment ---
env_path = r"C:\Users\Azath.A\os\auth.env"
load_dotenv(dotenv_path=env_path)

bearer_token = os.getenv("BEARER_TOKEN")
session_cookie = os.getenv("SESSION_COOKIE")

tenant_id = "4c039217-7d17-4207-8314-98348983718a"

# Endpoints
hierarchy_url = f"https://media.os.wpp.com/api/v2/tenants/{tenant_id}/hierarchy-tree"
create_url = f"https://media.os.wpp.com/_apps/os-workspaces/api/tenants/{tenant_id}/organization-units?disableTenantCache=true"
markets_url = "https://media.os.wpp.com/api/v2/markets"

headers = {
    "Authorization": f"Bearer {bearer_token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "python-requests/2.31"
}
cookies = {"session": session_cookie}

# --- File Readers ---
def read_clients_from_csv(filename="clients.csv"):
    """
    Expected CSV headers: client_name, market
    Accepts aliases: client, country, market_name
    """
    items = []
    with open(filename, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # start=2 (header is row 1)
            client = (row.get("client_name") or row.get("client") or "").strip()
            market = (row.get("market") or row.get("country") or row.get("market_name") or "").strip()
            if client and market:
                items.append({"client_name": client, "market": market})
            else:
                print(f"⚠️  Skipping row {i}: need 'client_name' and 'market'. Row={row}")
    return items

# --- Market mdId lookup with caching ---
_market_md_cache = {}

def get_market_md_id(market_name: str):
    """
    Query the Markets API to get mdId for a country-level market.
    Tries exact name match, then ISO codes, then falls back to first result.
    """
    key = market_name.strip().lower()
    if key in _market_md_cache:
        return _market_md_cache[key]

    params = {
        "page": 1,
        "itemsPerPage": 50,
        "filter[type]": "COUNTRY",
        "filter[search]": market_name
    }

    try:
        r = requests.get(markets_url, headers=headers, cookies=cookies, params=params, timeout=30)
    except requests.RequestException as e:
        print(f"❌ Network error looking up market '{market_name}': {e}")
        return None

    if r.status_code != 200:
        print(f"❌ Market lookup failed for '{market_name}': {r.status_code}")
        try:
            print(r.json())
        except Exception:
            print(r.text)
        return None

    payload = r.json()
    data = payload.get("data", [])
    if not data:
        print(f"⚠️  Market not found: {market_name}")
        return None

    # Choose best match
    exact = next((m for m in data if m.get("name", "").lower() == key), None)
    iso_match = next((m for m in data if m.get("isoAlpha2", "").lower() == key or m.get("isoAlpha3", "").lower() == key), None)
    chosen = exact or iso_match or data[0]

    md_id = chosen.get("id")
    canonical = chosen.get("name")
    if not md_id:
        print(f"⚠️  No id in market response for '{market_name}'. Chosen={chosen}")
        return None

    _market_md_cache[key] = md_id
    print(f"🌍 Market '{market_name}' -> {canonical} (mdId={md_id})")
    return md_id

# --- Load clients from CSV ---
rows = read_clients_from_csv("clients.csv")

if not rows:
    print("❌ No valid rows found in clients.csv. Ensure it has columns: client_name, market")
    output_file.close()
    sys.exit(1)

# --- 1. Load hierarchy once
try:
    resp = requests.get(hierarchy_url, headers=headers, cookies=cookies, timeout=30)
    resp.raise_for_status()
except requests.RequestException as e:
    print(f"❌ Failed to load hierarchy: {e}")
    output_file.close()
    sys.exit(1)

hierarchy = resp.json().get("mapping", {})
org_by_name = {item.get("name", "").lower(): item for item in hierarchy.values()}

# --- 2. Loop clients (client_name + market) ---
for row in rows:
    client_name = row["client_name"]
    market_name = row["market"]

    print("=" * 40)
    print(f"🔍 Processing client: {client_name} | market: {market_name}")

    # Find parent org-unit by client name
    parent = org_by_name.get(client_name.lower())
    if not parent:
        print(f"⚠️  Not found in hierarchy: {client_name}")
        continue

    parent_id = parent["azId"]

    # Resolve mdId dynamically via Markets API
    md_id = get_market_md_id(market_name)
    if not md_id:
        print(f"❌ No mdId resolved for market '{market_name}'. Skipping {client_name}.")
        continue

    # Build payload
    payload = {
        "type": "predefined",
        "parentId": parent_id,
        "categories": [],
        "data": {
            "mdId": md_id
        }
    }

    # Create org-unit
    try:
        create_resp = requests.post(create_url, headers=headers, cookies=cookies, json=payload, timeout=30)
    except requests.RequestException as e:
        print(f"❌ Network error posting for {client_name} -> {market_name}: {e}")
        continue

    if create_resp.status_code == 201:
        print(f"✅ Successfully created org-unit for {client_name} -> {market_name}")
    elif create_resp.status_code == 409:
        print(f"ℹ️  Org-unit already exists for {client_name} -> {market_name}")
        try:
            print(create_resp.json())
        except Exception:
            print(create_resp.text)
    else:
        print(f"❌ Failed for {client_name} -> {market_name}: {create_resp.status_code}")
        try:
            print(create_resp.json())
        except Exception:
            print(create_resp.text)

output_file.close()