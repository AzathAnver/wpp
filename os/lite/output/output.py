import json
import csv
import sys
import re
from pathlib import Path

ALREADY_EXIST_PHRASE = "Hierarchy node should be empty to apply/sync template"

OUT_FILES = {
    "already exist": "already exist.csv",
    "sucess": "sucess.csv",   # keeping your requested spelling
    "failed": "failed.csv",
}

HEADERS = ["market", "clientname", "brand", "category"]

# New: patterns to catch the non-JSON warning lines
FILENAME_LINE_PREFIX = re.compile(r"^[^:\n]+:\d+:\s*")  # strips "output.txt:311: "
NOT_FOUND_RE = re.compile(
    r"client/brand\s+node\s+not\s+found\s+for\s+['\"]?([^'\"\n]+)['\"]?",
    re.IGNORECASE,
)

def extract_row_fields(row: dict):
    market = row.get("Market") or row.get("market") or ""
    client = row.get("Client") or row.get("client") or ""
    brand = row.get("Brand") or row.get("brand") or ""
    category = row.get("Category") or row.get("category") or ""
    return market, client, brand, category

def flatten_response(obj: dict) -> str:
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

    if status == 200:
        return "sucess"
    if status == 400 and ALREADY_EXIST_PHRASE.lower() in text:
        return "already exist"
    return "failed"

# New: parse the plain-text warning and return a row if matched
def parse_not_found_warning(line: str):
    core = FILENAME_LINE_PREFIX.sub("", line.strip())
    m = NOT_FOUND_RE.search(core)
    if not m:
        return None
    name = m.group(1).strip()
    # We only know the brand/client name from this message
    return ["", "", name, ""]

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
                # Try to catch known non-JSON warnings
                parsed = parse_not_found_warning(line)
                if parsed:
                    buckets["failed"].append(parsed)
                # Skip all other non-JSON lines
                continue

            row = obj.get("row") or {}
            market, client, brand, category = extract_row_fields(row)

            if not market and not client and not brand and not category:
                continue

            cat = categorize(obj)
            buckets[cat].append([market, client, brand, category])

    out_dir = log_path.parent
    for cat, filename in OUT_FILES.items():
        out_path = out_dir / filename
        with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(HEADERS)
            for market, client, brand, category in buckets[cat]:
                w.writerow([market, client, brand, category])
        print(f"Wrote {len(buckets[cat])} rows -> {out_path}")

def main():
    default_path = Path(__file__).resolve().parent / "output.txt"
    log_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_path
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)
    parse_file(log_path)

if __name__ == "__main__":
    main()