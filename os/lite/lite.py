import os
import sys
import csv
import json
from collections import deque

import requests
from dotenv import load_dotenv
import pandas as pd

# Define output file path
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\lite\output\output.txt"

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


# ===== Static config (only assignmentId changes) =====
TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"
TEMPLATE_ID = "15207128-819e-4607-a036-9dc530032676"
BULK_URL = f"https://media.os.wpp.com/api/app-instances/templates/{TEMPLATE_ID}/apply/bulk"

# Static payload parts
APP_INSTANCE_IDS = [
    "1a4486b4-4d7c-4a72-98a2-55cc1a112265",
    "558f39ec-f60f-42a4-b33e-0b46288eb330",
    "365e8615-e147-49a6-b543-b95f800667cd",
    "702ad0f0-30bb-4908-9e0e-64f17d8ffbed",
    "a59c85bb-fd6d-4788-83a5-f0e034979e4b",
    "031bcaf2-96d2-4400-91fe-b42d783591b0",
    "68e56eb8-8c33-42b6-a98c-2a2c99ef3734",
    "3cb12169-ce24-49c8-9d27-57c268379c87",
    "7c333af4-dcff-4b8e-863e-7e51b5c141b4",
    "519e33c6-0fd5-4a86-b87f-0eb41f073a1a",
    "5dcf8a29-2127-4f24-896c-df6fb959b732",
    "eae6c0a1-fce7-4926-9a2f-95b68a994f03",
    "1ee02388-62e8-4cad-aafe-bf2cf54fdf9e",
    "8604f89d-0362-4c8c-8868-a2d9c756ef63",
    "f8763795-a2b3-45b5-acd2-42662f9edb9a",
    "9efba251-6491-40cb-a39f-d6be38906665",
    "133d417f-fb65-4772-8580-0b8d3ca615a9",
    "3d9b280b-319c-44b0-8591-3c2268c09aee",
    "f94a711f-a59a-41f1-8f14-6600f807554e",
    "c5a7eec0-1b7c-4f64-a986-aa153f4139c6",
    "dfd85d23-57e9-403d-96cc-ac06ac4a91d6",
    "671f98a6-c263-4726-a7b9-09c01ab9454c",
    "6a4ad2da-d3ab-4919-bbd4-63ace1677440",
]
LINK_TO_HIERARCHY = True
ASSIGNMENT_TYPE = "WORKSPACE"

# Inputs
INPUT_CSV = r"C:\Users\Azath.A\os\lite\clients.csv"  # columns: Market, Client, Brand, Category
ENV_PATH = r"C:\Users\Azath.A\os\auth.env"
TIMEOUT = 30
# =====================================================

def norm(s: str) -> str:
    return (s or "").strip().lower()

def load_auth():
    load_dotenv(dotenv_path=ENV_PATH)
    bearer = os.getenv("BEARER_TOKEN")
    session_cookie = os.getenv("SESSION_COOKIE")
    if not bearer and not session_cookie:
        print("ERROR: Set BEARER_TOKEN or SESSION_COOKIE in env.", file=sys.stderr)
        sys.exit(1)
    headers = {
        "Accept": "application/json",
        "User-Agent": "python-requests/2.x",
        "Content-Type": "application/json",
    }
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    cookies = {"session": session_cookie} if session_cookie else {}
    return headers, cookies

def fetch_tree(headers, cookies):
    url = f"https://media.os.wpp.com/api/v2/tenants/{TENANT_ID}/hierarchy-tree"
    resp = requests.get(url, headers=headers, cookies=cookies, timeout=TIMEOUT)
    resp.raise_for_status()
    mapping = resp.json().get("mapping", {}) or {}
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
    matches.sort(key=lambda n: n.get("azId"))
    return matches[0]

from collections import deque
def bfs_collect(nodes, start_ids, type_name=None, name=None):
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
    client = find_client(nodes, client_name)
    if not client:
        raise ValueError(f"Client not found: {client_name}")
    markets = bfs_collect(nodes, client.get("children") or [], type_name="MARKET", name=market_name)
    if not markets:
        raise ValueError(f"Market '{market_name}' not found under client '{client_name}'")
    candidates = []
    for market in sorted(markets, key=lambda n: n.get("azId")):
        brands = bfs_collect(nodes, market.get("children") or [], type_name="BRAND", name=brand_name)
        brands = [b for b in brands if brand_has_category(b, category_name)]
        candidates.extend(brands)
    if not candidates:
        raise ValueError(
            f"Brand '{brand_name}' with category '{category_name}' not found under market '{market_name}' (client '{client_name}')"
        )
    candidates.sort(key=lambda n: n.get("azId"))
    return candidates[0]["azId"]  # dynamic assignmentId

def read_csv_rows(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input CSV not found: {path}")
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"Market", "Client", "Brand", "Category"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV must have headers: {', '.join(sorted(required))}. Missing: {', '.join(sorted(missing))}")
        for r in reader:
            market = (r.get("Market") or "").strip()
            client = (r.get("Client") or "").strip()
            brand = (r.get("Brand") or "").strip()
            category = (r.get("Category") or "").strip()
            if market and client and brand and category:
                rows.append((market, client, brand, category))
    return rows

def post_apply_bulk(headers, cookies, assignment_id, app_instance_ids=None):
    payload = {
        "linkToHierarchy": True,
        "assignments": [{"assignmentId": assignment_id, "assignmentType": "WORKSPACE"}]
    }
    if app_instance_ids is not None:
        payload["appInstanceIds"] = app_instance_ids

    resp = requests.post(
        f"https://media.os.wpp.com/api/app-instances/templates/15207128-819e-4607-a036-9dc530032676/apply/bulk",
        headers={**headers, "Content-Type": "application/json"},
        cookies=cookies,
        json=payload,
        timeout=30
    )
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return payload, resp.status_code, body

def main():
    headers, cookies = load_auth()
    try:
        nodes = fetch_tree(headers, cookies)
    except Exception as e:
        print(f"ERROR fetching hierarchy: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        rows = read_csv_rows(INPUT_CSV)
        if not rows:
            print("No valid rows in CSV.", file=sys.stderr)
            sys.exit(2)
    except Exception as e:
        print(f"ERROR reading CSV: {e}", file=sys.stderr)
        sys.exit(1)

    for market, client, brand, category in rows:
        row_info = {"Market": market, "Client": client, "Brand": brand, "Category": category}
        try:
            assignment_id = resolve_brand_azid(nodes, market, client, brand, category)
            payload, status, body = post_apply_bulk(headers, cookies, assignment_id)
            print(json.dumps({
                "row": row_info,
                "input": payload,
                "status": status,
                "response": body
            }, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({
                "row": row_info,
                "error": str(e)
            }, ensure_ascii=False), file=sys.stderr)

if __name__ == "__main__":
    main()
output_file.close()