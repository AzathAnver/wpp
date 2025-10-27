import os
import re
import csv
import sys

def parse_log(log_path: str):
    # Buckets and file names (matching your requested names, including the misspelling of "sucess")
    buckets = {
        'sucess': [],
        'already exist': [],
        'market not found': [],
        'client not found': [],
        '400exist': [],  # NEW
        'failed': []
    }
    out_names = {
        'sucess': 'sucess.csv',
        'already exist': 'already exist.csv',
        'market not found': 'market not found.csv',
        'client not found': 'client not found.csv',
        '400exist': '400exist.csv',  # NEW
        'failed': 'failed.csv'
    }

    # Regex patterns
    re_processing = re.compile(r'Processing client:\s*(.*?)\s*\|\s*market:\s*(.*)', re.IGNORECASE)
    re_success = re.compile(r'Successfully created org-unit for\s+(.*?)\s*->\s*(.*)', re.IGNORECASE)

    # Capture status code if present
    re_failed_code = re.compile(r'Failed for\s+(.*?)\s*->\s*(.*?):\s*(\d{3})\b', re.IGNORECASE)
    re_failed = re.compile(r'Failed for\s+(.*?)\s*->\s*(.*?)(?::|$)', re.IGNORECASE)

    re_network = re.compile(r'Network error posting for\s+(.*?)\s*->\s*(.*?)(?::|$)', re.IGNORECASE)
    re_already_exists_for = re.compile(r'Org-unit already exists for\s+(.*?)\s*->\s*(.*)', re.IGNORECASE)

    # BRAND can't have children (straight/curly apostrophes, with/without apostrophe)
    re_brand_cant_children = re.compile(
        r"Type:\s*BRAND.*can(?:not|[’']?t)\s+have\s+children",
        re.IGNORECASE
    )

    current_client = None
    current_market = None
    current_category = None
    current_status_code = None
    brand_children_violation = False  # NEW

    def finalize():
        nonlocal current_client, current_market, current_category, current_status_code, brand_children_violation
        # Safety override: ensure 400 + BRAND can't have children => 400exist (not failed)
        if brand_children_violation and current_status_code == 400:
            current_category = '400exist'

        if current_client and current_market and current_category:
            buckets[current_category].append((current_client.strip(), current_market.strip()))
        current_client = None
        current_market = None
        current_category = None
        current_status_code = None
        brand_children_violation = False

    with open(log_path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            # Block separator ends a record
            if line.startswith('='):
                finalize()
                continue

            # New processing line starts a new record
            m = re_processing.search(line)
            if m:
                if current_client is not None:
                    finalize()
                current_client = m.group(1).strip()
                current_market = m.group(2).strip()
                current_category = None
                current_status_code = None
                brand_children_violation = False
                continue

            # Categorization (order matters: specific > general)
            # Market not found
            if ('market not found' in line.lower()) or ('no mdid resolved for market' in line.lower()):
                if current_category is None:
                    current_category = 'market not found'
                continue

            # Client not found (if ever present)
            if re.search(r'client not found', line, re.IGNORECASE):
                current_category = 'client not found'
                continue

            # Already exists (explicit)
            m = re_already_exists_for.search(line)
            if m:
                current_client = m.group(1).strip()
                current_market = m.group(2).strip()
                if current_category is None:
                    current_category = 'already exist'
                continue

            # Already exists (generic)
            if re.search(r'\balready exists\b', line, re.IGNORECASE):
                if current_category is None:
                    current_category = 'already exist'
                continue

            # Success
            m = re_success.search(line)
            if m:
                current_client = m.group(1).strip()
                current_market = m.group(2).strip()
                current_category = 'sucess'
                continue

            # Failed with explicit status code (capture it)
            m = re_failed_code.search(line)
            if m:
                current_client = m.group(1).strip()
                current_market = m.group(2).strip()
                try:
                    current_status_code = int(m.group(3))
                except Exception:
                    current_status_code = None
                if current_category is None:
                    current_category = 'failed'
                continue

            # Failed (no explicit code)
            m = re_failed.search(line)
            if m:
                current_client = m.group(1).strip()
                current_market = m.group(2).strip()
                if current_category is None:
                    current_category = 'failed'
                continue

            # Network error -> failed
            m = re_network.search(line)
            if m:
                current_client = m.group(1).strip()
                current_market = m.group(2).strip()
                if current_category is None:
                    current_category = 'failed'
                continue

            # BRAND can't have children
            if re_brand_cant_children.search(line):
                brand_children_violation = True
                # Immediate override if we already know the code = 400
                if current_status_code == 400:
                    current_category = '400exist'
                continue

            # Generic server error hint -> failed (and capture code if visible)
            if ('server error' in line.lower() or "'error':" in line.lower() or '"error":' in line.lower()):
                code_match = re.search(r'\b(4\d{2}|5\d{2})\b', line)
                if code_match:
                    try:
                        current_status_code = int(code_match.group(1))
                    except Exception:
                        pass
                if current_category is None:
                    current_category = 'failed'
                continue

        # Flush last record
        finalize()

    # Write CSVs next to the log file
    out_dir = os.path.dirname(log_path) or '.'
    for cat, rows in buckets.items():
        out_path = os.path.join(out_dir, out_names[cat])
        with open(out_path, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh)
            w.writerow(['client_name', 'market'])
            for client, market in rows:
                w.writerow([client, market])
        print(f"Wrote {len(rows)} rows to {out_path}")

if __name__ == '__main__':
    # Use path from CLI or default to your provided path
    log_file = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Azath.A\os\allmar\output\output.txt"
    parse_log(log_file)