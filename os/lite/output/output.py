import os
import json
import csv
import re
import sys
from pathlib import Path

# Output categories (keeping your requested spelling for "sucess")
CATEGORIES = [
    'sucess',
    'already exist',
    'market not found',
    'client not found',
    'failed'
]

RE_ALREADY = re.compile(r'\balready exist(s)?\b', re.IGNORECASE)
RE_MARKET_NOT_FOUND = re.compile(r"market\s*'[^']+'\s*not found|market not found", re.IGNORECASE)
RE_CLIENT_NOT_FOUND = re.compile(r"client\s*'[^']+'\s*not found|client not found", re.IGNORECASE)

def extract_text_from_entry(entry: dict) -> str:
    parts = []
    resp = entry.get('response')
    if isinstance(resp, dict):
        for k, v in resp.items():
            parts.append(f"{k}: {v}")
    elif resp is not None:
        parts.append(str(resp))
    err = entry.get('error')
    if err:
        parts.append(str(err))
    return " | ".join(parts)

def categorize(status, text: str) -> str:
    t = (text or "").lower()

    # Success from HTTP status
    if status == 200:
        return 'sucess'

    # Specific error patterns
    if RE_ALREADY.search(t):
        return 'already exist'
    if RE_MARKET_NOT_FOUND.search(t):
        return 'market not found'
    if RE_CLIENT_NOT_FOUND.search(t):
        return 'client not found'

    # Default
    return 'failed'

def parse_file(log_path: Path):
    buckets = {cat: [] for cat in CATEGORIES}

    with log_path.open('r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            # Ignore non-JSON lines (e.g., PS prompts)
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            row = obj.get('row') or {}
            client = row.get('Client') or row.get('client')
            market = row.get('Market') or row.get('market')
            if not client or not market:
                continue

            status = obj.get('status')
            text = extract_text_from_entry(obj)
            cat = categorize(status, text)
            if cat not in buckets:
                cat = 'failed'

            buckets[cat].append((client, market))

    # Write CSVs next to the log file
    out_dir = log_path.parent
    for cat, rows in buckets.items():
        out_path = out_dir / f"{cat}.csv"
        with out_path.open('w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh)
            w.writerow(['client_name', 'market'])
            w.writerows(rows)
        print(f"Wrote {len(rows)} rows -> {out_path}")

def main():
    # Default to "output.txt" in the same folder as this script
    default_path = Path(__file__).resolve().parent / "output.txt"
    log_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_path

    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)

    parse_file(log_path)

if __name__ == "__main__":
    main()