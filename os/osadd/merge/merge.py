import pandas as pd

# Load CSVs without headers and assign column names manually
lot_df = pd.read_csv('lot.csv', header=None, names=['brandname', 'username'])
emails_df = pd.read_csv('emails.csv', header=None, names=['username', 'useremail'])

# Optional: clean whitespace in case data has extra spaces
lot_df['username'] = lot_df['username'].str.strip()
emails_df['username'] = emails_df['username'].str.strip()

# Merge — this will duplicate rows if one username has multiple emails
merged_df = lot_df.merge(emails_df, on='username', how='left')

# Reorder columns (optional)
merged_df = merged_df[['brandname', 'username', 'useremail']]

# Save result
merged_df.to_csv('merged_output.csv', index=False)

# Print to console
print(merged_df)