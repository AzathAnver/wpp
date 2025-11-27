#!/usr/bin/env python3
"""
apply_templates_with_client_map.py

Same as before but logs which CSV client(s) caused each market azId to be processed.
"""

import os
import sys
import csv
import time
import random
import argparse
from typing import Dict, Any, List, Tuple, Optional, Set
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import requests
from dotenv import load_dotenv

# --------------------
# Config (override with CLI / env)
# --------------------
TENANT_ID = "4c039217-7d17-4207-8314-98348983718a"
TEMPLATE_ID = "271dc22b-ab65-4461-82fb-2dd923dc5ab0"  # CGandCP
APPLY_URL = f"https://media.os.wpp.com/api/app-instances/templates/{TEMPLATE_ID}/apply/bulk"

APP_INSTANCE_IDS = ["5be2e99a-f1dd-4bf1-ba39-97197186fc1f", "1209fa17-49be-4c55-9719-ccd320461266"]

CLIENTS_CSV_PATH = r"C:\Users\Azath.A\os\alltemp\clients.csv"
ENV_PATH = r"C:\Users\Azath.A\os\auth.env"
LOG_PATH = r"C:\Users\Azath.A\os\alltemp\output\output.txt"

# Default concurrency / retry settings (tweakable)
DEFAULT_WORKERS = 12
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 0.8  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0

# --------------------
# Helpers / logging
# --------------------
_log_lines = []
_log_lock = threading.Lock()


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts}  {msg}"
    with _log_lock:
        _log_lines.append(line)
    print(line)


def flush_log_to_file(path: str):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(_log_lines))
        log(f"Saved log to {path}")
    except Exception as e:
        log(f"Failed to write log file {path}: {e}")


# --------------------
# Auth / session factory
# --------------------
def load_auth_env(env_path: str):
    load_dotenv(dotenv_path=env_path)
    token = os.getenv("BEARER_TOKEN")
    session_cookie = os.getenv("SESSION_COOKIE")
    if not token or not session_cookie:
        raise RuntimeError("Missing BEARER_TOKEN or SESSION_COOKIE in auth.env")
    return token, session_cookie


def make_session_factory(token: str, session_cookie: str):
    def factory():
        s = requests.Session()
        s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "python-requests/fast-client"
        })
        s.cookies.set("session", session_cookie)
        return s
    return factory


# --------------------
# Hierarchy fetch + resolution
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
            has_header = True

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
# POST + retry logic
# --------------------
def is_empty_error(body) -> bool:
    text = ""
    if isinstance(body, dict):
        detail = body.get("detail") or ""
        text = f"{detail} {' '.join(str(v) for v in body.values())}"
    else:
        text = str(body)
    return "should be empty" in text.lower()


def apply_template_with_retries(session_factory, assignment_id: str,
                               max_retries: int = 3,
                               backoff_base: float = 0.8,
                               backoff_factor: float = 2.0) -> Tuple[str, int, Any]:
    session = session_factory()
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

    attempt = 0
    while attempt <= max_retries:
        attempt += 1
        try:
            resp = session.post(APPLY_URL, json=payload, timeout=90)
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            code = resp.status_code
            if 200 <= code < 300:
                return (assignment_id, code, body)
            else:
                if is_empty_error(body):
                    return (assignment_id, code, body)
                if 500 <= code < 600 and attempt <= max_retries:
                    sleep_for = backoff_base * (backoff_factor ** (attempt - 1))
                    sleep_for = sleep_for * (0.8 + random.random() * 0.4)
                    log(f"Retryable HTTP {code} for {assignment_id} (attempt {attempt}/{max_retries}). Sleeping {sleep_for:.2f}s")
                    time.sleep(sleep_for)
                    continue
                return (assignment_id, code, body)
        except requests.RequestException as e:
            if attempt <= max_retries:
                sleep_for = backoff_base * (backoff_factor ** (attempt - 1))
                sleep_for = sleep_for * (0.8 + random.random() * 0.4)
                log(f"Network error for {assignment_id} (attempt {attempt}/{max_retries}): {e}. Sleeping {sleep_for:.2f}s")
                time.sleep(sleep_for)
                continue
            else:
                return (assignment_id, 0, str(e))


