import json
import csv
import sys
from pathlib import Path

ALREADY_EXIST_PHRASE = "Hierarchy node should be empty to apply/sync template"

OUT_FILES = {
    "already exist": "already exist.csv",
    "sucess": "sucess.csv",   # keeping your requested spelling
    "failed": "failed.csv",
}

HEADERS = ["market", "clientname", "brand", "category"]

def extract_row_fields(row: dict):
    # Be tolerant to different key casing
    market = row.get("Market") or row.get("market") or ""
    client = row.get("Client") or row.get("client") or ""
    brand = row.get("Brand") or row.get("brand") or ""
    category = row.get("Category") or row.get("category") or ""
    return market, client, brand, category

def flatten_response(obj: dict) -> str:
    # Gather text from response and error to inspect messages
    parts = []
    resp = obj.get("response")
    if isinstance(resp, dict):
        parts.extend(str(v) for v in resp.values())
    elif resp is not None:
        parts.append(str(resp))
    err = obj.get("error")
    if err:
        parts.append(str(err))
    return " | ".join(parts)

def categorize(obj: dict) -> str:
    status = obj.get("status")
    text = flatten_response(obj).lower()

    # Success
    if status == 200:
        return "sucess"

    # Only this specific 400 should be treated as "already exist"
    if status == 400 and ALREADY_EXIST_PHRASE.lower() in text:
        return "already exist"

    # Everything else is failed
    return "failed"

def parse_file(log_path: Path):
    buckets = {k: [] for k in OUT_FILES.keys()}

    with log_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # Skip non-JSON lines (e.g., shell prompts)
                continue

            row = obj.get("row") or {}
            market, client, brand, category = extract_row_fields(row)

            # Require at least market + client for output; include brand/category if present
            if not market and not client and not brand and not category:
                continue

            cat = categorize(obj)
            buckets[cat].append([market, client, brand, category])

    # Write CSVs next to the log file
    out_dir = log_path.parent
    for cat, filename in OUT_FILES.items():
        out_path = out_dir / filename
        with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(HEADERS)  # market,clientname,brand,category
            for market, client, brand, category in buckets[cat]:
                # Header expects "clientname" as a single word
                w.writerow([market, client, brand, category])
        print(f"Wrote {len(buckets[cat])} rows -> {out_path}")

def main():
    # Default to output.txt in the same directory as this script,
    # or allow a path override via CLI arg.
    default_path = Path(__file__).resolve().parent / "output.txt"
    log_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_path
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)
    parse_file(log_path)

if __name__ == "__main__":
    main()