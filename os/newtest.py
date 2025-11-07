import os
import sys
import requests
from dotenv import load_dotenv

# ===== Config =====
OUTPUT_FILE_PATH = r"C:\Users\Azath.A\os\qc\output\output.txt"
TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"
HIERARCHY_URL = f"https://media.os.wpp.com/api/v2/markets?page=1&itemsPerPage=50000&filter%5Btype%5D=COUNTRY&filter"
ENV_PATH = r"C:\Users\Azath.A\os\auth.env"
TIMEOUT = 30
# ===================

# Auth
load_dotenv(dotenv_path=ENV_PATH)
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")

headers = {
    "Accept": "application/json",
    "User-Agent": "python-requests/2.31",
}
if BEARER_TOKEN:
    headers["Authorization"] = f"Bearer {BEARER_TOKEN}"
cookies = {"session": SESSION_COOKIE} if SESSION_COOKIE else {}

def main():
    # Fetch the hierarchy-tree response
    try:
        with requests.get(
            HIERARCHY_URL, headers=headers, cookies=cookies, timeout=TIMEOUT, stream=True
        ) as resp:
            resp.raise_for_status()

            # Ensure output directory exists
            os.makedirs(os.path.dirname(OUTPUT_FILE_PATH), exist_ok=True)

            # Write the raw response body exactly as received
            with open(OUTPUT_FILE_PATH, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
