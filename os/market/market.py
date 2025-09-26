import requests, csv, json
import pandas as pd
from dotenv import load_dotenv
import os
import sys

# Define output file path
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\market\output\output.txt"

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

# --- Setup environment ---
env_path = r"C:\Users\Azath.A\os\auth.env"
load_dotenv(dotenv_path=env_path)

bearer_token = os.getenv("BEARER_TOKEN")
session_cookie = os.getenv("SESSION_COOKIE")

tenant_id = "4c039217-7d17-4207-8314-98348983718a"

# Endpoints
hierarchy_url = f"https://media.os.wpp.com/api/v2/tenants/{tenant_id}/hierarchy-tree"
create_url = f"https://media.os.wpp.com/_apps/os-workspaces/api/tenants/{tenant_id}/organization-units?disableTenantCache=true"

headers = {
    "Authorization": f"Bearer {bearer_token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "python-requests/2.31"
}
cookies = {"session": session_cookie}

# --- File Readers ---
def read_clients_from_txt(filename="clients.txt"):
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def read_clients_from_csv(filename="clients.csv"):
    clients = []
    with open(filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clients.append(row["client_name"].strip())
    return clients

# Pick source: TXT or CSV
client_names = read_clients_from_txt("clients.txt")
# client_names = read_clients_from_csv("clients.csv")

# --- 1. Load hierarchy once
resp = requests.get(hierarchy_url, headers=headers, cookies=cookies)
resp.raise_for_status()
hierarchy = resp.json().get("mapping", {})

# --- 2. Fixed Germany mdId
thailand_md_id = "15050f40-d2fe-4a73-a937-b8fb6d78432f"

# --- 3. Loop clients ---
for client_name in client_names:
    print("=" * 40)
    print(f"🔍 Processing client: {client_name}")

    # Find parent org-unit
    parent = next(
        (item for item in hierarchy.values() if item.get("name", "").lower() == client_name.lower()),
        None
    )

    if not parent:
        print(f"⚠️  Not found in hierarchy: {client_name}")
        continue

    parent_id = parent["azId"]

    # Build payload
    payload = {
        "type": "predefined",
        "parentId": parent_id,
        "categories": [],
        "data": {
            "mdId": thailand_md_id
        }
    }

    # Call API
    create_resp = requests.post(create_url, headers=headers, cookies=cookies, json=payload)
    if create_resp.status_code == 201:
        print(f"✅ Successfully created Thailand org-unit under {client_name}")
    else:
        print(f"❌ Failed for {client_name}: {create_resp.status_code}")
        try:
            print(create_resp.json())
        except:
            print(create_resp.text)

output_file.close()