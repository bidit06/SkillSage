import os
import json
import pymongo
from pymongo.errors import BulkWriteError

# 1. Setup Connection
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = pymongo.MongoClient(MONGO_URL)
db = client["skillsage_db"]            # Change to your DB name
collection = db["unique_skill"]     # Change to your Collection name

# 2. Create a Unique Index (The Safety Lock)
# This strictly enforces that no two documents can have the same 'tool_name'
collection.create_index("tool_name", unique=True)
print("Unique index enforced on 'tool_name'.")

# 3. Load and Process Data
file_path = 'career_goals.json'  # Make sure this file is in the same folder
with open(file_path, 'r') as f:
    data = json.load(f)
    print("yup")

# Use a set to remove duplicates within the file itself first
unique_tools_set = set()
for item in data:
    # Safely get the list, defaulting to empty if missing
    tools = item.get('tools_and_technologies', [])
    unique_tools_set.update(tools)

# Prepare documents for MongoDB
mongo_docs = [{"tool_name": tool} for tool in sorted(list(unique_tools_set))]

# 4. Safe Insertion
if mongo_docs:
    try:
        # ordered=False allows the operation to continue even if one insert fails (is a duplicate)
        result = collection.insert_many(mongo_docs, ordered=False)
        print(f"Success! Inserted {len(result.inserted_ids)} new tools.")
        
    except BulkWriteError as bwe:
        # Calculate how many were inserted vs. duplicates
        total_attempted = len(mongo_docs)
        inserted_count = bwe.details['nInserted']
        duplicate_count = len(bwe.details['writeErrors'])
        
        print(f"Done. Inserted: {inserted_count}")
        print(f"Skipped (Duplicates): {duplicate_count}")
else:
    print("No tools found to insert.")