# --------------------
# Orchestration (with market -> clients mapping)
# --------------------
def build_unique_assignments(mapping: Dict[str, Dict[str, Any]], rows: List[Tuple[str, str]]):
    """
    Returns:
      client_azids: Set[str],
      market_azids: Set[str],
      unresolved: List[str],
      client_name_map: Dict[azId, client_name],
      market_name_map: Dict[azId, market_name],
      market_clients_map: Dict[azId, List[client_name]]
    """
    client_azids: Set[str] = set()
    market_azids: Set[str] = set()
    unresolved = []

    client_name_map: Dict[str, str] = {}
    market_name_map: Dict[str, str] = {}
    market_clients_map: Dict[str, List[str]] = defaultdict(list)

    client_markets = defaultdict(set)
    for client_name, market_name in rows:
        client_markets[client_name].add(market_name)

    for client_name, markets in client_markets.items():
        client_node = find_client_or_brand_node(mapping, client_name)
        if not client_node or not client_node.get("azId"):
            unresolved.append(f"Client not found: {client_name}")
            continue
        client_az = client_node["azId"]
        client_azids.add(client_az)
        client_name_map[client_az] = client_name

        for market in markets:
            try:
                m_az = get_parent_market_azid(mapping, market, client_name)
                market_azids.add(m_az)
                if m_az not in market_name_map:
                    # prefer the mapping name (official) if available, else CSV market
                    try:
                        mapping_name = mapping[m_az].get("name")
                    except Exception:
                        mapping_name = None
                    market_name_map[m_az] = mapping_name or market
                # append client name to market -> clients mapping (avoid dups)
                if client_name not in market_clients_map[m_az]:
                    market_clients_map[m_az].append(client_name)
            except Exception as e:
                unresolved.append(f"Could not resolve market '{market}' for client '{client_name}': {e}")

    return client_azids, market_azids, unresolved, client_name_map, market_name_map, market_clients_map


def run_concurrent_apply(session_factory, assignment_ids: List[str], workers: int, max_retries: int, backoff_base: float, backoff_factor: float):
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(apply_template_with_retries, session_factory, aid, max_retries, backoff_base, backoff_factor): aid for aid in assignment_ids}
        for fut in as_completed(futures):
            aid = futures[fut]
            try:
                assignment_id, code, body = fut.result()
                results.append((assignment_id, code, body))
            except Exception as e:
                results.append((aid, 0, str(e)))
    return results


# --------------------
# Main
# --------------------
def main():
    parser = argparse.ArgumentParser(description="Faster template apply script with market->client mapping")
    parser.add_argument("--csv", "-c", default=CLIENTS_CSV_PATH)
    parser.add_argument("--env", "-e", default=ENV_PATH)
    parser.add_argument("--workers", "-w", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--log", default=LOG_PATH)
    parser.add_argument("--backoff-base", type=float, default=DEFAULT_BACKOFF_BASE)
    parser.add_argument("--backoff-factor", type=float, default=DEFAULT_BACKOFF_FACTOR)
    args = parser.parse_args()

    try:
        token, session_cookie = load_auth_env(args.env)
    except Exception as e:
        log(f"❌ Auth load error: {e}")
        sys.exit(1)

    session_factory = make_session_factory(token, session_cookie)

    try:
        sess = session_factory()
        mapping = fetch_hierarchy(sess)
        log("Fetched hierarchy mapping.")
    except Exception as e:
        log(f"❌ Failed to fetch hierarchy: {e}")
        sys.exit(1)

    try:
        rows = load_clients_and_markets(args.csv)
        log(f"Loaded {len(rows)} rows from {args.csv}")
    except Exception as e:
        log(f"❌ CSV load error: {e}")
        sys.exit(1)

    if not rows:
        log("No rows to process.")
        sys.exit(0)

    client_azids, market_azids, unresolved, client_name_map, market_name_map, market_clients_map = build_unique_assignments(mapping, rows)
    for u in unresolved:
        log(f"⚠️ {u}")

    log(f"Unique client assignment IDs: {len(client_azids)}")
    log(f"Unique market assignment IDs: {len(market_azids)}")

    all_results = []
    if client_azids:
        log("Applying template to clients concurrently...")
        client_results = run_concurrent_apply(session_factory, list(client_azids), workers=args.workers,
                                              max_retries=args.max_retries, backoff_base=args.backoff_base, backoff_factor=args.backoff_factor)
        for aid, code, body in client_results:
            display = client_name_map.get(aid, aid)
            if 200 <= code < 300 or is_empty_error(body):
                log(f"Client {display} ({aid}) -> {code} ✅")
            else:
                log(f"Client {display} ({aid}) -> {code} ❌   {body}")
        all_results.extend(client_results)

    if market_azids:
        log("Applying template to markets concurrently...")
        market_results = run_concurrent_apply(session_factory, list(market_azids), workers=args.workers,
                                              max_retries=args.max_retries, backoff_base=args.backoff_base, backoff_factor=args.backoff_factor)
        for aid, code, body in market_results:
            market_display = market_name_map.get(aid, aid)
            clients_for_market = market_clients_map.get(aid, [])
            clients_str = ", ".join(clients_for_market) if clients_for_market else "N/A"
            if 200 <= code < 300 or is_empty_error(body):
                log(f"Market {market_display} ({aid}) for client(s): {clients_str} -> {code} ✅")
            else:
                log(f"Market {market_display} ({aid}) for client(s): {clients_str} -> {code} ❌   {body}")
        all_results.extend(market_results)

    succ_clients = sum(1 for a, c, b in all_results if 200 <= c < 300 or is_empty_error(b))
    fail = len(all_results) - succ_clients
    log(f"\n📊 Summary: success: {succ_clients}, failures: {fail}, total attempts: {len(all_results)}")
    flush_log_to_file(args.log)


if __name__ == "__main__":
    main()
