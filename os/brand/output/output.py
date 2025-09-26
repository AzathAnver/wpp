import os
import re

def parse_brand_log_file(input_filename, output_folder="parsed_logs"):
    # Create output folder if doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    with open(input_filename, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = content.split('🚀 Processing:')[1:]  # Skip first empty part

    success_entries = []
    already_exists_409_entries = []

    market_not_found_entries = []
    brand_not_found_entries = []
    category_not_found_entries = []

    other_errors_entries = []

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        header_line = lines[0].strip()

        # Extract fields using regex
        market_match = re.search(r'Market=([^,]+)', header_line)
        client_match = re.search(r'Client=([^,]+)', header_line)
        brand_match = re.search(r'Brand=([^,]+)', header_line)
        category_match = re.search(r'Category=(.+)', header_line)

        market = market_match.group(1).strip() if market_match else "Unknown"
        client = client_match.group(1).strip() if client_match else "Unknown"
        brand = brand_match.group(1).strip() if brand_match else "Unknown"
        category = category_match.group(1).strip() if category_match else "Unknown"

        # Format as clean CSV row
        csv_row = f"{market},{client},{brand},{category}"

        body = '\n'.join(lines[1:])

        # ✅ Success
        if '✅ Created Org Unit for Brand' in body:
            success_entries.append(csv_row)
            continue

        # ❌ 409 Conflict
        if '❌ Failed POST for' in body and ': 409' in body:
            already_exists_409_entries.append(csv_row)
            continue

        # ⚠️ Market Not Found
        if "⚠️ Error: Market '" in body and "with client '" in body and "not found." in body:
            market_not_found_entries.append(csv_row)
            continue

        # ⚠️ Brand Not Found
        if "⚠️ Error: Brand '" in body and "not found in API" in body:
            brand_not_found_entries.append(csv_row)
            continue

        # ⚠️ Category Not Found
        if "⚠️ Error: Category '" in body and "not found in category.json" in body:
            category_not_found_entries.append(csv_row)
            continue

        # ❗ Other Errors (including Python exceptions or unknown formats)
        if '⚠️ Error:' in body:
            clean_error = body.replace('\n', ' ').strip()
            other_errors_entries.append(csv_row + " | ERROR: " + clean_error)
            continue

        # Fallback: anything unrecognized
        other_errors_entries.append(csv_row + " | UNKNOWN STATUS: " + body.replace('\n', ' ').strip())

    # Helper to write file
    def write_file(filename, entries):
        with open(os.path.join(output_folder, filename), 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(entry + '\n')

    # Write all categorized files
    write_file('success.txt', success_entries)
    write_file('already_exists_409.txt', already_exists_409_entries)

    write_file('market_not_found.txt', market_not_found_entries)
    write_file('brand_not_found.txt', brand_not_found_entries)
    write_file('category_not_found.txt', category_not_found_entries)

    write_file('other_errors.txt', other_errors_entries)

    # Print summary
    print(f"📁 Output written to folder: '{output_folder}'")
    print(f"✅ Success: {len(success_entries)} entries")
    print(f"❌ Already Exists (409): {len(already_exists_409_entries)} entries")
    print(f"⚠️ Market Not Found: {len(market_not_found_entries)} entries")
    print(f"⚠️ Brand Not Found: {len(brand_not_found_entries)} entries")
    print(f"⚠️ Category Not Found: {len(category_not_found_entries)} entries")
    print(f"❗ Other Errors: {len(other_errors_entries)} entries")


# === MAIN ===
if __name__ == "__main__":
    input_file = "output.txt"   # 🔄 CHANGE TO YOUR LOG FILE
    parse_brand_log_file(input_file)