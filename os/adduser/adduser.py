import csv
import requests
import urllib.parse
import logging
from dotenv import load_dotenv
import os
from typing import Optional, Dict, Any
import sys
import json
from collections import deque
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from functools import wraps

# -------------------- CONFIG --------------------
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\adduser\output\output.txt"
env_path = r"C:\Users\Azath.A\os\auth.env"
load_dotenv(dotenv_path=env_path)

BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")

TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"
CSV_FILE_PATH = "input.csv"
BASE_URL = "https://media.os.wpp.com"

# Number of parallel worker threads (set to 10 or 20 as you requested)
WORKERS = 20
# ------------------------------------------------

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Thread-local storage for per-thread session
_thread_local = threading.local()

def get_session() -> requests.Session:
    """Return a thread-local requests.Session configured with headers/cookies."""
    if getattr(_thread_local, "session", None) is None:
        s = requests.Session()
        s.headers.update({
            "Authorization": f"Bearer {BEARER_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "python-requests/2.31"
        })
        # set cookie if cookie name is known; using same key used previously
        s.cookies.set("session_cookie_name", SESSION_COOKIE)
        _thread_local.session = s
    return _thread_local.session

# Thread-safe print to file + console
output_lock = threading.Lock()
output_file = open(OUTPUT_FILE_PATH, "w", encoding="utf-8")
_original_print = print

def safe_print(*args, **kwargs):
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    text = sep.join(map(str, args)) + end
    with output_lock:
        _original_print(*args, **kwargs)
        output_file.write(text)
        output_file.flush()

