import re
import os

# File path
file_path = r"C:\Users\Azath.A\os\osadd\particularuser\osll.txt"

# Read the file content
with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

# Regex to extract email addresses
emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", content)

# Remove duplicates from current extraction
unique_emails = set(emails)

# Output file
output_path = r"C:\Users\Azath.A\os\osadd\particularuser\emailidspresent.txt"

# Read old emails if file exists
if os.path.exists(output_path):
    with open(output_path, "r", encoding="utf-8") as f:
        old_emails = set(line.strip() for line in f if line.strip())
else:
    old_emails = set()

# Merge old + new
all_emails = sorted(unique_emails.union(old_emails))

# Save merged list back
with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(all_emails))

print(len(all_emails), "emails saved in", output_path)
