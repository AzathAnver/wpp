import requests
import json
from dotenv import load_dotenv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# ---------- Config ----------
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\group\output\output1.txt"
ENV_PATH = r"C:\Users\Azath.A\os\auth.env"
BRANDS_FILE = r"C:\Users\Azath.A\os\group\brands.txt"

TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"

# concurrency / retries
MAX_WORKERS = 10         # change to suit your network/API limits
MAX_RETRIES = 3
BACKOFF_BASE = 1.0       # seconds (exponential backoff: base * 2**attempt)

# Role IDs (unchanged)
ROLE_HIERARCHY = "1544916c-0ce0-4042-a8e5-6e18042c73b7"
ROLE_ARCHITECT = "6948d8e6-eca6-4c12-9241-a47db34db467"
ROLE_CGOVSTANDARD = "9e7c812c-c063-4613-9776-31f635bd1c03"

# ---------- Setup logging (thread-safe print) ----------
output_file = open(OUTPUT_FILE_PATH, "w", encoding="utf-8")
_print_lock = Lock()
_original_print = print

def print(*args, **kwargs):
    with _print_lock:
        _original_print(*args, **kwargs)
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        output_file.write(sep.join(map(str, args)) + end)
        output_file.flush()

# ---------- Load environment ----------
load_dotenv(dotenv_path=ENV_PATH)
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")
if not BEARER_TOKEN or not SESSION_COOKIE:
    print("❌ BEARER_TOKEN or SESSION_COOKIE not found in env. Exiting.")
    output_file.close()
    sys.exit(1)

# ---------- Utility: retry wrapper ----------
def retry_request(fn, *args, **kwargs):
    """Simple retry with exponential backoff. fn should raise exceptions on failure."""
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last = (attempt == MAX_RETRIES - 1)
            wait = BACKOFF_BASE * (2 ** attempt)
            print(f"⚠️ Request failed ({exc}) — attempt {attempt + 1}/{MAX_RETRIES}{' — giving up' if last else f' — retrying in {wait:.1f}s'}")
            if last:
                raise
            time.sleep(wait)

# ---------- Worker functions (use session local to thread) ----------
def get_session():
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "python-requests/2.31"
    })
    s.cookies.update({"session": SESSION_COOKIE})
    return s

def get_azid_for_brand(session, brand_name):
    url = f"https://media.os.wpp.com/api/v2/tenants/{TENANT_ID}/hierarchy-tree"
    def req():
        r = session.get(url, timeout=20)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Hierarchy API failed: {r.status_code} - {r.text}")
        return r.json()
    data = retry_request(req)
    return next(
        (item.get("azId") for item in data.get("mapping", {}).values()
         if item.get("name", "").strip().lower() == brand_name.strip().lower()),
        None
    )

def check_group_exists(session, brand_name):
    url = f"https://media.os.wpp.com/api/tenants/{TENANT_ID}/groups"
    params = {"page": 1, "itemsPerPage": 50, "sort": "name", "filter[search]": brand_name}
    def req():
        r = session.get(url, params=params, timeout=20)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Groups API failed: {r.status_code} - {r.text}")
        return r.json()
    data = retry_request(req)
    return [g for g in data.get("data", []) if g.get("name", "").strip().lower() == brand_name.strip().lower()]

def create_group(session, brand_name, account_uid):
    url = "https://media.os.wpp.com/api/az/groups"
    payload = {"account_uid": account_uid, "name": brand_name, "description": f"Client : {brand_name}", "custom_data": {}}
    def req():
        r = session.post(url, json=payload, timeout=20)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Create group failed: {r.status_code} - {r.text}")
        return r.json()
    return retry_request(req)

def patch_group_users(session):
    url = "https://media.os.wpp.com/api/az/groups/users"
    payload = {"create": [], "delete": []}
    def req():
        r = session.patch(url, json=payload, timeout=20)
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f"Patch users failed: {r.status_code} - {r.text}")
        return r.text if r.text else "{}"
    return retry_request(req)

def patch_group_roles(session, group_uid, account_uid):
    url = "https://media.os.wpp.com/api/az/groups/roles"
    payload = {
        "create": [
            {"group_id": group_uid, "role_id": ROLE_HIERARCHY, "account_id": account_uid},
            {"group_id": group_uid, "role_id": ROLE_CGOVSTANDARD, "account_id": account_uid},
            {"group_id": group_uid, "role_id": ROLE_ARCHITECT, "account_id": account_uid},
        ],
        "delete": []
    }
    def req():
        r = session.patch(url, json=payload, timeout=20)
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f"Patch roles failed: {r.status_code} - {r.text}")
        try:
            return r.json() if r.text else {}
        except ValueError:
            return {}
    return retry_request(req)

