import os
import sys
import csv
import requests
from collections import deque
from dotenv import load_dotenv
import pandas as pd
import json

# Define output file path
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\qc\output\output.txt"

# Open the output file
output_file = open(OUTPUT_FILE_PATH, "w", encoding="utf-8")

# Optional: Keep printing to console AND file
_original_print = print

def print(*args, **kwargs):
    # Print to console
    _original_print(*args, **kwargs)
    # Print to file
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    output_file.write(sep.join(map(str, args)) + end)
    output_file.flush() 


# ===== Config =====
TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"
HIERARCHY_URL = f"https://media.os.wpp.com/api/v2/tenants/{TENANT_ID}/hierarchy-tree"

INPUT_CSV = r"C:\Users\Azath.A\os\qc\input.csv"  # Must have header: Market,Client,Brand,Category
ENV_PATH = r"C:\Users\Azath.A\os\auth.env"
TIMEOUT = 30
# ===================

# Auth
load_dotenv(dotenv_path=ENV_PATH)
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")

headers = {
    "Accept": "application/json",
    "User-Agent": "python-requests/2.31",
}
if BEARER_TOKEN:
    headers["Authorization"] = f"Bearer {BEARER_TOKEN}"
cookies = {"session": SESSION_COOKIE} if SESSION_COOKIE else {}

def norm(s: str) -> str:
    return (s or "").strip().lower()

def fetch_tree():
    resp = requests.get(HIERARCHY_URL, headers=headers, cookies=cookies, timeout=TIMEOUT)
    resp.raise_for_status()
    mapping = resp.json().get("mapping", {}) or {}
    # Ensure azId field is present and build node dict
    nodes = {az: ({**node, "azId": az} if "azId" not in node else node) for az, node in mapping.items()}
    return nodes

def find_client(nodes, client_name):
    client_name_n = norm(client_name)
    matches = [
        n for n in nodes.values()
        if str(n.get("type", "")).upper() == "CLIENT" and norm(n.get("name")) == client_name_n
    ]
    if not matches:
        return None
    # If somehow multiple, pick deterministically
    matches.sort(key=lambda n: n.get("azId"))
    return matches[0]

def bfs_collect(nodes, start_ids, type_name=None, name=None):
    """BFS from start_ids; collect nodes matching type_name and/or name (both case-insensitive)."""
    want_type = type_name.upper() if type_name else None
    want_name = norm(name) if name else None

    seen = set()
    out = []
    q = deque(start_ids or [])
    while q:
        az = q.popleft()
        if az in seen:
            continue
        seen.add(az)
        node = nodes.get(az)
        if not node:
            continue

        t_ok = True if not want_type else (str(node.get("type", "")).upper() == want_type)
        n_ok = True if not want_name else (norm(node.get("name")) == want_name)
        if t_ok and n_ok:
            out.append(node)

        for child in (node.get("children") or []):
            q.append(child)
    return out

def brand_has_category(brand_node, category_name):
    if not category_name:
        return True
    cat_n = norm(category_name)
    for c in (brand_node.get("categories") or []):
        if norm(c.get("name")) == cat_n:
            return True
    return False

def resolve_brand_azid(nodes, market_name, client_name, brand_name, category_name):
    # 1) Find CLIENT globally by name
    client = find_client(nodes, client_name)
    if not client:
        raise ValueError(f"Client not found: {client_name}")

    # 2) Under CLIENT, find all MARKETs matching the market_name
    markets = bfs_collect(nodes, client.get("children") or [], type_name="MARKET", name=market_name)
    if not markets:
        raise ValueError(f"Market '{market_name}' not found under client '{client_name}'")

    # 3) For each matching MARKET, find BRANDs with correct name and category
    candidates = []
    for market in sorted(markets, key=lambda n: n.get("azId")):
        brands = bfs_collect(nodes, market.get("children") or [], type_name="BRAND", name=brand_name)
        brands = [b for b in brands if brand_has_category(b, category_name)]
        candidates.extend(brands)

    if not candidates:
        raise ValueError(f"Brand '{brand_name}' with category '{category_name}' not found under market '{market_name}' (client '{client_name}')")

    # Deterministic pick if multiple
    candidates.sort(key=lambda n: n.get("azId"))
    return candidates[0]["azId"]

def read_csv_rows(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input CSV not found: {path}")
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"Market", "Client", "Brand", "Category"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV must have header columns: {', '.join(sorted(required))}. Missing: {', '.join(sorted(missing))}")
        for r in reader:
            market = (r.get("Market") or "").strip()
            client = (r.get("Client") or "").strip()
            brand = (r.get("Brand") or "").strip()
            category = (r.get("Category") or "").strip()
            if market and client and brand and category:
                rows.append((market, client, brand, category))
    return rows

def main():
    try:
        nodes = fetch_tree()
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        rows = read_csv_rows(INPUT_CSV)
    except Exception as e:
        print(f"Input error: {e}", file=sys.stderr)
        sys.exit(1)

    for market, client, brand, category in rows:
        try:
            azid = resolve_brand_azid(nodes, market, client, brand, category)
            # Print input along with the brand azId
            print(f"Found row({market},{client},{brand},{category}): {azid}")
        except Exception as e:
            # Keep stdout clean; errors go to stderr
            print(f"Error ({market},{client},{brand},{category}): {e}", file=sys.stderr)

if __name__ == "__main__":
    main()

output_file.close()