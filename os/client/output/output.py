import re

def parse_log_file(input_filename):
    with open(input_filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by "🔍 Processing client: " to get each client block
    blocks = content.split('🔍 Processing client: ')[1:]  # Skip first empty if any

    success_clients = []
    not_found_clients = []
    already_exists_409_clients = []
    unable_to_do_400_clients = []

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        # First line is client name
        client_name = lines[0].strip()

        # Join remaining lines for easier parsing
        body = '\n'.join(lines[1:])

        # Check for success
        if '✅ Successfully created' in body:
            success_clients.append(client_name)
            continue

        # Check for 400 error
        if '❌ Failed for' in body and ': 400' in body:
            unable_to_do_400_clients.append(client_name)
            continue

        # Check for 409 error
        if 'Found exact client' in body:
            already_exists_409_clients.append(client_name)
            continue

        # Check for "not found" messages
        if ("⚠️ Client '" + client_name + "' not found in API search.") in body or \
           ("⚠️ Not found in hierarchy: " + client_name) in body:
            not_found_clients.append(client_name)
            continue

        # Fallback: if none match, log as unknown (optional, you can skip or classify differently)
        # For now, we'll treat unclassified as not found
        not_found_clients.append(client_name)

    # Write to files
    with open('success.txt', 'w', encoding='utf-8') as f:
        for client in success_clients:
            f.write(client + '\n')

    with open('not_found.txt', 'w', encoding='utf-8') as f:
        for client in not_found_clients:
            f.write(client + '\n')

    with open('already_exists_409.txt', 'w', encoding='utf-8') as f:
        for client in already_exists_409_clients:
            f.write(client + '\n')

    with open('unable_to_do_400.txt', 'w', encoding='utf-8') as f:
        for client in unable_to_do_400_clients:
            f.write(client + '\n')

    print(f"✅ Success: {len(success_clients)} clients")
    print(f"⚠️ Not Found: {len(not_found_clients)} clients")
    print(f"❌ Already Exists (409): {len(already_exists_409_clients)} clients")
    print(f"❌ Unable to Do (400): {len(unable_to_do_400_clients)} clients")
    print("📁 Files written: success.txt, not_found.txt, already_exists_409.txt, unable_to_do_400.txt")


# Usage
if __name__ == "__main__":
    input_file = "output.txt"  # <-- Change this to your actual input filename
    parse_log_file(input_file)