import os
import requests
from dotenv import load_dotenv

# --- Config ---
TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"
HIERARCHY_URL = f"https://media.os.wpp.com/api/v2/tenants/{TENANT_ID}/hierarchy-tree"

MARKET_NAME = "Germany"  # static market
INPUT_PATH = r"C:\Users\Azath.A\os\ctemp\brands.txt"  # one name per line (client or brand)

# --- Auth ---
ENV_PATH = r"C:\Users\Azath.A\os\auth.env"
load_dotenv(dotenv_path=ENV_PATH)
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
SESSION_COOKIE = os.getenv("SESSION_COOKIE")

headers = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Accept": "application/json",
    "User-Agent": "python-requests/2.31",
}
cookies = {"session": SESSION_COOKIE} if SESSION_COOKIE else {}

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def fetch_tree():
    resp = requests.get(HIERARCHY_URL, headers=headers, cookies=cookies)
    resp.raise_for_status()
    mapping = resp.json().get("mapping", {}) or {}
    # Build indexes
    nodes_by_id = {}
    for node in mapping.values():
        az = node.get("azId")
        if az:
            nodes_by_id[az] = node

    parent_of = {}
    for node in nodes_by_id.values():
        for child in (node.get("children") or []):
            parent_of[child] = node["azId"]

    # Find the Germany market azId
    market_azid = None
    for node in nodes_by_id.values():
        if node.get("type") == "MARKET" and _norm(node.get("name")) == _norm(MARKET_NAME):
            market_azid = node.get("azId")
            break
    if not market_azid:
        raise RuntimeError(f"Market '{MARKET_NAME}' not found in hierarchy.")

    # Name index for CLIENT/BRAND
    name_index = {}
    for node in nodes_by_id.values():
        if node.get("type") in ("CLIENT", "BRAND"):
            name_index.setdefault(_norm(node.get("name")), []).append(node)

    return nodes_by_id, parent_of, name_index, market_azid

def ascend_to_client_if_in_market(start_azid, market_azid, nodes_by_id, parent_of):
    """Walk up parents from start_azid. Return client azId if the chain includes the target market."""
    seen = set()
    current = start_azid
    client_azid = None
    in_market_chain = False

    while current and current not in seen:
        seen.add(current)
        node = nodes_by_id.get(current)
        if not node:
            break
        if node.get("type") == "CLIENT" and client_azid is None:
            client_azid = current
        if current == market_azid:
            in_market_chain = True
        current = parent_of.get(current)

    if in_market_chain and client_azid:
        return client_azid
    return None

def resolve_client_azid_in_market(name, nodes_by_id, parent_of, name_index, market_azid):
    candidates = name_index.get(_norm(name), [])
    # Prefer CLIENT nodes over BRAND nodes when names collide
    candidates.sort(key=lambda n: 0 if n.get("type") == "CLIENT" else 1)
    for cand in candidates:
        client_azid = ascend_to_client_if_in_market(cand.get("azId"), market_azid, nodes_by_id, parent_of)
        if client_azid:
            return client_azid
    return None

def main():
    nodes_by_id, parent_of, name_index, market_azid = fetch_tree()

    # Read a single input file with one name per line (client or brand)
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]

    for name in names:
        client_azid = resolve_client_azid_in_market(name, nodes_by_id, parent_of, name_index, market_azid)
        if client_azid:
            # Only print: clientAzId,marketAzId
            print(f"{client_azid},{market_azid}")

if __name__ == "__main__":
    main()