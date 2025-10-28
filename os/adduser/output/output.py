import re
import csv

def parse_output_log(input_file='output.txt'):
    """Parse the log file and categorize entries"""
    success_list = []
    user_not_found_list = []
    group_not_found_list = []
    other_user_list = []
    failed_list = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Check for processing row (start of new record)
        # Updated regex to handle apostrophes and special characters in group names
        process_match = re.search(r"Processing Row (\d+): Group='(.*?)', User='(.*?)'", line)
        if process_match:
            current_row = process_match.group(1)
            current_group = process_match.group(2)
            current_email = process_match.group(3)
            
            # Look ahead to see what happens with this record
            j = i + 1
            found_result = False
            
            while j < len(lines) and j < i + 15:  # Check next 15 lines max
                next_line = lines[j].strip()
                
                # Check for successful assignment
                if '✅ Successfully assigned' in next_line:
                    success_match = re.search(r'✅ Successfully assigned ([^\s]+) to group', next_line)
                    if success_match:
                        assigned_email = success_match.group(1)
                        
                        # Check if it's the same email or different (other user)
                        if assigned_email.lower() != current_email.lower():
                            other_user_list.append({
                                'clientname': current_group,
                                'email': current_email
                            })
                        else:
                            success_list.append({
                                'clientname': current_group,
                                'email': assigned_email
                            })
                        found_result = True
                        break
                
                # Check for group not found
                if f"Row {current_row}:" in next_line and "Group" in next_line and "not found" in next_line:
                    group_not_found_list.append({
                        'clientname': current_group,
                        'email': current_email
                    })
                    found_result = True
                    break
                
                # Check for user not found
                if f"Row {current_row}:" in next_line and "No users found for username" in next_line:
                    user_not_found_list.append({
                        'clientname': current_group,
                        'email': current_email
                    })
                    found_result = True
                    break
                
                # Check for ERROR followed by group not found (special case like Pet's Delight)
                if 'ERROR' in next_line and "Error searching group" in next_line:
                    # Look for the next WARNING line for this row
                    k = j + 1
                    while k < len(lines) and k < j + 3:
                        check_line = lines[k].strip()
                        if f"Row {current_row}:" in check_line and "not found" in check_line:
                            group_not_found_list.append({
                                'clientname': current_group,
                                'email': current_email
                            })
                            found_result = True
                            break
                        k += 1
                    if found_result:
                        break
                
                # Check for any other ERROR for this row
                if 'ERROR' in next_line and f"Row {current_row}:" in next_line and not found_result:
                    failed_list.append({
                        'clientname': current_group,
                        'email': current_email
                    })
                    found_result = True
                    break
                
                # Check for failure indicators
                if ('❌' in next_line or 'Failed' in next_line or 'failed' in next_line) and \
                   f"Row {current_row}" in next_line:
                    failed_list.append({
                        'clientname': current_group,
                        'email': current_email
                    })
                    found_result = True
                    break
                
                # Check if we hit another processing row (stop looking)
                if 'Processing Row' in next_line and f"Row {current_row}" not in next_line:
                    break
                    
                j += 1
            
            # If no result found, check if we missed something
            if not found_result:
                # This shouldn't happen, but if it does, put it in failed
                failed_list.append({
                    'clientname': current_group,
                    'email': current_email
                })
        
        i += 1
    
    return success_list, user_not_found_list, group_not_found_list, other_user_list, failed_list

def write_to_csv(data, filename):
    """Write data to CSV file with clientname and email headers"""
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['clientname', 'email']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        if data:
            # Sort by clientname then email
            data.sort(key=lambda x: (x['clientname'], x['email']))
            writer.writerows(data)
    print(f"✅ Created {filename} with {len(data)} entries")

def main():
    # Parse the log file
    success, user_not_found, group_not_found, other_user, failed = parse_output_log('output.txt')
    
    # Write to CSV files
    print("📊 Creating CSV files...")
    write_to_csv(success, 'success.csv')
    write_to_csv(user_not_found, 'usernotfound.csv')
    write_to_csv(group_not_found, 'groupnotfound.csv')
    write_to_csv(other_user, 'otheruser.csv')
    write_to_csv(failed, 'failed.csv')

if __name__ == "__main__":
    main()