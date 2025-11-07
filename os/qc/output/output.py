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
        if not line:
            continue
        
        # Handle success lines: Found row(...)
        # Match until ): to get everything inside parentheses
        success_match = re.match(r'Found row\((.*?)\):\s*([a-f0-9\-]+)', line, re.IGNORECASE)
        if success_match:
            params = success_match.group(1)
            uuid = success_match.group(2).strip()
            
            # Split by comma and handle the 4 expected fields
            parts = [p.strip() for p in params.split(',')]
            if len(parts) >= 4:
                # Join back any extra commas that might be in category
                market = parts[0]
                client = parts[1]
                brand = parts[2]
                category = ','.join(parts[3:])  # Join remaining parts
                
                success_list.append({
                    'market': market,
                    'client': client,
                    'brand': brand,
                    'category': category,
                    'uuid': uuid
                })
            continue
        
        # Handle error lines: Error (...)
        error_match = re.match(r'Error\s*\((.*?)\):\s*(.+)', line, re.IGNORECASE)
        if error_match:
            params = error_match.group(1)
            error_message = error_match.group(2).strip()
            
            # Split by comma and handle the 4 expected fields
            parts = [p.strip() for p in params.split(',')]
            if len(parts) >= 4:
                # Join back any extra commas that might be in category
                market = parts[0]
                client = parts[1]
                brand = parts[2]
                category = ','.join(parts[3:])  # Join remaining parts
                
                failed_list.append({
                    'market': market,
                    'client': client,
                    'brand': brand,
                    'category': category,
                    'error_message': error_message
                })
            elif len(parts) == 3:
                # Handle cases where category might be missing
                market = parts[0]
                client = parts[1]
                brand = parts[2]
                category = ''
                
                failed_list.append({
                    'market': market,
                    'client': client,
                    'brand': brand,
                    'category': category,
                    'error_message': error_message
                })
            else:
                print(f"⚠️  Could not parse error line: {line}")
        else:
            # Line didn't match either pattern
            if line.startswith('Error') or line.startswith('Found'):
                print(f"⚠️  Could not parse line: {line}")
    
    return success_list, failed_list


def write_success_csv(data, filename='success.csv'):
    if data:
        data.sort(key=lambda x: (x['client'], x['market'], x['brand']))
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['market', 'client', 'brand', 'category', 'uuid']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"✅ Created {filename} with {len(data)} entries")
    else:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['market', 'client', 'brand', 'category', 'uuid']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        print(f"✅ Created {filename} with 0 entries")

def write_failed_csv(data, filename='failed.csv'):
    if data:
        data.sort(key=lambda x: (x['client'], x['market'], x['brand']))
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['market', 'client', 'brand', 'category', 'error_message']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"✅ Created {filename} with {len(data)} entries")
    else:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['market', 'client', 'brand', 'category', 'error_message']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        print(f"✅ Created {filename} with 0 entries")

def main():
    success, failed = parse_output_log('output.txt')
    print("📊 Creating CSV files...")
    print(f"📈 Parsed {len(success)} successful entries")
    print(f"📉 Parsed {len(failed)} failed entries")
    write_success_csv(success, 'success.csv')
    write_failed_csv(failed, 'failed.csv')

if __name__ == "__main__":
    main()