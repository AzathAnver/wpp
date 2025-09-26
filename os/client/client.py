import requests
import pandas as pd
from dotenv import load_dotenv
import os
import re
import sys

# === FILE PATHS ===
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\client\output\output.txt"
INPUT_FILE_PATH = r"C:\Users\Azath.A\os\client\name.txt"
ENV_PATH = r"C:\Users\Azath.A\os\auth.env"

TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"

# === File Logging Setup ===
output_file = open(OUTPUT_FILE_PATH, "w", encoding="utf-8")
_original_print = print
def print(*args, **kwargs):
    """Print to console AND to log file at once."""
    _original_print(*args, **kwargs)
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    output_file.write(sep.join(map(str, args)) + end)
    output_file.flush()

# === Environment Variables ===
load_dotenv(dotenv_path=ENV_PATH)
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")

if not BEARER_TOKEN:
    sys.exit("❌ Missing BEARER_TOKEN in environment file.")

# === HTTP Session Setup ===
session = requests.Session()
headers = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "authorization": f"Bearer {BEARER_TOKEN}",
    "user-agent": "Mozilla/5.0"
}
if SESSION_COOKIE:
    session.headers.update({"cookie": SESSION_COOKIE})
session.headers.update(headers)

# === Helper: Normalized String Comparison ===
def normalize_name(name: str) -> str:
    """Normalize client name for case-insensitive, whitespace-tolerant comparison."""
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)  # collapse multiple spaces
    return name

# === Load Client Names from File ===
ext = os.path.splitext(INPUT_FILE_PATH)[1].lower()
if ext == ".csv":
    df = pd.read_csv(INPUT_FILE_PATH)
    if "ClientName" not in df.columns:
        raise ValueError("CSV file must contain a 'ClientName' column.")
    client_names = df["ClientName"].dropna().tolist()
elif ext == ".txt":
    with open(INPUT_FILE_PATH, "r", encoding="utf-8") as f:
        client_names = [line.strip() for line in f if line.strip()]
else:
    raise ValueError("File must be CSV or TXT.")

# === Process Each Client ===
for client_name in client_names:
    print(f"\n🔍 Processing client: {client_name}")

    search_url = (
        f"https://media.os.wpp.com/api/clients"
        f"?page=1&itemsPerPage=50&filter[search]={client_name}"
    )
    resp = session.get(search_url)
    if resp.status_code != 200:
        print(f"❌ Failed to search client {client_name}: {resp.status_code}")
        continue

    data = resp.json()
    results = data.get("data", [])
    if not results:
        print(f"⚠️ Client '{client_name}' not found in API search.")
        continue

    # Try to find an EXACT normalized match
    normalized_input = normalize_name(client_name)
    matched = next(
        (item for item in results if normalize_name(item["name"]) == normalized_input),
        None
    )

    if not matched:
        print(f"⚠️ No exact match found for '{client_name}'. Closest API hit: {results[0]['name']}")
        continue

    client_id = matched["id"]
    print(f"✅ Found exact client '{client_name}' with mdId: {client_id}")

    # === Step 2: Create Organization Unit ===
    post_url = (
        f"https://media.os.wpp.com/_apps/os-workspaces/api/tenants/"
        f"{TENANT_ID}/organization-units?disableTenantCache=true"
    )
    payload = {
        "type": "predefined",
        "categories": [],
        "data": {"mdId": client_id}
    }

    resp = session.post(post_url, json=payload)

    if resp.status_code in (200, 201):
        print(f"✅ Successfully created org-unit for '{client_name}' →",
              resp.json().get("status", "LIVE"))
    elif resp.status_code == 409:
        print(f"ℹ️ Org-unit for '{client_name}' already exists → skipping.")
    else:
        print(f"❌ Failed for {client_name}: {resp.status_code}")
        print("Response:", resp.text)

# === Close Log File ===
output_file.close()