import requests
import pandas as pd
import os
import json
from dotenv import load_dotenv
import sys
import time
from typing import Optional

# ---------------- CONFIG ----------------
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\brand\output\output.txt"
ENV_PATH = r"C:\Users\Azath.A\os\auth.env"
CSV_FILE = r"C:\Users\Azath.A\os\brand\input.csv"
CATEGORY_FILE = r"C:\Users\Azath.A\os\category.json"

BRAND_CACHE_FILE = r"C:\Users\Azath.A\os\brand\cache\brand_cache.json"
HIERARCHY_CACHE_FILE = r"C:\Users\Azath.A\os\brand\cache\hierarchy_cache.json"

# Set this env var to "1" to force refresh caches (useful for testing)
FORCE_REFRESH = os.getenv("FORCE_REFRESH_CACHE", "0") == "1"

# API / tenant
tenant_id = "4c039217-7d17-4207-8314-98348983718a"

# ---------------- Logging to file + console ----------------
os.makedirs(os.path.dirname(OUTPUT_FILE_PATH), exist_ok=True)
output_file = open(OUTPUT_FILE_PATH, "w", encoding="utf-8")
_original_print = print
def print(*args, **kwargs):
    _original_print(*args, **kwargs)
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    output_file.write(sep.join(map(str, args)) + end)
    output_file.flush()

# ---------------- Load env + headers ----------------
load_dotenv(dotenv_path=ENV_PATH)
bearer_token = os.getenv("BEARER_TOKEN")
session_cookie = os.getenv("SESSION_COOKIE")

headers = {
    "Authorization": f"Bearer {bearer_token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "python-requests/2.31"
}
cookies = {"session": session_cookie}

# ---------------- Ensure cache dir ----------------
os.makedirs(os.path.dirname(BRAND_CACHE_FILE), exist_ok=True)

# ---------------- Helpers ----------------
def _normalize_name(s: str) -> str:
    return " ".join(str(s).split()).casefold()

# safe load/dump JSON
def _load_json(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Could not load JSON from {path}: {e}")
        return None

def _dump_json(path: str, data: dict):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp, path)

# ---------------- Session with retries ----------------
session = requests.Session()
session.headers.update(headers)
session.cookies.update(cookies)

def _get_with_retries(url, params=None, max_retries=3, backoff_factor=0.5):
    attempt = 0
    while True:
        try:
            r = session.get(url, params=params, timeout=20)
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            # For 4xx (other than 429) don't retry
            if status and 400 <= status < 500 and status != 429:
                raise
            attempt += 1
            if attempt > max_retries:
                raise
            sleep = backoff_factor * (2 ** (attempt - 1))
            print(f"   ↻ GET error (status={status}), retrying in {sleep:.1f}s... ({attempt}/{max_retries})")
            time.sleep(sleep)
        except requests.RequestException as e:
            attempt += 1
            if attempt > max_retries:
                raise
            sleep = backoff_factor * (2 ** (attempt - 1))
            print(f"   ↻ Network error: {e}. Retrying in {sleep:.1f}s... ({attempt}/{max_retries})")
            time.sleep(sleep)

# ---------------- CACHED HIERARCHY ----------------
def get_hierarchy_mapping(force_refresh: bool = False):
    """
    Returns mapping (dictionary) from last saved cache or fetches once from API.
    """
    if not force_refresh:
        cached = _load_json(HIERARCHY_CACHE_FILE)
        if cached:
            print("🔁 Using cached hierarchy mapping.")
            return cached

    print("📡 Fetching hierarchy-tree from API (one-time)...")
    url = f"https://media.os.wpp.com/api/v2/tenants/{tenant_id}/hierarchy-tree"
    resp = _get_with_retries(url)
    payload = resp.json()
    mapping = payload.get("mapping", {})
    _dump_json(HIERARCHY_CACHE_FILE, mapping)
    print(f"   ✅ Hierarchy cached to {HIERARCHY_CACHE_FILE} (entries: {len(mapping)})")
    return mapping

# ---------------- CACHED BRAND LOOKUP ----------------
# The cache structure will be: { normalized_name: { "mdId": "<id>", "name": "<original name>" } }
brand_cache = {}
loaded_cache = _load_json(BRAND_CACHE_FILE)
if loaded_cache and not FORCE_REFRESH:
    brand_cache = loaded_cache
    print(f"🔁 Loaded brand cache with {len(brand_cache)} entries.")
elif loaded_cache and FORCE_REFRESH:
    print("♻️ Force refresh requested — ignoring existing brand cache.")
else:
    print("🆕 No brand cache found, starting fresh.")

