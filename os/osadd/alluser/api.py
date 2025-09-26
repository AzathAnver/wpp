import requests
import pandas as pd
from dotenv import load_dotenv
import os

# Full path to your .env file
env_path = r"C:\Users\Azath.A\os\auth.env"

# Load environment variables from that file
load_dotenv(dotenv_path=env_path)

BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")


# === Setup session ===
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


def get_emails(search_name):
    url = "https://media.os.wpp.com/api/users"
    params = {
        "offset": 0,
        "limit": 50,
        "sortBy": "firstname",
        "orderBy": "asc",
        "filter[search]": search_name,
        "filter[jobTitle]": "",
        "filter[country]": "",
        "filter[department]": "",
        "filter[countryAlpha2Code]": ""
    }

    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    data = resp.json()

    emails = []
    for user in data.get("data", []):
        if "email" in user:
            emails.append(user["email"])
    return emails


if __name__ == "__main__":
    # 🔹 Read search names from txt file
    with open("names.csv", "r", encoding="utf-8") as f:
        search_names = [line.strip() for line in f if line.strip()]

    all_emails = []

    for name in search_names:
        print(f"Fetching results for: {name}")
        try:
            emails = get_emails(name)
            for e in emails:
                all_emails.append({"name": name, "email": e})
        except Exception as ex:
            print(f"❌ Error fetching {name}: {ex}")

    # Save results to CSV
    if all_emails:
        df = pd.DataFrame(all_emails)
        df.to_csv("emails.csv", index=False)
        print("✅ Saved emails to emails.csv")
    else:
        print("⚠️ No results fetched")
