#!/usr/bin/env python3
"""
parse_log_final_status.py

Parses threaded log "output1.txt" and writes "summary.csv" with final (de-duplicated)
status per group uid (and per brand-only events). Uses last-seen event to decide final state.
"""

import re
import csv
from pathlib import Path

INPUT_PATH = Path("output1.txt")   # change if needed
OUTPUT_PATH = Path("summary.csv")

# Regex patterns
processing_brand_re = re.compile(r"Processing brand:\s*(.+)$")
found_group_re = re.compile(r"📂 Found existing group → uid:\s*([0-9a-fA-F-]+)\s*\|\s*name:\s*(.+)$")
created_group_re = re.compile(r"✅ Created group → uid:\s*([0-9a-fA-F-]+),\s*name:\s*(.+)$")
roles_patched_re = re.compile(r"🔑 Roles patched for existing group\s*([0-9a-fA-F-]+)\. Response:\s*(.+)$")
# 422 message often contains (group_id, role_id, account_id)=(<group_uuid>, ...
error_422_groupid_re = re.compile(r"\(group_id, role_id, account_id\)=\(\s*([0-9a-fA-F-]+)\s*,")
error_422_generic_re = re.compile(r"422 - .*already exists", re.IGNORECASE)
failed_fetch_azid_re = re.compile(r"Failed to fetch azId for '([^']+)':")
failed_patch_roles_uid_re = re.compile(r"Failed to patch roles for existing group\s*([0-9a-fA-F-]+):\s*(.+)$")
generic_failed_re = re.compile(r"\bFailed\b", re.IGNORECASE)
timeout_re = re.compile(r"Read timed out", re.IGNORECASE)
bad_request_re = re.compile(r"Groups API failed: 400", re.IGNORECASE)


