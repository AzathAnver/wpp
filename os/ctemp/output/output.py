import re
import csv

def parse_output_log(input_file='output.txt'):
    # Initialize lists to store data for each category
    success_list = []
    already_exist_list = []
    failed_list = []
    
    # Extract market from the first line if present
    default_market = None
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Look for market in the header
    for line in lines[:5]:  # Check first few lines
        market_match = re.search(r'Market:\s*(.+?)$', line.strip())
        if market_match:
            default_market = market_match.group(1).strip()
            break
    
    i = 0
    current_client = None
    current_status = {'post1': None, 'post2': None}
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Check for new client processing
        if line.startswith('— Processing client:'):
            # Save previous client data if exists
            if current_client and (current_status['post1'] or current_status['post2']):
                categorize_client(current_client, default_market, current_status, 
                                 success_list, already_exist_list, failed_list)
            
            # Reset for new client
            current_client = None
            current_status = {'post1': None, 'post2': None}
            
            # Extract client name
            client_match = re.search(r'— Processing client:\s+(.+?)$', line)
            if client_match:
                current_client = client_match.group(1).strip()
        
        # Check for client/brand not found
        elif current_client and 'Client/Brand node not found' in line:
            failed_list.append({
                'client': current_client,
                'market': default_market or 'Japan'
            })
            current_client = None
            current_status = {'post1': None, 'post2': None}
        
        # Check for market resolution failure
        elif current_client and 'Could not resolve' in line and 'Market for' in line:
            # This means the market couldn't be found for this client
            failed_list.append({
                'client': current_client,
                'market': default_market or 'Japan'
            })
            current_client = None
            current_status = {'post1': None, 'post2': None}
        
        # Check for POST #1 status
        elif current_client and '→ POST #1 status:' in line:
            if '200 ✅' in line:
                current_status['post1'] = 'success'
            elif '400' in line:
                current_status['post1'] = 'already_exists'
        
        # Check for POST #2 status
        elif current_client and '→ POST #2 status:' in line:
            if '200 ✅' in line:
                current_status['post2'] = 'success'
            elif '400' in line:
                current_status['post2'] = 'already_exists'
        
        i += 1
    
    # Don't forget the last client
    if current_client and (current_status['post1'] or current_status['post2']):
        categorize_client(current_client, default_market, current_status, 
                         success_list, already_exist_list, failed_list)
    
    return success_list, already_exist_list, failed_list

def categorize_client(client, market, status, success_list, already_exist_list, failed_list):
    """Categorize client based on POST statuses"""
    market = market or 'Japan'  # Default to Japan if not specified
    
    # If POST #2 exists, use its status (market level is more specific)
    if status['post2']:
        if status['post2'] == 'success':
            success_list.append({'client': client, 'market': market})
        elif status['post2'] == 'already_exists':
            already_exist_list.append({'client': client, 'market': market})
    # If only POST #1 exists
    elif status['post1']:
        if status['post1'] == 'success':
            success_list.append({'client': client, 'market': market})
        elif status['post1'] == 'already_exists':
            already_exist_list.append({'client': client, 'market': market})

def write_to_csv(data, filename):
    """Write data to CSV file with client and market headers"""
    if data:
        # Sort data by client name for better readability
        data.sort(key=lambda x: x['client'])
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['client', 'market']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"✅ Created {filename} with {len(data)} entries")
    else:
        # Create empty file with headers
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['client', 'market']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        print(f"⚠️ Created {filename} with 0 entries (empty)")

def print_detailed_summary(success, already_exist, failed):
    """Print detailed summary of results"""
    print("\n📋 Detailed Results:")
    
    if success:
        print("\n✅ SUCCESS:")
        for item in sorted(success, key=lambda x: x['client']):
            print(f"   - {item['client']} ({item['market']})")
    
    if already_exist:
        print("\n⚠️ ALREADY EXISTS (Hierarchy not empty):")
        for item in sorted(already_exist, key=lambda x: x['client']):
            print(f"   - {item['client']} ({item['market']})")
    
    if failed:
        print("\n❌ FAILED (Client/Market not found):")
        for item in sorted(failed, key=lambda x: x['client']):
            print(f"   - {item['client']} ({item['market']})")

def main():
    # Parse the log file
    print("📄 Parsing output.txt file...")
    success, already_exist, failed = parse_output_log('output.txt')
    
    # Write to CSV files
    print("\n📊 Creating CSV files...")
    write_to_csv(success, 'success.csv')
    write_to_csv(already_exist, 'already_exist.csv')
    write_to_csv(failed, 'failed.csv')
    
    # Print summary
    print("\n📈 Summary:")
    print(f"   Success: {len(success)} clients")
    print(f"   Already Exist: {len(already_exist)} clients")
    print(f"   Failed: {len(failed)} clients")
    print(f"   Total: {len(success) + len(already_exist) + len(failed)} clients")
    
    # Print detailed summary (optional - comment out if not needed)
    print_detailed_summary(success, already_exist, failed)

if __name__ == "__main__":
    main()