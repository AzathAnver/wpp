import csv
import requests
import urllib.parse
import logging
from dotenv import load_dotenv
import os
from typing import Optional, Dict, Any


# --- Setup environment ---
env_path = r"C:\Users\Azath.A\os\auth.env"
load_dotenv(dotenv_path=env_path)

BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")

headers = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Accept": "application/json",
    "User-Agent": "python-requests/2.31"
}

cookies = {
    "session": SESSION_COOKIE
}

TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"
CSV_FILE_PATH = "input.csv"
BASE_URL = "https://media.os.wpp.com"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Session setup
session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json"
})
session.cookies.set("session_cookie_name", SESSION_COOKIE)  # Update cookie name if known


def search_group_by_name(group_name: str) -> Optional[str]:
    encoded_name = urllib.parse.quote(group_name.strip())
    url = f"{BASE_URL}/api/tenants/{TENANT_ID}/groups?page=1&itemsPerPage=50&sort=name&filter%5Bsearch%5D={encoded_name}"

    try:
        response = session.get(url)
        response.raise_for_status()
        data = response.json()

        for group in data.get("data", []):
            if group["name"].lower() == group_name.strip().lower():
                return group["id"]
        return None
    except Exception as e:
        logger.error(f"Error searching group '{group_name}': {e}")
        return None


def search_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    encoded_email = urllib.parse.quote(email.strip())
    url = f"{BASE_URL}/api/users?offset=0&limit=50&sortBy=firstname&orderBy=asc&filter%5Bsearch%5D={encoded_email}"

    try:
        response = session.get(url)
        response.raise_for_status()
        data = response.json()

        for user in data.get("data", []):
            if user.get("email", "").lower() == email.strip().lower():
                return user
        return None
    except Exception as e:
        logger.error(f"Error searching user '{email}': {e}")
        return None


def assign_user_to_group(group_id: str, user_email: str):
    url = f"{BASE_URL}/api/az/groups/users"
    payload = {
        "create": [{"groupId": group_id, "userId": user_email}],
        "delete": []
    }

    try:
        response = session.patch(url, json=payload)

        # ✅ Accept 200, 201, 204 as success
        if response.status_code in (200, 201, 204):
            logger.info(f"✅ Successfully assigned {user_email} to group {group_id}")
        else:
            logger.error(f"❌ Failed to assign {user_email} to group {group_id}. Status: {response.status_code}, Response: {response.text}")

    except Exception as e:
        logger.error(f"Exception during PATCH for {user_email}: {e}")


def assign_users_by_username(username_part: str, group_id: str, row_num: int):
    """
    Search users by partial name (username before @), assign all matches to group.
    """
    logger.info(f"Row {row_num}: Searching users by username fragment: '{username_part}'")
    url = f"{BASE_URL}/api/users?offset=0&limit=50&sortBy=firstname&orderBy=asc&filter%5Bsearch%5D={urllib.parse.quote(username_part)}"

    try:
        response = session.get(url)
        response.raise_for_status()
        data = response.json()

        found_any = False
        for user in data.get("data", []):
            email = user.get("email", "").lower()
            # Optional: you can match username part exactly if needed
            # But usually, search API already does fuzzy match
            logger.info(f"Row {row_num}: Found potential match: {email}")
            assign_user_to_group(group_id, email)
            found_any = True

        if not found_any:
            logger.warning(f"Row {row_num}: No users found for username '{username_part}'")

    except Exception as e:
        logger.error(f"Row {row_num}: Error searching users by username '{username_part}': {e}")


def main():
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

            # Skip if BOTH are empty
            if not raw_group_name and not raw_user_email:
                continue

            if not raw_group_name:
                logger.warning(f"Row {row_num}: Group name missing. Skipping.")
                continue
            if not raw_user_email:
                logger.warning(f"Row {row_num}: User email missing. Skipping.")
                continue

            logger.info(f"Processing Row {row_num}: Group='{raw_group_name}', User='{raw_user_email}'")

            group_id = search_group_by_name(raw_group_name)
            if not group_id:
                logger.warning(f"Row {row_num}: Group '{raw_group_name}' not found. Skipping.")
                continue

            # First: Try direct email match
            user = search_user_by_email(raw_user_email)
            if user:
                assign_user_to_group(group_id, raw_user_email)
            else:
                # Fallback: Extract username part (before @) and search broadly
                if "@" in raw_user_email:
                    username_part = raw_user_email.split("@")[0].strip()
                    if username_part:
                        assign_users_by_username(username_part, group_id, row_num)
                    else:
                        logger.warning(f"Row {row_num}: Could not extract username from '{raw_user_email}'. Skipping.")
                else:
                    logger.warning(f"Row {row_num}: Invalid email format '{raw_user_email}'. Skipping.")


if __name__ == "__main__":
    main()