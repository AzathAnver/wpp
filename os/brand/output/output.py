import os
import re
import sys

OUT_DIR = "parsed_logs"

# Patterns to find header variants (old: '🚀 Processing: Market=..., Client=..., Brand=..., Category=...'
# and new: '🚀 Processing row 1: Market=..., Client=..., Brand=..., Category=...')
HEADER_RE = re.compile(
    r"^🚀\s*Processing(?:\s*row\s*\d+)?\s*:?\s*(?:Market=([^,]+),\s*Client=([^,]+),\s*Brand=([^,]+),\s*Category=(.+)|(.+))",
    flags=re.IGNORECASE
)

# Alternate header with commas but without the exact order - attempt a generic capture
GENERIC_HDR_RE = re.compile(
    r"Market=([^,]+).*Client=([^,]+).*Brand=([^,]+).*Category=(.+)",
    flags=re.IGNORECASE
)

# Useful error / success markers (we'll match substrings; JSON error bodies are kept as text)
SUCCESS_MARKER = "✅ Created Org Unit for Brand"
FAILED_POST_MARKER = "❌ Failed POST for"
ERROR_PREFIX = "⚠️ Error"
ERROR_FOR_ROW_RE = re.compile(r"⚠️\s*Error\s*for\s*row\s*\d+\s*:\s*(.*)", flags=re.IGNORECASE)

# Specific error patterns
MARKET_CLIENT_NOT_FOUND_RE = re.compile(r"Market\s+'([^']+)'\s+with client\s+'([^']+)'\s+not found", flags=re.IGNORECASE)
NO_EXACT_BRAND_RE = re.compile(r"No exact brand named\s+'([^']+)'", flags=re.IGNORECASE)
CATEGORY_NOT_FOUND_RE = re.compile(r"Category\s+'([^']+)'\s+not found", flags=re.IGNORECASE)
POST_409_RE = re.compile(r":\s*409\b")  # simple check for ": 409" in the line

# Helper: normalize field values
def _norm(s: str) -> str:
    if s is None:
        return "Unknown"
    return " ".join(s.strip().split())

