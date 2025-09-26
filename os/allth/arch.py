import requests
from dotenv import load_dotenv
import os

# --- Configuration ---
TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"
HIERARCHY_URL = f"https://media.os.wpp.com/api/v2/tenants/{TENANT_ID}/hierarchy-tree"
PATCH_URL = "https://media.os.wpp.com/api/az/groups/roles"

# Static group and role IDs
STATIC_GROUP_ID = "9d3aa2cf-2211-4d34-a844-32b63dcc80c2"
STATIC_ROLE_ID = "1544916c-0ce0-4042-a8e5-6e18042c73b7"

# --- Load environment ---
env_path = r"C:\Users\Azath.A\os\auth.env"
load_dotenv(dotenv_path=env_path)

BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")

if not BEARER_TOKEN or not SESSION_COOKIE:
    raise ValueError("❌ Missing BEARER_TOKEN or SESSION_COOKIE in .env file")

HEADERS = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "python-requests/2.31"
}

COOKIES = {
    "session": SESSION_COOKIE
}

# --- Step 1: Fetch hierarchy to get account_uid (azId) for each brand ---
print("🔍 Fetching hierarchy data...")
response = requests.get(HIERARCHY_URL, headers=HEADERS, cookies=COOKIES)

if response.status_code != 200:
    print(f"❌ Failed to fetch hierarchy: {response.status_code} - {response.text}")
    exit(1)

data = response.json()
mapping = data.get("mapping", {})

# --- Step 2: Read brand names from file ---
txt_file_path = r"C:\Users\Azath.A\os\clientgroup\brands.txt"
try:
    with open(txt_file_path, "r", encoding="utf-8") as file:
        brand_names = [line.strip() for line in file if line.strip()]
except FileNotFoundError:
    print(f"❌ brands.txt not found at {txt_file_path}")
    exit(1)

print(f"📄 Loaded {len(brand_names)} brand(s) from file.")

# --- Step 3: Match brands to account_uids ---
accounts_to_assign = []

for brand in brand_names:
    matched_item = next(
        (item for item in mapping.values()
         if item.get("name", "").lower() == brand.lower()),
        None
    )

    if matched_item:
        account_uid = matched_item.get("azId")
        if account_uid:
            accounts_to_assign.append({
                "brand_name": brand,
                "account_id": account_uid
            })
            print(f"✅ Matched '{brand}' → account_uid: {account_uid}")
        else:
            print(f"⚠️ No azId found for brand: {brand}")
    else:
        print(f"⚠️ Brand '{brand}' not found in hierarchy.")

if not accounts_to_assign:
    print("🚫 No valid accounts found to assign. Exiting.")
    exit(0)

# --- Step 4: Assign roles ONE BY ONE ---
print(f"\n🚀 Starting individual assignments for {len(accounts_to_assign)} account(s)...")

success_count = 0
skip_count = 0
fail_count = 0

for item in accounts_to_assign:
    brand_name = item["brand_name"]
    account_id = item["account_id"]

    payload = {
        "create": [{
            "group_id": STATIC_GROUP_ID,
            "role_id": STATIC_ROLE_ID,
            "account_id": account_id
        }],
        "delete": []
    }

    print(f"\n➡️  Processing: {brand_name} (account_id: {account_id})")
    patch_response = requests.patch(PATCH_URL, headers=HEADERS, cookies=COOKIES, json=payload)

    if patch_response.status_code == 201:
        result = patch_response.json()
        assigned = result[0]  # assuming one item returned
        print(f"🎉 SUCCESS: Assigned role to {brand_name}")
        print(f"   ➤ UID: {assigned['uid']}, Group: {assigned['group_uid']}, Account: {assigned['account_uid']}")
        success_count += 1

    elif patch_response.status_code == 422:
        error_detail = patch_response.json().get("message", "Unknown error")
        print(f"🔶 ALREADY EXISTS (422): {error_detail}")
        skip_count += 1

    else:
        print(f"❌ FAILED ({patch_response.status_code}): {patch_response.text}")
        fail_count += 1

# --- Final Summary ---
print("\n" + "="*60)
print("✅ ASSIGNMENT SUMMARY:")
print(f"   Success: {success_count}")
print(f"   Skipped (Already Exists): {skip_count}")
print(f"   Failed: {fail_count}")
print("="*60)