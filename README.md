OS Automation Scripts

This repository contains a set of Python scripts designed to automate client, brand, group, and market management tasks. Each script is modular and works with simple input files (CSV or TXT) to perform operations such as adding users, creating groups, and assigning clients to markets.

📂 Repository Structure
os/
├── adduser/        # Add emails to groups
├── brand/          # Add brands under clients
├── client/         # Validate and add clients
├── group/          # Create groups from TXT files
├── market/         # Add clients to specific markets
├── osadd/          # (users check in OS default group)
├── auth.env        # Authentication environment variables
├── category.json   # Category mappings
├── details.txt     # Reference/data file
├── nctest2.py      # Test script
├── newl.py         # Test script
└── Notes.txt       # Documentation notes

🚀 Scripts Overview
Folder / Script	Description: Input
adduser/	Adds email IDs to groups mentioned in the input.	CSV file: clientname, email. If the email ID is not present, then it will search for the username and add the email ID to that group
brand./	Add brands under a client.	CSV file: marketname,clientname,brandname, category. 
client/	Checks if a client exists in the hierarchy. If not present, attempts to add it. Returns 409 or 443 if already exists.	Inline (within script) / API
group/	Creates groups based on client names.	TXT file: clientname . If the Group is already present, then it will skip to the next.
market/	Assigns clients to specific markets.	TXT file: clientname
auth.env	Handles authentication (credentials, tokens, etc.).


🖥️ Usage

Each script can be run individually.

Add users to groups
python adduser/adduser.py input.csv

Add brands under clients
python brand/brand.py brand_input.csv

Create groups
python group/group.py groups.txt

Add clients to markets
python market/market.py market_clients.txt


🔑 Configuration
Store authentication details in auth.env (never commit secrets).
auth.py loads credentials and tokens automatically.
Adjust API endpoints or environment variables as needed.

📌 Notes
Make sure your input CSV/TXT files are properly formatted.
Error codes 409 or 443 indicate the client already exists.
Error 500, 400, 501 and 502 refer to the server being loaded and unable to process the API call. So either rerun the script with these failed codes or check the failure manually.
Use category.json for category mappings in the brand addition.

