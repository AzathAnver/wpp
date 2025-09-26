import requests, csv, json
import pandas as pd
from dotenv import load_dotenv
import os
import sys

# Define output file path
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\group\output\output.txt"

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

# --- Setup ---
tenant_id = "4c039217-7d17-4207-8314-98348983718a"

# --- Setup environment ---
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

# --- Static Role IDs ---
ROLE_HIERARCHY = "1544916c-0ce0-4042-a8e5-6e18042c73b7"
ROLE_ARCHITECT = "6948d8e6-eca6-4c12-9241-a47db34db467"

# --- Helper Functions ---

def get_azid_for_brand(brand_name: str):
    """Look up azId (account_uid) for a brand from hierarchy-tree (case-insensitive)."""
    url_hierarchy = f"https://media.os.wpp.com/api/v2/tenants/{tenant_id}/hierarchy-tree"
    r = requests.get(url_hierarchy, headers=headers, cookies=cookies)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Hierarchy API failed: {r.status_code} - {r.text}")
    data = r.json()
    return next(
        (item.get("azId") for item in data.get("mapping", {}).values()
         if item.get("name", "").strip().lower() == brand_name.strip().lower()),
        None
    )

def check_group_exists(brand_name: str):
    """Check if group exists for brand (case-insensitive match)."""
    url_groups = f"https://media.os.wpp.com/api/tenants/{tenant_id}/groups"
    params = {
        "page": 1,
        "itemsPerPage": 50,
        "sort": "name",
        "filter[search]": brand_name
    }
    r = requests.get(url_groups, headers=headers, cookies=cookies, params=params)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Groups API failed: {r.status_code} - {r.text}")
    data = r.json()
    # Make results truly case-insensitive by filtering manually
    return [
        g for g in data.get("data", [])
        if g.get("name", "").strip().lower() == brand_name.strip().lower()
    ]

def create_group(brand_name: str, account_uid: str):
    """Create group in /az/groups."""
    url_post = "https://media.os.wpp.com/api/az/groups"
    payload = {
        "account_uid": account_uid,
        "name": brand_name,
        "description": f"Client : {brand_name}",
        "custom_data": {}
    }
    r = requests.post(url_post, headers=headers, cookies=cookies, json=payload)
    if r.status_code not in (200, 201):  # ✅ 201 is now success
        raise RuntimeError(f"Create group failed: {r.status_code} - {r.text}")
    return r.json()


def patch_group_users():
    """Patch users endpoint (empty payload for now)."""
    url_patch_users = "https://media.os.wpp.com/api/az/groups/users"
    payload = {"create": [], "delete": []}
    r = requests.patch(url_patch_users, headers=headers, cookies=cookies, json=payload)
    if r.status_code not in (200, 201, 204):  # ✅ accept 201/204 too
        raise RuntimeError(f"Patch users failed: {r.status_code} - {r.text}")
    return r.text if r.text else "{}"  # return at least an empty JSON string


def patch_group_roles(group_uid: str, account_uid: str):
    """Patch roles for a group (Hierarchy & Architect)."""
    url_patch_roles = "https://media.os.wpp.com/api/az/groups/roles"
    payload = {
        "create": [
            {
                "group_id": group_uid,
                "role_id": ROLE_HIERARCHY,
                "account_id": account_uid
            },
            {
                "group_id": group_uid,
                "role_id": ROLE_ARCHITECT,
                "account_id": account_uid
            }
        ],
        "delete": []
    }
    r = requests.patch(url_patch_roles, headers=headers, cookies=cookies, json=payload)
    if r.status_code not in (200, 201, 204):  # ✅ handle all success statuses
        raise RuntimeError(f"Patch roles failed: {r.status_code} - {r.text}")
    return r.json() if r.text else {}

# --- Main Workflow ---
txt_file_path = r"C:\Users\Azath.A\os\group\brands.txt"
with open(txt_file_path, "r", encoding="utf-8") as file:
    brand_names = [line.strip() for line in file if line.strip()]

for brand_name in brand_names:
    print(f"\n🔎 Processing brand: {brand_name}")

    # Step 1: Get azId (account_uid) with error handling
    try:
        account_uid = get_azid_for_brand(brand_name)
    except RuntimeError as e:
        print(f"❌ Failed to fetch azId for '{brand_name}': {e}")
        continue

    if not account_uid:
        print(f"⚠️ No azId found for '{brand_name}' in hierarchy tree. Skipping.")
        continue

    # Step 2: Check if group already exists
    try:
        groups = check_group_exists(brand_name)
    except RuntimeError as e:
        print(f"❌ Failed to check groups for '{brand_name}': {e}")
        continue

    if groups:
        for g in groups:
            print(f"📂 Group already exists → id: {g['id']} | name: {g['name']}")
        continue

    # Step 3: Create new group
    try:
        group = create_group(brand_name, account_uid)
        group_uid = group["uid"]
        print(f"✅ Created group → uid: {group_uid}, name: {group['name']}")
    except Exception as e:
        print(f"❌ Failed to create group for '{brand_name}': {e}")
        continue

    # Step 4: Patch users (noop)
    try:
        patch_group_users()
        print("👤 Patched users (noop).")
    except Exception as e:
        print(f"❌ Failed to patch users for '{brand_name}': {e}")

    # Step 5: Patch roles
    try:
        roles = patch_group_roles(group_uid, account_uid)
        print(f"🔑 Patched roles successfully → {len(roles)} roles assigned.")
    except Exception as e:
        print(f"❌ Failed to patch roles for '{brand_name}': {e}")
output_file.close()