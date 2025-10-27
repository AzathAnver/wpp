import re
import csv

def parse_output_log(input_file='output.txt'):
    # Initialize lists to store data for each category
    sucess_list = []
    already_exist_list = []
    failed_list = []
    
    current_client = None
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Check for new client processing
        if line.startswith('— Processing client:'):
            # Extract client name and markets
            client_match = re.search(r'— Processing client: (.+?) \(markets?: (.+?)\)', line)
            if client_match:
                current_client = client_match.group(1).strip()
                # Skip if it's just "client" (generic placeholder)
                if current_client.lower() == 'client':
                    # Check next line for client/brand not found
                    if i + 1 < len(lines) and 'Client/Brand node not found' in lines[i + 1]:
                        markets = client_match.group(2).strip()
                        # Split markets and add to failed list
                        market_list = [m.strip() for m in markets.split(',')]
                        for market in market_list:
                            if market.lower() != 'market':  # Skip generic "market"
                                failed_list.append({
                                    'client': current_client,
                                    'market': market
                                })
                    current_client = None
        
        # Process market results for valid clients
        elif current_client:
            # Check for sucessful market processing (status 200)
            if '→ POST #2 status: 200 ✅ (Template applied to market)' in line:
                # Get the previous line to find the market name
                if i > 0:
                    prev_line = lines[i-1].strip()
                    market_match = re.search(r"✅ Processing market '(.+?)':", prev_line)
                    if market_match:
                        market = market_match.group(1)
                        sucess_list.append({
                            'client': current_client,
                            'market': market
                        })
            
            # Check for already existing market (status 400)
            elif '→ POST #2 status: 400 ⚠️ (Template already applied to market)' in line:
                # Get the previous line to find the market name
                if i > 0:
                    prev_line = lines[i-1].strip()
                    market_match = re.search(r"✅ Processing market '(.+?)':", prev_line)
                    if market_match:
                        market = market_match.group(1)
                        already_exist_list.append({
                            'client': current_client,
                            'market': market
                        })
            
            # Check for markets that could not be resolved
            elif '⚠️ Could not resolve market' in line:
                market_match = re.search(r"Could not resolve market '(.+?)' for '(.+?)':", line)
                if market_match:
                    market = market_match.group(1)
                    failed_list.append({
                        'client': current_client,
                        'market': market
                    })
        
        i += 1
    
    return sucess_list, already_exist_list, failed_list

def write_to_csv(data, filename):
    """Write data to CSV file with client and market headers"""
    if data:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['client', 'market']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"✅ Created {filename} with {len(data)} entries")
    else:
        print(f"⚠️ No data to write for {filename}")

def main():
    # Parse the log file
    print("📄 Parsing output.txt file...")
    sucess, already_exist, failed = parse_output_log('output.txt')
    
    # Write to CSV files
    print("\n📊 Creating CSV files...")
    write_to_csv(sucess, 'sucess.csv')
    write_to_csv(already_exist, 'already_exist.csv')
    write_to_csv(failed, 'failed.csv')
    
    # Print summary
    print("\n📈 Summary:")
    print(f"   Success: {len(sucess)} entries")
    print(f"   Already Exist: {len(already_exist)} entries")
    print(f"   Failed: {len(failed)} entries")
    print(f"   Total: {len(sucess) + len(already_exist) + len(failed)} entries")

if __name__ == "__main__":
    main()