def get_brand_mdId_cached(brand_name: str) -> str:
    normalized = _normalize_name(brand_name)
    # quick hit
    if normalized in brand_cache:
        entry = brand_cache[normalized]
        print(f"   🔍 Cache hit for '{brand_name}' -> mdId={entry['mdId']}")
        return entry["mdId"]

    # Not in cache: do the least-work paginated search but stop ASAP when found.
    print(f"   🔎 Searching remote brands API for exact match: '{brand_name}'")
    page = 1
    page_size = 100  # keep page_size large to reduce calls
    target = normalized
    first_page_names = []

    while True:
        params = {"page": page, "itemsPerPage": page_size, "filter[search]": brand_name}
        resp = _get_with_retries("https://media.os.wpp.com/api/brands", params=params)
        payload = resp.json()
        data = payload.get("data", []) or []

        if page == 1:
            first_page_names = [b.get("name", "") for b in data]

        # scan current page for exact-match (normalized)
        for b in data:
            name = b.get("name", "")
            if _normalize_name(name) == target:
                md = b.get("id")
                brand_cache[target] = {"mdId": md, "name": name}
                _dump_json(BRAND_CACHE_FILE, brand_cache)  # persist immediately
                print(f"   ✅ Matched brand exactly: '{name}' (mdId={md})  — cached.")
                return md

        # no exact-match found on this page
        if len(data) < page_size:
            # last page — stop
            break
        page += 1

    # If we reach here: no exact match found
    suggestions = ", ".join(first_page_names[:5])
    raise ValueError(f"No exact brand named '{brand_name}' found (case-insensitive). Top results: {suggestions}")

# ---------------- post_org_unit unchanged except using session ----------------
def post_org_unit(brand_name: str, category_name: str, parentId: str, mdId: str):
    """POST the organization-unit with given details."""
    # load categories (one time)
    with open(CATEGORY_FILE, "r", encoding="utf-8") as f:
        categories_json = json.load(f)
    categories_data = categories_json["data"]
    category_lookup = {c["name"].strip().lower(): c["id"] for c in categories_data}

    cat_id = category_lookup.get(category_name.lower())
    if not cat_id:
        raise ValueError(f"Category '{category_name}' not found in {CATEGORY_FILE}")

    url = f"https://media.os.wpp.com/_apps/os-workspaces/api/tenants/{tenant_id}/organization-units?disableTenantCache=true"

    payload = {
        "type": "predefined",
        "parentId": parentId,
        "categories": [
            {
                "hierarchy": [],
                "id": cat_id,
                "parent": None,
                "name": category_name,
                "aliases": [],
                "createdAt": None,
                "updatedAt": None,
                "deletedAt": None
            }
        ],
        "data": {
            "mdId": mdId
        }
    }

    # Use session.post for connection reuse
    r = session.post(url, json=payload, timeout=30)
    if r.status_code in (200, 201):
        created = r.json()
        print(f"✅ Created Org Unit for Brand '{brand_name}' under Market {parentId}")
        print(f"   ➡️ OrgUnit azId: {created.get('azId')}")
    else:
        print(f"❌ Failed POST for {brand_name}: {r.status_code} {r.text}")

# ---------------- get_parentId optimized to use one cached mapping ----------------
def get_parentId_from_mapping(mapping: dict, market_name: str, client_name: str) -> str:
    market_nodes = {
        node["azId"]: node
        for node in mapping.values()
        if node.get("type") == "MARKET"
        and node.get("name", "").strip().lower() == market_name.strip().lower()
    }

    client_nodes = {
        node["azId"]: node
        for node in mapping.values()
        if node.get("type") in ("CLIENT", "BRAND")
        and node.get("name", "").strip().lower() == client_name.strip().lower()
    }

    for m_id, m_node in market_nodes.items():
        for child in m_node.get("children", []):
            if child in client_nodes:
                return m_id

    for c_id, c_node in client_nodes.items():
        for child in c_node.get("children", []):
            if child in market_nodes:
                return child

    raise ValueError(f"Market '{market_name}' with client '{client_name}' not found.")

# ---------------- Main loop ----------------
def main():
    # prepare mapping (single GET or cached)
    mapping = get_hierarchy_mapping(force_refresh=FORCE_REFRESH)

    # Load CSV
    df = pd.read_csv(CSV_FILE)
    df = df.rename(columns=lambda c: c.strip())
    required_cols = ["Market", "ClientName", "BrandName", "Category"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        df = pd.read_csv(CSV_FILE, header=None, names=required_cols)

    for i, row in df.iterrows():
        market_name = row["Market"]
        client_name = row["ClientName"]
        brand_name = row["BrandName"]
        category_name = row["Category"]

        print(f"\n🚀 Processing row {i+1}: Market={market_name}, Client={client_name}, Brand={brand_name}, Category={category_name}")
        try:
            mdId = get_brand_mdId_cached(brand_name)
            parentId = get_parentId_from_mapping(mapping, market_name, client_name)
            post_org_unit(brand_name, category_name, parentId, mdId)
        except Exception as e:
            print(f"⚠️ Error for row {i+1}: {e}")

    print("\n🎉 Done.")
    output_file.close()

if __name__ == "__main__":
    main()