def parse_log_file(filename: str, output_folder: str = OUT_DIR):
    os.makedirs(output_folder, exist_ok=True)

    with open(filename, "r", encoding="utf-8") as fh:
        lines = [ln.rstrip("\n") for ln in fh]

    blocks = []  # list of (header_line, body_lines)
    current_header = None
    current_body = []

    for ln in lines:
        if ln.startswith("🚀"):
            # start a new block
            if current_header is not None:
                blocks.append((current_header, current_body))
            current_header = ln
            current_body = []
        else:
            # accumulate into current block (if any)
            if current_header is not None:
                current_body.append(ln)
            else:
                # ignore global log lines (cache messages, fetch messages, etc.)
                pass

    # append last block
    if current_header is not None:
        blocks.append((current_header, current_body))

    # Containers for categorized rows
    success_entries = []
    already_exists_409_entries = []
    market_not_found_entries = []
    brand_not_found_entries = []
    category_not_found_entries = []
    other_errors_entries = []

    for header, body_lines in blocks:
        # Try to extract fields using first regexes
        market = client = brand = category = "Unknown"

        # Try the main header RE
        m = GENERIC_HDR_RE.search(header)
        if m:
            market = _norm(m.group(1))
            client = _norm(m.group(2))
            brand = _norm(m.group(3))
            category = _norm(m.group(4))
        else:
            # fallback: try to parse after the colon if present (older variant)
            after_colon = header.split(":", 1)
            if len(after_colon) == 2:
                payload = after_colon[1].strip()
                m2 = GENERIC_HDR_RE.search(payload)
                if m2:
                    market = _norm(m2.group(1))
                    client = _norm(m2.group(2))
                    brand = _norm(m2.group(3))
                    category = _norm(m2.group(4))
                else:
                    # try loose splitting by commas if format is like "Market=X, Client=Y, Brand=Z, Category=K"
                    parts = [p.strip() for p in payload.split(",")]
                    try:
                        # naive mapping based on key=
                        kv = {}
                        for p in parts:
                            if "=" in p:
                                k, v = p.split("=", 1)
                                kv[k.strip().lower()] = v.strip()
                        market = _norm(kv.get("market", market))
                        client = _norm(kv.get("client", client))
                        brand = _norm(kv.get("brand", brand))
                        category = _norm(kv.get("category", category))
                    except Exception:
                        pass

        # Build CSV row base (no commas inside simple fields assumed)
        csv_row = f"{market},{client},{brand},{category}"

        body_text = "\n".join(body_lines).strip()

        # Classification checks (order matters)
        if SUCCESS_MARKER in body_text:
            success_entries.append(csv_row)
            continue

        # Check for 409 failed POST
        if FAILED_POST_MARKER in body_text and POST_409_RE.search(body_text):
            already_exists_409_entries.append(csv_row)
            continue

        # Check for "Error for row X: ..." and inspect message
        err_match = ERROR_FOR_ROW_RE.search(body_text)
        err_text = None
        if err_match:
            err_text = err_match.group(1).strip()

            # Check market/client not found wording
            if MARKET_CLIENT_NOT_FOUND_RE.search(err_text):
                market_not_found_entries.append(csv_row)
                continue

            # Category not found?
            if CATEGORY_NOT_FOUND_RE.search(err_text) or "not found in category.json" in err_text:
                category_not_found_entries.append(csv_row)
                continue

            # Brand not found variants
            if NO_EXACT_BRAND_RE.search(err_text) or "brand" in err_text.lower() and "not found" in err_text.lower():
                brand_not_found_entries.append(csv_row)
                continue

            # generic error capture
            clean_err = " ".join(err_text.split())
            other_errors_entries.append(f"{csv_row} | ERROR: {clean_err}")
            continue

        # If no 'Error for row' but body contains 'No exact brand' or other messages
        if NO_EXACT_BRAND_RE.search(body_text) or "No exact brand named" in body_text:
            brand_not_found_entries.append(csv_row)
            continue

        if "not found in category.json" in body_text or "Category '" in body_text and "not found" in body_text:
            category_not_found_entries.append(csv_row)
            continue

        if "Market '" in body_text and "with client" in body_text and "not found" in body_text:
            market_not_found_entries.append(csv_row)
            continue

        # Fallback: if body contains a generic '⚠️ Error' without the 'for row' prefix
        if ERROR_PREFIX in body_text:
            clean_err = " ".join(body_text.replace("\n", " ").split())
            other_errors_entries.append(f"{csv_row} | ERROR: {clean_err}")
            continue

        # Unknown/unclassifiable block -> save to other_errors with raw body preview
        preview = body_text.replace("\n", " ").strip()[:400]
        other_errors_entries.append(f"{csv_row} | UNKNOWN: {preview}")

    # Helper to write lists to file
    def write_file(fn, rows):
        path = os.path.join(output_folder, fn)
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(r + "\n")

    write_file("success.txt", success_entries)
    write_file("already_exists_409.txt", already_exists_409_entries)
    write_file("market_not_found.txt", market_not_found_entries)
    write_file("brand_not_found.txt", brand_not_found_entries)
    write_file("category_not_found.txt", category_not_found_entries)
    write_file("other_errors.txt", other_errors_entries)

    # Print summary
    print(f"📁 Output written to folder: '{output_folder}'")
    print(f"✅ Success: {len(success_entries)}")
    print(f"❌ Already Exists (409): {len(already_exists_409_entries)}")
    print(f"⚠️ Market Not Found: {len(market_not_found_entries)}")
    print(f"⚠️ Brand Not Found: {len(brand_not_found_entries)}")
    print(f"⚠️ Category Not Found: {len(category_not_found_entries)}")
    print(f"❗ Other / Unknown: {len(other_errors_entries)}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        in_file = sys.argv[1]
    else:
        in_file = "output.txt"

    if not os.path.exists(in_file):
        print(f"Input file '{in_file}' not found. Provide the path to the log file as argument.")
        sys.exit(2)

    parse_log_file(in_file)