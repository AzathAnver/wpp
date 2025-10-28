import re
import csv

def parse_output_log(input_file='output.txt'):
    """Parse the log file and separate success and failed entries"""
    success_list = []
    failed_list = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line in lines:
        line = line.strip()
        if not line:  # Skip empty lines
            continue
        
        # Check if it's an error line
        if line.startswith('Error'):
            # Extract the tuple data from error line
            # Pattern: Error (market,client,brand,category): ...
            match = re.match(r'Error\s*\(([^,]+),([^,]+),([^,]+),([^)]+)\):', line)
            if match:
                market = match.group(1).strip()
                client = match.group(2).strip()
                brand = match.group(3).strip()
                category = match.group(4).strip()
                
                # Extract error message if needed
                error_msg_match = re.search(r':\s*(.+)$', line)
                error_message = error_msg_match.group(1) if error_msg_match else "Unknown error"
                
                failed_list.append({
                    'market': market,
                    'client': client,
                    'brand': brand,
                    'category': category,
                    'error_message': error_message
                })
        else:
            # It's a success line
            # Pattern: (market,client,brand,category): UUID
            match = re.match(r'\(([^,]+),([^,]+),([^,]+),([^)]+)\):\s*([a-f0-9\-]+)', line)
            if match:
                market = match.group(1).strip()
                client = match.group(2).strip()
                brand = match.group(3).strip()
                category = match.group(4).strip()
                uuid = match.group(5).strip()
                
                success_list.append({
                    'market': market,
                    'client': client,
                    'brand': brand,
                    'category': category,
                    'uuid': uuid
                })
    
    return success_list, failed_list

def write_success_csv(data, filename='success.csv'):
    """Write success data to CSV file"""
    if data:
        # Sort by client, then market, then brand
        data.sort(key=lambda x: (x['client'], x['market'], x['brand']))
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['market', 'client', 'brand', 'category', 'uuid']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"✅ Created {filename} with {len(data)} entries")
    else:
        # Create empty file with headers
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['market', 'client', 'brand', 'category', 'uuid']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        print(f"✅ Created {filename} with 0 entries")

def write_failed_csv(data, filename='failed.csv'):
    """Write failed data to CSV file"""
    if data:
        # Sort by client, then market, then brand
        data.sort(key=lambda x: (x['client'], x['market'], x['brand']))
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['market', 'client', 'brand', 'category', 'error_message']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"✅ Created {filename} with {len(data)} entries")
    else:
        # Create empty file with headers
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['market', 'client', 'brand', 'category', 'error_message']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        print(f"✅ Created {filename} with 0 entries")

def main():
    # Parse the log file
    success, failed = parse_output_log('output.txt')
    
    # Write to CSV files
    print("📊 Creating CSV files...")
    write_success_csv(success, 'success.csv')
    write_failed_csv(failed, 'failed.csv')

if __name__ == "__main__":
    main()