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


def get_brand_mdId(brand_name: str) -> str:
    """Call /api/brands to get mdId for a given brand name"""
    url = f"https://media.os.wpp.com/api/brands?page=1&itemsPerPage=50&filter[search]={brand_name}"
    resp = requests.get(url, headers=headers, cookies=cookies)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        raise ValueError(f"Brand '{brand_name}' not found in API")
    return data[0]["id"]  # mdId


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
df = pd.read_csv(csv_file, header=None, names=["Market", "ClientName", "BrandName", "Category"])

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