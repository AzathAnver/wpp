import pandas as pd

# File paths
file1 = r"C:\Users\Azath.A\os\osadd\particularuser\input.txt"
file2 = r"C:\Users\Azath.A\os\osadd\particularuser\emailidspresent.txt"
output_file = r"C:\Users\Azath.A\os\osadd\particularuser\unique_emails.csv"



# Read CSVs (assuming each file has one column with email IDs)
emails1 = pd.read_csv(file1, header=None, names=["email"])
emails2 = pd.read_csv(file2, header=None, names=["email"])

# Normalize: strip spaces + lowercase
set1 = set(emails1["email"].str.strip().str.lower())
set2 = set(emails2["email"].str.strip().str.lower())

# Find emails only in one file
unique_emails = (set1 - set2) | (set2 - set1)

# Save result to CSV
pd.DataFrame(sorted(unique_emails), columns=["email"]).to_csv(output_file, index=False)

print(f"Unique emails saved to {output_file}")
