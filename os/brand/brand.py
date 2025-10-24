import requests
import pandas as pd
import os
import json
from dotenv import load_dotenv
import sys

# Define output file path
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\brand\output\output.txt"

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


tenant_id = "4c039217-7d17-4207-8314-98348983718a"

# 🔑 Load credentials
env_path = r"C:\Users\Azath.A\os\auth.env"
load_dotenv(dotenv_path=env_path)

bearer_token = os.getenv("BEARER_TOKEN")
session_cookie = os.getenv("SESSION_COOKIE")

headers = {
    "Authorization": f"Bearer {bearer_token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "python-requests/2.31"
}
cookies = {"session": session_cookie}

# --- Load categories dictionary from file ---
with open(r"C:\Users\Azath.A\os\category.json", "r", encoding="utf-8") as f:
    categories_json = json.load(f)
categories_data = categories_json["data"]
category_lookup = {c["name"].strip().lower(): c["id"] for c in categories_data}


def _normalize_name(s: str) -> str:
    # collapse whitespace + case-insensitive comparison
    return " ".join(s.split()).casefold()

def get_brand_mdId(brand_name: str) -> str:
    """
    Strictly return mdId for an exact brand name (case-insensitive).
    Will NOT fall back to the first partial result.
    Raises if none or multiple exact matches are found.
    """
    target = _normalize_name(brand_name)
    page = 1
    page_size = 100
    exact_matches = []
    first_page_names = []

    while True:
        params = {
            "page": page,
            "itemsPerPage": page_size,
            "filter[search]:": brand_name  # requests will safely encode via params
        }
        # Some backends are picky about the trailing colon — if you see 400s, change the key to "filter[search]"
        params = {
            "page": page,
            "itemsPerPage": page_size,
            "filter[search]": brand_name
        }

        resp = requests.get(
            "https://media.os.wpp.com/api/brands",
            headers=headers,
            cookies=cookies,
            params=params
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data", []) or []

        if page == 1:
            first_page_names = [b.get("name", "") for b in data]

        for b in data:
            name = b.get("name", "")
            if _normalize_name(name) == target:
                exact_matches.append(b)

        # stop if looks like no more pages
        if len(data) < page_size:
            break
        page += 1

    if len(exact_matches) == 1:
        match = exact_matches[0]
        print(f"   ✅ Matched brand exactly: '{match.get('name')}' (mdId={match.get('id')})")
        return match["id"]

    if len(exact_matches) > 1:
        options = ", ".join(f"{b.get('name')} (id={b.get('id')})" for b in exact_matches[:10])
        extra = "..." if len(exact_matches) > 10 else ""
        raise ValueError(f"Multiple brands named '{brand_name}' found. Please disambiguate. Candidates: {options}{extra}")

    suggestions = ", ".join(first_page_names[:5])
    raise ValueError(f"No exact brand named '{brand_name}' found (case-insensitive). Top results: {suggestions}")


def get_parentId(market_name: str, client_name: str) -> str:
    """
    Fetch /hierarchy-tree and get specific market azId
    by validating that the market contains the desired client.
    """
    url = f"https://media.os.wpp.com/api/v2/tenants/{tenant_id}/hierarchy-tree"
    resp = requests.get(url, headers=headers, cookies=cookies)
    resp.raise_for_status()
    data = resp.json()
    mapping = data.get("mapping", {})

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

    # Try to link market ↔︎ client
    for m_id, m_node in market_nodes.items():
        for child in m_node.get("children", []):
            if child in client_nodes:
                return m_id  # found the Market hosting this Client!

    for c_id, c_node in client_nodes.items():
        for child in c_node.get("children", []):
            if child in market_nodes:
                return child  # found the Market as child of Client!

    raise ValueError(f"Market '{market_name}' with client '{client_name}' not found.")


def post_org_unit(brand_name: str, category_name: str, parentId: str, mdId: str):
    """POST the organization-unit with given details."""
    cat_id = category_lookup.get(category_name.lower())
    if not cat_id:
        raise ValueError(f"Category '{category_name}' not found in category.json")

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

    resp = requests.post(url, headers=headers, cookies=cookies, json=payload)

    if resp.status_code in (200, 201):  # ✅ Accept success
        print(f"✅ Created Org Unit for Brand '{brand_name}' under Market {parentId}")
        # You can also parse and print the new azId if you want:
        created = resp.json()
        print(f"   ➡️ OrgUnit azId: {created.get('azId')}")
    else:
        print(f"❌ Failed POST for {brand_name}: {resp.status_code} {resp.text}")

# --- Run on CSV ---
csv_file = r"C:\Users\Azath.A\os\brand\input.csv"
# Expect a header row: Market,ClientName,BrandName,Category
df = pd.read_csv(csv_file)
df = df.rename(columns=lambda c: c.strip())  # trim any spaces in headers
required_cols = ["Market", "ClientName", "BrandName", "Category"]
missing = [c for c in required_cols if c not in df.columns]
if missing:
    # Fallback if your file truly has no header
    df = pd.read_csv(csv_file, header=None, names=required_cols)

for _, row in df.iterrows():
    market_name = row["Market"]          # e.g., Germany
    client_name = row["ClientName"]      # e.g., Amazon
    brand_name = row["BrandName"]        # e.g., 7 Vidas
    category_name = row["Category"]      # e.g., Charities

    print(f"\n🚀 Processing: Market={market_name}, Client={client_name}, Brand={brand_name}, Category={category_name}")
    try:
        mdId = get_brand_mdId(brand_name)
        parentId = get_parentId(market_name, client_name)
        post_org_unit(brand_name, category_name, parentId, mdId)
    except Exception as e:
        print(f"⚠️ Error: {e}")
output_file.close()