# ---------- Worker that processes a single brand ----------
def process_brand(brand_name, stats):
    """Process a single brand. stats is a dict used to update counters (thread-safe via Lock in outer scope)."""
    session = get_session()
    try:
        print(f"\n🔎 Processing brand: {brand_name}")

        # Step 1
        try:
            account_uid = get_azid_for_brand(session, brand_name)
        except Exception as e:
            print(f"❌ Failed to fetch azId for '{brand_name}': {e}")
            with stats_lock:
                stats["failed"] += 1
            return

        if not account_uid:
            print(f"⚠️ No azId found for '{brand_name}' in hierarchy tree. Skipping.")
            with stats_lock:
                stats["skipped_no_azid"] += 1
            return

        # Step 2
        try:
            groups = check_group_exists(session, brand_name)
        except Exception as e:
            print(f"❌ Failed to check groups for '{brand_name}': {e}")
            with stats_lock:
                stats["failed"] += 1
            return

        if groups:
            # assign roles to each existing group
            for g in groups:
                group_uid = g.get("id") or g.get("uid") or g.get("group_uid") or g.get("groupId")
                if not group_uid:
                    print(f"⚠️ Could not determine UID for existing group object: {g}. Skipping this group entry.")
                    continue
                existing_account_uid = g.get("account_uid") or g.get("accountId") or g.get("account_id") or account_uid
                print(f"📂 Found existing group → uid: {group_uid} | name: {g.get('name')}")
                try:
                    resp = patch_group_roles(session, group_uid, existing_account_uid)
                    print(f"🔑 Roles patched for existing group {group_uid}. Response: {resp if resp else '(no content)'}")
                except Exception as e:
                    print(f"❌ Failed to patch roles for existing group {group_uid}: {e}")
                    # continue to next group
            with stats_lock:
                stats["updated_existing"] += 1
            return

        # Step 3: create group
        try:
            group = create_group(session, brand_name, account_uid)
            group_uid = group.get("uid") or group.get("id") or group.get("group_uid") or group.get("groupId")
            print(f"✅ Created group → uid: {group_uid}, name: {group.get('name')}")
        except Exception as e:
            print(f"❌ Failed to create group for '{brand_name}': {e}")
            with stats_lock:
                stats["failed"] += 1
            return

        # Step 4: patch users (noop)
        try:
            patch_group_users(session)
            print("👤 Patched users (noop).")
        except Exception as e:
            print(f"❌ Failed to patch users for '{brand_name}': {e}")

        # Step 5: patch roles
        try:
            roles = patch_group_roles(session, group_uid, account_uid)
            print(f"🔑 Patched roles successfully → {roles if roles else '(no content)'}")
            with stats_lock:
                stats["created_and_assigned"] += 1
        except Exception as e:
            print(f"❌ Failed to patch roles for '{brand_name}': {e}")
            with stats_lock:
                stats["failed"] += 1

    finally:
        session.close()

# ---------- Main: read brands + run ThreadPool ----------
try:
    with open(BRANDS_FILE, "r", encoding="utf-8") as f:
        brand_list = [line.strip() for line in f if line.strip()]
except Exception as e:
    print(f"❌ Unable to open brands file: {e}")
    output_file.close()
    sys.exit(1)

total = len(brand_list)
if total == 0:
    print("⚠️ No brands to process. Exiting.")
    output_file.close()
    sys.exit(0)

# stats
stats = {"failed": 0, "skipped_no_azid": 0, "updated_existing": 0, "created_and_assigned": 0}
stats_lock = Lock()

print(f"🚀 Starting processing of {total} brands using up to {MAX_WORKERS} workers...")

with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, total)) as executor:
    future_to_brand = {executor.submit(process_brand, brand, stats): brand for brand in brand_list}
    completed = 0
    for future in as_completed(future_to_brand):
        brand = future_to_brand[future]
        try:
            future.result()
        except Exception as exc:
            print(f"❌ Unhandled exception for {brand}: {exc}")
            with stats_lock:
                stats["failed"] += 1
        completed += 1
        print(f"📊 Progress: {completed}/{total} completed.")

# final stats
print("\n✅ All done.")
print(f"Total brands: {total}")
print(f"Created & roles assigned: {stats['created_and_assigned']}")
print(f"Existing groups updated (roles assigned): {stats['updated_existing']}")
print(f"Skipped (no azId): {stats['skipped_no_azid']}")
print(f"Failed: {stats['failed']}")

# cleanup
output_file.close()
