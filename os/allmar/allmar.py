import requests, csv, json
import pandas as pd
from dotenv import load_dotenv
import os
import sys
from typing import Optional

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

# Endpoints (hierarchy and create still used)
hierarchy_url = f"https://media.os.wpp.com/api/v2/tenants/{tenant_id}/hierarchy-tree"
create_url = f"https://media.os.wpp.com/_apps/os-workspaces/api/tenants/{tenant_id}/organization-units?disableTenantCache=true"
# markets_url = "https://media.os.wpp.com/api/v2/markets"  # not used when using local file

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

# --- Load local markets file (robust) ---
LOCAL_MARKETS_PATH = r"C:\Users\Azath.A\os\market.json"

def load_local_markets(path=LOCAL_MARKETS_PATH):
    """
    Loads market.json and builds:
      - name_to_id: exact lowercase name -> id
      - alt_to_id: alternative keys (isoAlpha2/3) if present
    The loader attempts multiple parsing strategies to be robust to format.
    """
    name_to_id = {}
    alt_to_id = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                print(f"⚠️  Local markets file is empty: {path}")
                return name_to_id, alt_to_id

            # Try parsing as a JSON array/object first
            try:
                parsed = json.loads(content)
                # If it's a dict with a top-level list under some key, try to find it
                if isinstance(parsed, dict):
                    # look for common keys
                    for possible in ("data", "markets", "items", "countries"):
                        if possible in parsed and isinstance(parsed[possible], list):
                            parsed = parsed[possible]
                            break
                    else:
                        # maybe it's already a mapping of name->id
                        # Check simple mapping: {"Afghanistan": "id", ...}
                        if all(isinstance(v, str) for v in parsed.values()):
                            for k, v in parsed.items():
                                name_to_id[k.strip().lower()] = v
                            return name_to_id, alt_to_id

                # Now parsed should be a list of objects
                if isinstance(parsed, list):
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        # prefer 'id' and 'name'
                        _id = item.get("id") or item.get("mdId") or item.get("md_id")
                        _name = item.get("name") or item.get("marketName") or item.get("country")
                        if _id and _name:
                            name_to_id[_name.strip().lower()] = _id
                        # capture iso codes if present
                        iso2 = item.get("isoAlpha2") or item.get("iso2")
                        iso3 = item.get("isoAlpha3") or item.get("iso3")
                        if _id and iso2:
                            alt_to_id[iso2.strip().lower()] = _id
                        if _id and iso3:
                            alt_to_id[iso3.strip().lower()] = _id
                    return name_to_id, alt_to_id

            except json.JSONDecodeError:
                # Could be newline-delimited JSON objects or a flat repeated id/name sequence.
                pass

            # Try line-by-line JSON objects
            lines = content.splitlines()
            parsed_any = False
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    parsed_any = True
                    if isinstance(obj, dict):
                        _id = obj.get("id")
                        _name = obj.get("name")
                        if _id and _name:
                            name_to_id[_name.strip().lower()] = _id
                except Exception:
                    # not JSON per-line; keep going
                    pass
            if parsed_any:
                return name_to_id, alt_to_id

            # Try to extract id/name pairs from a flat text (very last resort)
            # e.g. '"id": "xxx", "name": "Afghanistan", "id": "yyy", "name": "Aland Islands", ...'
            parts = content.replace('\n', ' ').split('"id"')
            for part in parts[1:]:
                try:
                    # find id between first quotes
                    first_quote = part.find('"')
                    second_quote = part.find('"', first_quote + 1)
                    _id = part[first_quote+1:second_quote]
                    # find "name"
                    name_idx = part.find('"name"')
                    if name_idx != -1:
                        # find the next quotes around the name value
                        after_name = part[name_idx:]
                        nq1 = after_name.find('"', after_name.find(':')+1)
                        nq2 = after_name.find('"', nq1+1)
                        _name = after_name[nq1+1:nq2]
                        if _id and _name:
                            name_to_id[_name.strip().lower()] = _id
                except Exception:
                    continue

            if not name_to_id and not alt_to_id:
                print(f"⚠️  Could not parse local markets file: {path}")
                return name_to_id, alt_to_id

    except FileNotFoundError:
        print(f"❌ Local markets file not found at: {path}")
    except Exception as e:
        print(f"❌ Error loading local markets file {path}: {e}")

    return name_to_id, alt_to_id

# Load local markets into memory once
_name_to_id_map, _alt_to_id_map = load_local_markets(LOCAL_MARKETS_PATH)

def get_market_md_id_local(market_name: str) -> Optional[str]:
    """
    Resolve mdId from local mapping. Matching logic:
      1) exact lowercase match
      2) trimmed match
      3) substring startswith or contains (best-effort)
      4) iso2/iso3 lookup via alt map
    Returns the id string or None if not found.
    """
    if not market_name:
        return None
    key = market_name.strip().lower()

    # exact match
    if key in _name_to_id_map:
        return _name_to_id_map[key]

    # iso/alt match
    if key in _alt_to_id_map:
        return _alt_to_id_map[key]

    # try contains / startswith fuzzy matches
    # prefer startswith then contains
    for name, _id in _name_to_id_map.items():
        if name.startswith(key) or key.startswith(name):
            return _id
    for name, _id in _name_to_id_map.items():
        if key in name or name in key:
            return _id

    # not found
    return None

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

    # Resolve mdId from local markets file
    md_id = get_market_md_id_local(market_name)
    if not md_id:
        print(f"❌ No mdId resolved for market '{market_name}' from local file. Skipping {client_name}.")
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
