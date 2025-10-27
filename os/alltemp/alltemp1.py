import os
import sys
from typing import Dict, Any, Optional, List, Tuple
import csv
import requests
from dotenv import load_dotenv

# --------------------
# Config
# --------------------
TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"
TEMPLATE_ID = "271dc22b-ab65-4461-82fb-2dd923dc5ab0"
APPLY_URL = f"https://media.os.wpp.com/api/app-instances/templates/{TEMPLATE_ID}/apply/bulk"

# App instances (unchanged)
APP_INSTANCE_IDS = ["5be2e99a-f1dd-4bf1-ba39-97197186fc1f"]

# CSV path (can be overridden by CLI arg)
CLIENTS_CSV_PATH = r"C:\Users\Azath.A\os\alltemp\clients.csv"

ENV_PATH = r"C:\Users\Azath.A\os\auth.env"

# Optional: also log to file
LOG_PATH = r"C:\Users\Azath.A\os\alltemp\output\output.txt"
log_file = None

def log(msg: str):
    print(msg)
    if log_file:
        log_file.write(msg + "\n")
        log_file.flush()

# --------------------
# Auth / Session
# --------------------
def get_session() -> requests.Session:
    load_dotenv(dotenv_path=ENV_PATH)
    token = os.getenv("BEARER_TOKEN")
    session_cookie = os.getenv("SESSION_COOKIE")
    if not token or not session_cookie:
        raise RuntimeError("Missing BEARER_TOKEN or SESSION_COOKIE in auth.env")
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "python-requests/2.31"
    })
    s.cookies.set("session", session_cookie)
    return s

# --------------------
# GET hierarchy
# --------------------
def fetch_hierarchy(session: requests.Session) -> Dict[str, Any]:
    url = f"https://media.os.wpp.com/api/v2/tenants/{TENANT_ID}/hierarchy-tree"
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    mapping = data.get("mapping", {})
    if not isinstance(mapping, dict) or not mapping:
        raise RuntimeError("Hierarchy mapping is empty or invalid.")
    return mapping

# --------------------
# Resolution logic
# --------------------
def find_client_or_brand_node(mapping: Dict[str, Dict[str, Any]], client_name: str) -> Optional[Dict[str, Any]]:
    name_lc = client_name.strip().lower()
    matches_client = [n for n in mapping.values()
                      if n.get("type") == "CLIENT" and (n.get("name") or "").strip().lower() == name_lc]
    if matches_client:
        return matches_client[0]
    matches_brand = [n for n in mapping.values()
                     if n.get("type") == "BRAND" and (n.get("name") or "").strip().lower() == name_lc]
    return matches_brand[0] if matches_brand else None

def get_parent_market_azid(mapping: Dict[str, Dict[str, Any]], market_name: str, client_name: str) -> str:
    """
    Resolve the market azId for a given client/brand:
      - find MARKET nodes named <market_name>
      - find CLIENT/BRAND nodes named <client_name>
      - if a market has the client in its children -> return that market azId
      - else if a client has the market in its children -> return that market azId
      - else raise
    """
    mkt_name_lc = market_name.strip().lower()
    client_name_lc = client_name.strip().lower()

    market_nodes = {
        node["azId"]: node
        for node in mapping.values()
        if node.get("type") == "MARKET"
        and (node.get("name") or "").strip().lower() == mkt_name_lc
    }

    client_nodes = {
        node["azId"]: node
        for node in mapping.values()
        if node.get("type") in ("CLIENT", "BRAND")
        and (node.get("name") or "").strip().lower() == client_name_lc
    }

    # Market -> has child = client
    for m_id, m_node in market_nodes.items():
        for child in m_node.get("children", []) or []:
            if child in client_nodes:
                return m_id

    # Client -> has child = market
    for c_id, c_node in client_nodes.items():
        for child in c_node.get("children", []) or []:
            if child in market_nodes:
                return child

    raise ValueError(f"Market '{market_name}' with client '{client_name}' not found.")

# --------------------
# POST apply
# --------------------
def apply_template(session: requests.Session, assignment_id: str) -> (int, Any):
    payload = {
        "appInstanceIds": APP_INSTANCE_IDS,
        "linkToHierarchy": True,
        "assignments": [
            {
                "assignmentId": assignment_id,
                "assignmentType": "WORKSPACE"
            }
        ]
    }
    resp = session.post(APPLY_URL, json=payload, timeout=90)
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return resp.status_code, body

