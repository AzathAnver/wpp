import requests
import pandas as pd
from dotenv import load_dotenv
import os


# --- Setup ---
tenant_id = "4c039217-7d17-4207-8314-98348983718a"
url = f"https://media.os.wpp.com/api/v2/tenants/{tenant_id}/hierarchy-tree"

# 🛠️ Replace with your real token and session cookie:
# --- Setup environment ---
env_path = r"C:\Users\Azath.A\os\auth.env"
load_dotenv(dotenv_path=env_path)

bearer_token = os.getenv("BEARER_TOKEN")
session_cookie = os.getenv("SESSION_COOKIE")

headers = {
    "Authorization": f"Bearer {bearer_token}",
    "Accept": "application/json",
    "User-Agent": "python-requests/2.31"
}

cookies = {
    "session": session_cookie
}

# --- Inputs ---
brand_name = "Amazon"
market_name = "Germany"
market_mdId = "c4a22815-f54d-4b8d-9b81-b3ad73add8e6"

resp = requests.get(url, headers=headers, cookies=cookies)
if resp.status_code != 200:
    print("❌ API error", resp.status_code, resp.text)
    exit()

data = resp.json()
mapping = data.get("mapping", {})

# Step 1: Brand nodes (CLIENT or BRAND)
brand_nodes = {
    node["azId"]: node
    for node in mapping.values()
    if node.get("type") in ("BRAND", "CLIENT")
    and node.get("name", "").strip().lower() == brand_name.strip().lower()
}

# Step 2: Market nodes (looser match: name or mdId)
market_nodes = {
    node["azId"]: node
    for node in mapping.values()
    if node.get("type") == "MARKET"
    and (
        node.get("mdId") == market_mdId
        or node.get("name", "").strip().lower() == market_name.strip().lower()
    )
}

print("🗺️ Matching markets and brands/clients:")
found = False

# (A) Market → children contain Brand/Client
for m_id, m_node in market_nodes.items():
    for child in m_node.get("children", []):
        if child in brand_nodes:
            print("=" * 50)
            print(f"🎯 Market: {m_node['name']} ({m_id})")
            found = True

# (B) Brand/Client → children contain Market
for b_id, b_node in brand_nodes.items():
    for child in b_node.get("children", []):
        if child in market_nodes:  # bingo!
            print("=" * 50)
            print(f"🎯 Market: {market_nodes[child]['name']} ({child})")
            
            found = True

if not found:
    print(f"⚠️ No match found for Brand='{brand_name}' in Market='{market_name}'")