import csv
import re

# Input and output file paths
log_file = "output.txt"
created_csv = "clients_created.csv"
found_csv = "clients_found.csv"
skipped_csv = "clients_skipped.csv"

# Prepare containers
created_clients = []
found_clients = []
skipped_clients = []

# Read the log file
with open(log_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Walk through log lines
for i, line in enumerate(lines):
    line = line.strip()
    
    if line.startswith("🔎 Processing brand:"):
        # Extract "raw brand name" after colon
        brand = line.split(":", 1)[1].strip()
        
        # Peek at following lines until we hit a message about its status
        if i + 1 < len(lines):
            next_line = lines[i+1].strip()
            
            # Case A: Created new group
            if next_line.startswith("✅ Created group"):
                match = re.search(r"name:\s*(.*)", next_line)
                brand_name = match.group(1).strip() if match else brand
                created_clients.append([brand_name])
            
            # Case B: Group already existed
            elif "Group already exists" in next_line:
                match = re.search(r"\| name:\s*(.*)", next_line)
                brand_name = match.group(1).strip() if match else brand
                found_clients.append([brand_name])
            
            # Case C: Skipped (no azId)
            elif "No azId found" in next_line:
                skipped_clients.append([brand])

# --- Save results ---

def write_csv(filename, header, rows):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([header])
        writer.writerows(rows)

write_csv(created_csv, "client_name", created_clients)
write_csv(found_csv, "client_name", found_clients)
write_csv(skipped_csv, "client_name", skipped_clients)

print(f"✅ Done! Extracted:")
print(f"   - {created_csv} ({len(created_clients)} names)")
print(f"   - {found_csv} ({len(found_clients)} names)")
print(f"   - {skipped_csv} ({len(skipped_clients)} names)")