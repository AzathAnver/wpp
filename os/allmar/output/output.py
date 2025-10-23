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
        'failed': []
    }
    out_names = {
        'sucess': 'sucess.csv',
        'already exist': 'already exist.csv',
        'market not found': 'market not found.csv',
        'client not found': 'client not found.csv',
        'failed': 'failed.csv'
    }

    # Regex patterns
    re_processing = re.compile(r'Processing client:\s*(.*?)\s*\|\s*market:\s*(.*)', re.IGNORECASE)
    re_success = re.compile(r'Successfully created org-unit for\s+(.*?)\s*->\s*(.*)', re.IGNORECASE)
    re_failed = re.compile(r'Failed for\s+(.*?)\s*->\s*(.*?)(?::|$)', re.IGNORECASE)
    re_network = re.compile(r'Network error posting for\s+(.*?)\s*->\s*(.*?)(?::|$)', re.IGNORECASE)
    re_already_exists_for = re.compile(r'Org-unit already exists for\s+(.*?)\s*->\s*(.*)', re.IGNORECASE)

    current_client = None
    current_market = None
    current_category = None

    def finalize():
        nonlocal current_client, current_market, current_category
        if current_client and current_market and current_category:
            buckets[current_category].append((current_client.strip(), current_market.strip()))
        current_client = None
        current_market = None
        current_category = None

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

            # Failed
            m = re_failed.search(line)
            if m:
                current_client = m.group(1).strip()
                current_market = m.group(2).strip()
                if current_category is None:
                    current_category = 'failed'
                continue

            m = re_network.search(line)
            if m:
                current_client = m.group(1).strip()
                current_market = m.group(2).strip()
                if current_category is None:
                    current_category = 'failed'
                continue

            # Generic server error hint -> failed
            if ('server error' in line.lower() or '"error":' in line.lower()) and re.search(r'\b(4\d{2}|5\d{2})\b', line):
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