import chromadb

# Connect to the same database folder
try:
    client = chromadb.PersistentClient(path="./skillsage_chroma_db")
    collection = client.get_collection("skillsage_vdb")
    
    print(f"📊 Total items in database: {collection.count()}")
    
    # Peek at the data
    data = collection.peek(limit=10)
    print("\n🔍 First 10 IDs (Skill Names):")
    print(data['ids'])

except Exception as e:
    print(f"❌ Error reading database: {e}")