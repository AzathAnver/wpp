import requests
import time
from datetime import datetime
from dotenv import load_dotenv
import os

# --- Setup environment ---
env_path = r"C:\Users\Azath.A\os\auth.env"
load_dotenv(dotenv_path=env_path)

BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKI = os.getenv("SESSION_COOKIE")

headers = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Accept": "application/json",
    "User-Agent": "python-requests/2.31"
}

cookies = {
    "session": SESSION_COOKI
}


API_URL = "https://media.os.wpp.com/api/feeds/status"

while True:
    try:
        response = requests.get(API_URL, headers=headers, cookies=cookies)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{current_time} | Status code: {response.status_code}")
    except Exception as e:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{current_time} | Error: {e}")
    time.sleep(60)