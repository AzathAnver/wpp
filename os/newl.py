import requests
import pandas as pd
from dotenv import load_dotenv
import os

# --- Setup ---
tenant_id = "4c039217-7d17-4207-8314-98348983718a"
url = f"https://media.os.wpp.com/api/v2/tenants/{tenant_id}/hierarchy-tree"

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

# --- API Request ---
response = requests.get(url, headers=headers, cookies=cookies)

if response.status_code == 200:
    data = response.json()

    # Load brand names dynamically from txt file
    txt_file_path = r"C:\Users\Azath.A\downloads\brands.txt"
    with open(txt_file_path, "r", encoding="utf-8") as file:
        brand_names = [line.strip() for line in file if line.strip()]

    # Perform case-insensitive search for each brand
    for search_name in brand_names:
        matching_item = next(
            (item for item in data.get("mapping", {}).values()
             if item.get("name", "").lower() == search_name.lower()),
            None
        )

        if matching_item:
            print(f"🎉 Found '{search_name}': azId = {matching_item.get('azId')}")
        else:
            print(f"⚠️ '{search_name}' not found in response.")
else:
    print(f"❌ Request failed: {response.status_code} - {response.text}")