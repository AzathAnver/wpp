import os
import re
import csv
import sys

def parse_apply_sync_log(log_path: str):
    """
    Parse logs from the apply/sync template run and bucket client/market pairs into:
      - sucess.csv  (spelling kept to match your convention)
      - failed.csv

    Success for a record (client + market):
      - Every POST status is either:
          * 200
          * 400 with detail: "Hierarchy node should be empty to apply/sync template"
      - Anything else (other codes, missing detail for a 400, no POST lines, or explicit errors)
        -> failed
    """
    buckets = {
        'sucess': [],
        'failed': []
    }
    out_names = {
        'sucess': 'sucess.csv',
        'failed': 'failed.csv'
    }

    # Regex patterns (robust with emojis/symbols before text)
    re_processing = re.compile(r'Processing client:\s*(.*?)\s*\(market:\s*(.*?)\)', re.IGNORECASE)
    re_post_status = re.compile(r'POST\s*#\s*(\d+)\s*status:\s*(\d{3})', re.IGNORECASE)
    re_response = re.compile(r'Response:\s*(.*)', re.IGNORECASE)

    # Allowed 400 detail text
    re_allowed_400_detail = re.compile(
        r'hierarchy node should be empty to apply/sync template',
        re.IGNORECASE
    )

    # Explicit failure hints
    re_client_brand_not_found = re.compile(r'client/brand node not found', re.IGNORECASE)
    re_could_not_resolve_market = re.compile(r'could not resolve market', re.IGNORECASE)
    re_skipping = re.compile(r'\bskipping\b', re.IGNORECASE)

    current_client = None
    current_market = None

    # Per-record state
    statuses_ok = True           # All seen statuses are acceptable so far
    pending_allowed_400 = 0      # Count of 400 statuses awaiting validation via Response detail
    saw_any_status = False       # At least one POST status line seen
    explicit_failure = False     # Direct failure messages force failure

    def finalize():
        nonlocal current_client, current_market, statuses_ok, pending_allowed_400, saw_any_status, explicit_failure

        if current_client and current_market:
            if saw_any_status and statuses_ok and pending_allowed_400 == 0 and not explicit_failure:
                buckets['sucess'].append((current_client.strip(), current_market.strip()))
            else:
                buckets['failed'].append((current_client.strip(), current_market.strip()))

        # Reset for next record
        current_client = None
        current_market = None
        statuses_ok = True
        pending_allowed_400 = 0
        saw_any_status = False
        explicit_failure = False

    with open(log_path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            # Start of a new record
            m = re_processing.search(line)
            if m:
                if current_client is not None:
                    finalize()
                current_client = m.group(1).strip()
                current_market = m.group(2).strip()
                statuses_ok = True
                pending_allowed_400 = 0
                saw_any_status = False
                explicit_failure = False
                continue

            if current_client is None:
                continue  # ignore lines before the first "Processing client"

            # Explicit failure hints
            if (re_client_brand_not_found.search(line)
                or re_could_not_resolve_market.search(line)
                or re_skipping.search(line)):
                explicit_failure = True

            # POST status lines
            m = re_post_status.search(line)
            if m:
                saw_any_status = True
                try:
                    code = int(m.group(2))
                except Exception:
                    statuses_ok = False
                else:
                    if code == 200:
                        pass  # OK
                    elif code == 400:
                        # Acceptable only if followed by the specific Response detail
                        pending_allowed_400 += 1
                    else:
                        statuses_ok = False
                continue

            # Response lines (to satisfy/validate pending 400s)
            m = re_response.search(line)
            if m:
                if pending_allowed_400 > 0:
                    resp_text = m.group(1)
                    if re_allowed_400_detail.search(resp_text):
                        pending_allowed_400 -= 1
                    else:
                        pending_allowed_400 -= 1
                        statuses_ok = False
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
    # Defaults to output.txt (current directory) if no CLI arg provided
    log_file = sys.argv[1] if len(sys.argv) > 1 else 'output.txt'
    parse_apply_sync_log(log_file)