# Simple retry decorator for network calls
def retry_on_exception(max_retries=3, backoff=1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for i in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    wait = backoff * (2 ** (i - 1))
                    logger.warning(f"Call {func.__name__} failed (attempt {i}/{max_retries}): {e}. Retrying in {wait:.1f}s")
                    time.sleep(wait)
            # final try to raise original exception
            raise last_exc
        return wrapper
    return decorator

# Caches (protected by lock for thread-safety)
cache_lock = threading.Lock()
group_cache: Dict[str, Optional[str]] = {}  # group_name_lower -> group_id or None
user_cache: Dict[str, Optional[Dict[str, Any]]] = {}  # email_lower -> user dict or None

@retry_on_exception(max_retries=3, backoff=0.5)
def fetch_groups_page(search_encoded: str, page: int = 1, items_per_page: int = 50):
    s = get_session()
    url = f"{BASE_URL}/api/tenants/{TENANT_ID}/groups?page={page}&itemsPerPage={items_per_page}&sort=name&filter%5Bsearch%5D={search_encoded}"
    r = s.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def search_group_by_name_once(group_name: str) -> Optional[str]:
    """Search and cache group id by exact name. Will try API and cache result."""
    key = group_name.strip().lower()
    with cache_lock:
        if key in group_cache:
            return group_cache[key]

    encoded_name = urllib.parse.quote(group_name.strip())
    try:
        data = fetch_groups_page(encoded_name, page=1, items_per_page=50)
        found_id = None
        for group in data.get("data", []):
            if group.get("name", "").strip().lower() == group_name.strip().lower():
                found_id = group.get("id")
                break
        with cache_lock:
            group_cache[key] = found_id
        return found_id
    except Exception as e:
        logger.error(f"Error searching group '{group_name}': {e}")
        with cache_lock:
            group_cache[key] = None
        return None

@retry_on_exception(max_retries=3, backoff=0.5)
def fetch_users_page(search_encoded: str, offset: int = 0, limit: int = 50):
    s = get_session()
    url = f"{BASE_URL}/api/users?offset={offset}&limit={limit}&sortBy=firstname&orderBy=asc&filter%5Bsearch%5D={search_encoded}"
    r = s.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def search_user_by_email_cached(email: str) -> Optional[Dict[str, Any]]:
    key = email.strip().lower()
    with cache_lock:
        if key in user_cache:
            return user_cache[key]

    encoded_email = urllib.parse.quote(email.strip())
    try:
        data = fetch_users_page(encoded_email, offset=0, limit=50)
        found_user = None
        for user in data.get("data", []):
            if user.get("email", "").strip().lower() == email.strip().lower():
                found_user = user
                break
        with cache_lock:
            user_cache[key] = found_user
        return found_user
    except Exception as e:
        logger.error(f"Error searching user '{email}': {e}")
        with cache_lock:
            user_cache[key] = None
        return None

def assign_user_to_group(group_id: str, user_email: str) -> bool:
    """Assign a user to group. Returns True on success."""
    s = get_session()
    url = f"{BASE_URL}/api/az/groups/users"
    payload = {
        "create": [{"groupId": group_id, "userId": user_email}],
        "delete": []
    }
    try:
        r = s.patch(url, json=payload, timeout=30)
        if r.status_code in (200, 201, 204):
            logger.info(f"✅ Successfully assigned {user_email} to group {group_id}")
            safe_print(f"SUCCESS: {user_email} -> {group_id}")
            return True
        else:
            logger.error(f"❌ Failed to assign {user_email} to group {group_id}. Status: {r.status_code}, Response: {r.text}")
            safe_print(f"FAILED: {user_email} -> {group_id} Status:{r.status_code} Response:{r.text}")
            return False
    except Exception as e:
        logger.error(f"Exception during PATCH for {user_email}: {e}")
        safe_print(f"ERROR: {user_email} -> {group_id} Exception:{e}")
        return False

def assign_users_by_username(username_part: str, group_id: str, row_num: int):
    logger.info(f"Row {row_num}: Searching users by username fragment: '{username_part}'")
    encoded = urllib.parse.quote(username_part.strip())
    try:
        data = fetch_users_page(encoded, offset=0, limit=50)
        found_any = False
        for user in data.get("data", []):
            email = user.get("email", "").lower()
            logger.info(f"Row {row_num}: Found potential match: {email}")
            assign_user_to_group(group_id, email)
            found_any = True
        if not found_any:
            logger.warning(f"Row {row_num}: No users found for username '{username_part}'")
            safe_print(f"WARNING: Row {row_num}: No users for {username_part} in group {group_id}")
    except Exception as e:
        logger.error(f"Row {row_num}: Error searching users by username '{username_part}': {e}")
        safe_print(f"ERROR: Row {row_num}: search by username {username_part} failed: {e}")

def process_row(row_num: int, raw_group_name: str, raw_user_email: str):
    """Process a single CSV row. This is what runs concurrently."""
    if not raw_group_name or not raw_user_email:
        safe_print(f"Row {row_num}: missing group or user -> skipped")
        return

    safe_print(f"Processing Row {row_num}: Group='{raw_group_name}', User='{raw_user_email}'")
    group_id = search_group_by_name_once(raw_group_name)
    if not group_id:
        logger.warning(f"Row {row_num}: Group '{raw_group_name}' not found. Skipping.")
        safe_print(f"Row {row_num}: Group '{raw_group_name}' not found.")
        return

    # Try direct email match
    user = search_user_by_email_cached(raw_user_email)
    if user:
        assign_user_to_group(group_id, raw_user_email)
    else:
        # Fallback: username before @
        if "@" in raw_user_email:
            username_part = raw_user_email.split("@", 1)[0].strip()
            if username_part:
                assign_users_by_username(username_part, group_id, row_num)
            else:
                logger.warning(f"Row {row_num}: Could not extract username from '{raw_user_email}'. Skipping.")
                safe_print(f"Row {row_num}: Could not extract username from '{raw_user_email}'. Skipping.")
        else:
            logger.warning(f"Row {row_num}: Invalid email format '{raw_user_email}'. Skipping.")
            safe_print(f"Row {row_num}: Invalid email format '{raw_user_email}'. Skipping.")

def preload_group_cache_from_csv(csv_path: str):
    """Scan the CSV and preload group ids for unique group names (faster later)."""
    unique_groups = set()
    with open(csv_path, mode='r', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if len(row) >= 1:
                group = row[0].strip()
                if group:
                    unique_groups.add(group)
    safe_print(f"Preloading {len(unique_groups)} unique groups...")
    for g in unique_groups:
        # This will cache every group (including None for not found)
        try:
            search_group_by_name_once(g)
        except Exception as e:
            logger.exception(f"Error preloading group '{g}': {e}")

def main():
    # preload groups (search each group only once)
    preload_group_cache_from_csv(CSV_FILE_PATH)

    # Read rows to process
    rows_to_process = []
    with open(CSV_FILE_PATH, mode='r', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        for row_num, row in enumerate(reader, start=1):
            # Skip if row is completely empty
            if len(row) == 0 or all(cell.strip() == "" for cell in row):
                continue
            if len(row) < 2:
                if any(cell.strip() for cell in row):
                    logger.warning(f"Row {row_num}: Malformed row (expected 2 columns, got {len(row)}): {row}")
                continue
            raw_group_name = row[0].strip()
            raw_user_email = row[1].strip()
            if not raw_group_name and not raw_user_email:
                continue
            rows_to_process.append((row_num, raw_group_name, raw_user_email))

    safe_print(f"Starting ThreadPoolExecutor with {WORKERS} workers for {len(rows_to_process)} rows...")

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        future_to_row = {executor.submit(process_row, rn, g, u): (rn, g, u) for rn, g, u in rows_to_process}
        for future in as_completed(future_to_row):
            rn, g, u = future_to_row[future]
            try:
                future.result()
            except Exception as e:
                logger.exception(f"Unhandled exception processing Row {rn} ({g}, {u}): {e}")
                safe_print(f"ERROR: Unhandled exception in Row {rn}: {e}")

    safe_print("All done.")
    output_file.close()

if __name__ == "__main__":
    main()
