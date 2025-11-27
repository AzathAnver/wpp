#!/usr/bin/env python3
"""
Parse the script run log (output.txt) and produce:
 - summary.json (overall counts + top lists)
 - per_group.csv (group -> totals / successes / not_found)
 - failed_rows.csv (all lines that indicate failures / warnings / errors)
Designed for the log format produced by your script (lines like "Processing Row X: Group='...' , SUCCESS: email -> id", "Row X: Group '...' not found.", "FAILED:" or "ERROR:").
"""

import re
import json
import csv
from collections import defaultdict, Counter
from pathlib import Path

# --- CONFIG ---
LOG_PATH = Path("output.txt")   # update if your file is elsewhere
OUT_DIR = Path(".")
SUMMARY_JSON = OUT_DIR / "summary.json"
PER_GROUP_CSV = OUT_DIR / "per_group.csv"
FAILED_ROWS_CSV = OUT_DIR / "failed_rows.csv"
TOP_N_GROUPS = 25
# --------------

# Regex patterns (tuned to the log lines in your file)
re_processing = re.compile(r"Processing Row\s*(\d+):\s*Group='(?P<group>.*?)'\s*,\s*User='(?P<user>.*?)'", re.IGNORECASE)
re_group_not_found = re.compile(r"Row\s*(\d+):\s*Group\s*'(?P<group>.*?)'\s*not found\.", re.IGNORECASE)
re_success = re.compile(r"SUCCESS:\s*(?P<email>[\w\.\-\+@]+)\s*->\s*(?P<id>[0-9a-fA-F\-]+)")
re_failed = re.compile(r"FAILED:\s*(?P<rest>.*)")
re_error = re.compile(r"ERROR:\s*(?P<rest>.*)")
re_warning = re.compile(r"WARNING:\s*(?P<rest>.*)")

# Data collectors
total_rows_seen = 0
processed_rows = set()        # row numbers seen in Processing lines
not_found_rows = []           # list of (row, group, raw_line)
successes = []                # tuples (email, id, line)
failures = []                 # lines containing FAILED/ERROR/WARNING
group_stats = defaultdict(lambda: {"attempts": 0, "successes": 0, "not_found": 0, "users": set()})
unique_users_attempted = set()
unique_users_success = set()
other_info_lines = []

# Read log file
if not LOG_PATH.exists():
    raise SystemExit(f"Log file not found: {LOG_PATH}. Update LOG_PATH at top of script.")

with LOG_PATH.open("r", encoding="utf-8", errors="replace") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue

        # Processing rows
        m = re_processing.search(line)
        if m:
            total_rows_seen += 1
            rownum = int(m.group(1))
            grp = m.group("group").strip()
            user = m.group("user").strip().lower()
            processed_rows.add(rownum)
            unique_users_attempted.add(user)
            group_stats[grp]["attempts"] += 1
            group_stats[grp]["users"].add(user)
            continue

        # Group not found
        m = re_group_not_found.search(line)
        if m:
            rownum = int(m.group(1))
            grp = m.group("group").strip()
            not_found_rows.append({"row": rownum, "group": grp, "line": line})
            # increment not_found for group (ensure group key exists)
            group_stats[grp]["not_found"] += 1
            continue

        # SUCCESS lines
        m = re_success.search(line)
        if m:
            email = m.group("email").lower()
            uid = m.group("id")
            successes.append({"email": email, "id": uid, "line": line})
            unique_users_success.add(email)
            # Attempt to attribute success to most recent group by scanning previous lines is possible,
            # but simpler & reliable: if you have group in the same line previously it was recorded. We'll attempt
            # to map success to a group by searching the line for "-> <id>" matches to find the group key.
            # So: try to find last "Processing Row" group that had that user (best-effort).
            # We'll do a small pass later to attribute per-group successes using the log context.
            continue

        # Failures / Warnings / Errors
        if re_failed.search(line) or re_error.search(line) or re_warning.search(line) or line.startswith("❌") or "Exception" in line:
            failures.append(line)
            continue

        # Misc lines we keep for debug if needed
        other_info_lines.append(line)

