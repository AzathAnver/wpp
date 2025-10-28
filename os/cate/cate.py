#!/usr/bin/env python3

def read_file_lines(filename):
    """Read file and return cleaned lines"""
    with open(filename, 'r') as f:
        # Strip whitespace and convert to uppercase for comparison
        return set(line.strip().upper() for line in f if line.strip())

def compare_files(cate_file='cate.txt', data_file='data.txt'):
    """Compare files and find unique items in data.txt"""
    
    # Read both files
    cate_items = read_file_lines(cate_file)
    data_items = read_file_lines(data_file)
    
    # Find items in data.txt but not in cate.txt
    unique_items = data_items - cate_items
    
    # Display results
    print(f"Total items in cate.txt: {len(cate_items)}")
    print(f"Total items in data.txt: {len(data_items)}")
    print(f"Unique items in data.txt (not in cate.txt): {len(unique_items)}")
    print("\n" + "="*50)
    
    if unique_items:
        print("Items present in data.txt but NOT in cate.txt:\n")
        for item in sorted(unique_items):
            print(f"  - {item}")
    else:
        print("No unique items found. All items in data.txt exist in cate.txt.")
    
    # Optional: Find items in cate.txt but not in data.txt
    reverse_unique = cate_items - data_items
    if reverse_unique:
        print("\n" + "="*50)
        print("Items present in cate.txt but NOT in data.txt:\n")
        for item in sorted(reverse_unique):
            print(f"  - {item}")

if __name__ == "__main__":
    compare_files()