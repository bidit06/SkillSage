import chromadb

# 1. Connect to the existing database
# We use the exact path from your logs to ensure we read the real data
db_path = "/run/media/bidit/New Volume/skillsage_chroma_db"
client = chromadb.PersistentClient(path=db_path)

# 2. Get the collection
collection_name = "skillsage_vdb"

try:
    collection = client.get_collection(name=collection_name)
    
    # 3. Check the count
    count = collection.count()
    print(f"✅ Connection Successful!")
    print(f"📊 Total items in '{collection_name}': {count}")
    
    # 4. Peek at the data (shows the first 3 items)
    # This proves the data is actually retrievable
    print("\n🔍 Peeking at the first 3 items:")
    data = collection.peek(limit=3)
    
    # Pretty print the IDs and a snippet of the documents
    for i in range(len(data['ids'])):
        doc_snippet = data['documents'][i][:100] if data['documents'][i] else "No text"
        print(f"\nItem {i+1}:")
        print(f"  ID: {data['ids'][i]}")
        print(f"  Document Snippet: {doc_snippet}...")
        print(f"  Metadata: {data['metadatas'][i]}")

except Exception as e:
    print(f"❌ Error: {e}")
    print("Make sure the path is correct and the collection name matches exactly.")