# Second pass: attribute successes to groups by scanning log and matching email near a Processing Row
# Build a mapping of email -> last-seen group (simple streaming scan)
email_to_last_group = {}
with LOG_PATH.open("r", encoding="utf-8", errors="replace") as fh:
    current_group = None
    for line in fh:
        line = line.strip()
        m = re_processing.search(line)
        if m:
            current_group = m.group("group").strip()
            user = m.group("user").strip().lower()
            # map the username used on that row to the group (helpful for username fragment cases)
            if user:
                email_to_last_group[user] = current_group
            continue
        # also if a SUCCESS mentions an email, map that email to current_group
        m2 = re_success.search(line)
        if m2:
            email = m2.group("email").lower()
            if current_group:
                email_to_last_group[email] = current_group

# Now tally successes into group_stats using the best-effort mapping
for s in successes:
    email = s["email"]
    grp = email_to_last_group.get(email)
    if grp:
        group_stats[grp]["successes"] += 1
    else:
        # fallback: unknown-group bucket
        group_stats["<UNKNOWN>"]["successes"] += 1

# Build summary
total_successes = len(successes)
total_failures = len(failures)
total_not_found = len(not_found_rows)
total_unique_users_attempted = len(unique_users_attempted)
total_unique_users_success = len(unique_users_success)
total_rows_processed = total_rows_seen  # approximate from 'Processing' lines

# Top groups by attempts and successes
group_attempts_counter = Counter({g: v["attempts"] for g, v in group_stats.items()})
group_success_counter = Counter({g: v["successes"] for g, v in group_stats.items()})
top_attempted = group_attempts_counter.most_common(TOP_N_GROUPS)
top_successful = group_success_counter.most_common(TOP_N_GROUPS)

summary = {
    "log_file": str(LOG_PATH),
    "rows_processed_lines_found": total_rows_processed,
    "total_success_lines": total_successes,
    "total_failure_lines": total_failures,
    "total_not_found_group_lines": total_not_found,
    "unique_users_attempted": total_unique_users_attempted,
    "unique_users_succeeded": total_unique_users_success,
    "top_groups_by_attempts": top_attempted,
    "top_groups_by_successes": top_successful,
    "notes": "This summary is best-effort: mapping successes to groups is done using proximity heuristics (email -> last seen group)."
}

# Write summary JSON
with SUMMARY_JSON.open("w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=2)

# Write per-group CSV
with PER_GROUP_CSV.open("w", encoding="utf-8", newline="") as fh:
    writer = csv.writer(fh)
    writer.writerow(["group", "attempts", "successes", "not_found", "unique_users_count"])
    for g, stats in sorted(group_stats.items(), key=lambda kv: kv[1]["attempts"], reverse=True):
        writer.writerow([g, stats["attempts"], stats["successes"], stats["not_found"], len(stats["users"])])

# Write failed_rows CSV (errors, warnings, not found lines)
with FAILED_ROWS_CSV.open("w", encoding="utf-8", newline="") as fh:
    writer = csv.writer(fh)
    writer.writerow(["type", "row", "group", "user", "raw_line"])
    # not found rows
    for r in not_found_rows:
        writer.writerow(["group_not_found", r["row"], r["group"], "", r["line"]])
    # failures (best-effort attempt to extract row/group)
    for line in failures:
        # try to find row/group/user in the line
        m = re_processing.search(line)
        row = ""
        group = ""
        user = ""
        if m:
            row = m.group(1)
            group = m.group("group")
            user = m.group("user")
        writer.writerow(["failure", row, group, user, line])

print("Summary written to:", SUMMARY_JSON)
print("Per-group CSV written to:", PER_GROUP_CSV)
print("Failed rows CSV written to:", FAILED_ROWS_CSV)