def is_empty_error(body) -> bool:
    text = ""
    if isinstance(body, dict):
        detail = body.get("detail") or ""
        text = f"{detail} {' '.join(str(v) for v in body.values())}"
    else:
        text = str(body)
    return "should be empty" in text.lower()

# --------------------
# CSV loader
# --------------------
def load_clients_and_markets(csv_path: str) -> List[Tuple[str, str]]:
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Clients CSV not found: {csv_path}")

    rows: List[Tuple[str, str]] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            has_header = csv.Sniffer().has_header(sample)
        except Exception:
            has_header = True  # assume header if unsure

        if has_header:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise RuntimeError("CSV has header but no fieldnames detected.")
            fields_map = {name.strip().lower(): name for name in reader.fieldnames}
            client_key = None
            for k in ("clientname", "client", "brand", "brandname"):
                if k in fields_map:
                    client_key = fields_map[k]
                    break
            market_key = None
            for k in ("market", "marketname", "country"):
                if k in fields_map:
                    market_key = fields_map[k]
                    break
            if not client_key or not market_key:
                raise RuntimeError(f"CSV must contain headers 'clientname' and 'market' (found: {reader.fieldnames})")
            for row in reader:
                c = (row.get(client_key) or "").strip()
                m = (row.get(market_key) or "").strip()
                if c and m:
                    rows.append((c, m))
        else:
            reader = csv.reader(f)
            for idx, row in enumerate(reader, start=1):
                if len(row) < 2:
                    log(f"⚠️ Skipping row {idx}: expected 2 columns (client, market). Got: {row}")
                    continue
                c = (row[0] or "").strip()
                m = (row[1] or "").strip()
                if c and m:
                    rows.append((c, m))
    return rows

# --------------------
# Main
# --------------------
def main():
    global log_file
    # Optional logging to file
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        log_file = open(LOG_PATH, "w", encoding="utf-8")
    except Exception:
        log_file = None  # proceed without file logging

    try:
        session = get_session()
        mapping = fetch_hierarchy(session)

        # Allow override via CLI: python script.py path\to\clients.csv
        csv_path = sys.argv[1] if len(sys.argv) > 1 else CLIENTS_CSV_PATH

        try:
            client_market_rows = load_clients_and_markets(csv_path)
        except Exception as e:
            log(f"❌ {e}")
            sys.exit(1)

        if not client_market_rows:
            log("⚠️ No client/market rows found in the CSV file.")
            sys.exit(0)

        log(f"🔧 Will process {len(client_market_rows)} row(s) from CSV: {csv_path}\n")

        for client_name, market_name in client_market_rows:
            log(f"— Processing client: {client_name} (market: {market_name})")

            # First assignment: client/brand node azId
            client_node = find_client_or_brand_node(mapping, client_name)
            if not client_node or not client_node.get("azId"):
                log(f"   ⚠️ Client/Brand node not found for '{client_name}'. Skipping.")
                continue
            first_assignment_id = client_node["azId"]
            log(f"   ✅ First assignmentId (client/brand): {first_assignment_id}")

            # Second assignment: market azId from CSV per-row
            try:
                second_assignment_id = get_parent_market_azid(mapping, market_name, client_name)
                log(f"   ✅ Second assignmentId (market={market_name}): {second_assignment_id}")
            except Exception as e:
                log(f"   ⚠️ Could not resolve market '{market_name}' for '{client_name}': {e}")
                continue

            # POST #1
            code1, body1 = apply_template(session, first_assignment_id)
            ok1 = 200 <= code1 < 300
            log(f"   → POST #1 status: {code1} {'✅' if ok1 else '❌'}")
            if not ok1:
                log(f"     Response: {body1}")

            # POST #2
            code2, body2 = apply_template(session, second_assignment_id)
            ok2 = 200 <= code2 < 300
            log(f"   → POST #2 status: {code2} {'✅' if ok2 else '❌'}")
            if not ok2:
                log(f"     Response: {body2}")

        log("\n🏁 Done.")

    except requests.HTTPError as e:
        log(f"❌ HTTP error: {e.response.status_code} - {e.response.text}")
        sys.exit(1)
    except Exception as e:
        log(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        if log_file:
            log_file.close()

if __name__ == "__main__":
    main()