def parse_log_file(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")

    # maps
    uid_to_brand = {}      # uid -> brand name (from Found/Created lines)
    uid_events = {}        # uid -> list of (line_no, status, detail)
    brand_events = {}      # brand -> list of (line_no, status, detail) for events without uid

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for i, raw_line in enumerate(fh, start=1):
            line = raw_line.rstrip("\n")

            # 1) Found existing group -> map uid to brand
            m = found_group_re.search(line)
            if m:
                uid = m.group(1).strip()
                brand = m.group(2).strip()
                uid_to_brand[uid] = brand
                # treat "found existing group" as info (not final) but record it
                uid_events.setdefault(uid, []).append((i, "FOUND", line))
                continue

            # 2) Created group -> map uid to brand and record creation success
            m = created_group_re.search(line)
            if m:
                uid = m.group(1).strip()
                brand = m.group(2).strip()
                uid_to_brand[uid] = brand
                uid_events.setdefault(uid, []).append((i, "CREATED", line))
                continue

            # 3) Roles patched (Success) with uid
            m = roles_patched_re.search(line)
            if m:
                uid = m.group(1).strip()
                detail = m.group(2).strip()
                uid_events.setdefault(uid, []).append((i, "SUCCESS", detail))
                # also map brand if the response contains JSON with group_uid - not necessary here
                continue

            # 4) 422 error: extract group_id if possible
            if "422" in line and "already exists" in line.lower():
                m = error_422_groupid_re.search(line)
                if m:
                    uid = m.group(1).strip()
                    uid_events.setdefault(uid, []).append((i, "422_ALREADY_EXISTS", line.strip()))
                else:
                    # no group id in tuple — fallback: record as generic brand-level if brand is present
                    # Try to find "group_id" uuid anywhere
                    uuid_match = re.search(r"([0-9a-fA-F-]{36})", line)
                    if uuid_match:
                        uid = uuid_match.group(1)
                        uid_events.setdefault(uid, []).append((i, "422_ALREADY_EXISTS", line.strip()))
                    else:
                        # generic 422: record as brand-less failure (we'll keep it in generic bucket)
                        brand_events.setdefault("(unknown)", []).append((i, "422_ALREADY_EXISTS", line.strip()))
                continue

            # 5) Failed to patch roles with uid
            m = failed_patch_roles_uid_re.search(line)
            if m:
                uid = m.group(1).strip()
                detail = m.group(2).strip()
                uid_events.setdefault(uid, []).append((i, "FAILED_PATCH_ROLES", detail))
                continue

            # 6) Failed to fetch azId for 'brand'
            m = failed_fetch_azid_re.search(line)
            if m:
                brand = m.group(1).strip()
                brand_events.setdefault(brand, []).append((i, "FAILED_AZID_FETCH", line.strip()))
                continue

            # 7) Timeout or generic network failure lines (may not include uid)
            if timeout_re.search(line):
                # try to capture uid in line
                uuid = re.search(r"([0-9a-fA-F-]{36})", line)
                if uuid:
                    uid = uuid.group(1)
                    uid_events.setdefault(uid, []).append((i, "TIMEOUT", line.strip()))
                else:
                    brand_events.setdefault("(unknown)", []).append((i, "TIMEOUT", line.strip()))
                continue

            # 8) 400 Bad Request (Groups API) — sometimes related to a brand search
            if bad_request_re.search(line):
                brand_events.setdefault("(unknown)", []).append((i, "BAD_REQUEST_400", line.strip()))
                continue

            # 9) Any generic 'Failed' lines (last-resort)
            if generic_failed_re.search(line):
                # Try to find a uid
                uuid = re.search(r"([0-9a-fA-F-]{36})", line)
                brand_match = processing_brand_re.search(line)
                if uuid:
                    uid = uuid.group(1)
                    uid_events.setdefault(uid, []).append((i, "FAILED", line.strip()))
                elif brand_match:
                    brand = brand_match.group(1).strip()
                    brand_events.setdefault(brand, []).append((i, "FAILED", line.strip()))
                else:
                    brand_events.setdefault("(unknown)", []).append((i, "FAILED", line.strip()))
                continue

    return uid_to_brand, uid_events, brand_events


def compute_final_status(uid_to_brand, uid_events, brand_events):
    """
    Decide final status per uid (use last-seen event by line number).
    For brand-level events (no uid), decide last-seen per brand.
    Returns list of rows: (brand, group_uid, final_status, detail, line_no)
    """
    rows = []

    # Process uid-based events
    for uid, events in uid_events.items():
        # pick the event with largest line_no (last seen)
        last_line, last_status, last_detail = max(events, key=lambda t: t[0])
        brand = uid_to_brand.get(uid, "(unknown)")
        # Normalize statuses into friendly labels
        if last_status == "SUCCESS":
            final = "Success"
        elif last_status == "422_ALREADY_EXISTS":
            final = "422 - Already Exists"
        elif last_status in ("CREATED",):
            final = "Success (Created)"
        elif last_status in ("FAILED_PATCH_ROLES", "FAILED", "TIMEOUT"):
            final = "Failed"
        elif last_status == "FOUND":
            final = "Found (no action)"
        else:
            final = last_status
        rows.append((brand, uid, final, last_detail.replace("\n", " "), last_line))

    # Process brand-only events (no uid)
    for brand, events in brand_events.items():
        last_line, last_status, last_detail = max(events, key=lambda t: t[0])
        # If this brand is known via any UID mapping, skip (we will have uid rows); but still include if brand not present
        known_uids = [u for u, b in uid_to_brand.items() if b == brand]
        if known_uids:
            # brand has uid entries; we can skip brand-only events to avoid duplicates
            continue
        # Normalize
        if last_status == "422_ALREADY_EXISTS":
            final = "422 - Already Exists"
        elif last_status in ("FAILED_AZID_FETCH", "BAD_REQUEST_400", "FAILED"):
            final = "Failed"
        elif last_status == "TIMEOUT":
            final = "Failed (Timeout)"
        else:
            final = last_status
        rows.append((brand, "", final, last_detail.replace("\n", " "), last_line))

    # Sort rows by line_no (appearance order)
    rows.sort(key=lambda r: r[4])
    return rows


def write_csv(rows, out_path: Path):
    header = ["brand", "group_uid", "final_status", "detail", "line_no"]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for r in rows:
            writer.writerow(r)


def main():
    print(f"Parsing log: {INPUT_PATH}")
    uid_to_brand, uid_events, brand_events = parse_log_file(INPUT_PATH)
    print(f"Found {len(uid_events)} unique uids with events, and {len(brand_events)} brand-level events.")
    rows = compute_final_status(uid_to_brand, uid_events, brand_events)
    write_csv(rows, OUTPUT_PATH)
    print(f"Written summary to: {OUTPUT_PATH} ({len(rows)} rows)")
    print("Legend: final_status values: Success / 422 - Already Exists / Failed / Success (Created) / Found (no action)")

if __name__ == "__main__":
    main()
