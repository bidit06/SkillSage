import os
import json
import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path

# --- CONFIGURATION ---
# Define paths relative to this script (backend/ingest_data.py)
BASE_DIR = Path(__file__).resolve().parent
# Ensure the database is stored INSIDE the backend folder as requested
CHROMA_DB_PATH = BASE_DIR / "skillsage_chroma_db"

print(f"📂 Database Path: {CHROMA_DB_PATH}")

# Initialize ChromaDB (Persistent)
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))

# Initialize Embedding Model (Local)
print("⏳ Loading embedding model (all-MiniLM-L6-v2)...")
embedder = SentenceTransformer('all-MiniLM-L6-v2')
print("✅ Model loaded.")

def get_embedding(text):
    return embedder.encode(text).tolist()

def ingest_collection(collection_name, data, type_label):
    collection = chroma_client.get_or_create_collection(name=collection_name)
    
    ids = []
    documents = []
    embeddings = []
    metadatas = []
    
    # Track IDs seen in this batch to prevent duplicates causing a crash
    seen_ids_in_batch = set()
    
    print(f"🔄 Processing {len(data)} items for '{collection_name}'...")

    for item in data:
        # --- 1. ID GENERATION LOGIC ---
        if 'career_id' in item:
            item_id = item['career_id']
            title = item.get('career_title', 'Unknown Career')
        elif 'skill_id' in item:
            item_id = item['skill_id']
            title = item.get('skill_name', 'Unknown Skill')
        elif 'faq_id' in item:
            item_id = item['faq_id']
            title = item.get('question', 'Unknown Question')
        elif 'skill_name' in item: # Fallback for seed_data.json
            clean_name = item['skill_name'].lower().replace(" ", "_")
            item_id = f"seed_{clean_name}"
            title = item['skill_name']
        else:
            print(f"⚠️ Skipping item with no identifiable ID: {item}")
            continue

        # --- DUPLICATE CHECK ---
        if item_id in seen_ids_in_batch:
            # print(f"⚠️ Skipping duplicate ID in this batch: {item_id}")
            continue
        
        seen_ids_in_batch.add(item_id)

        # --- 2. CONTENT FORMATTING (The Text AI Reads) ---
        if type_label == "career":
            salary = item.get('salary_range', {}).get('mid_level', 'N/A')
            demand = item.get('job_market', {}).get('demand', 'N/A')
            
            text = (
                f"Career: {title}. "
                f"Category: {item.get('category', '')}. "
                f"Description: {item.get('description', '')} "
                f"Salary: {salary}. "
                f"Demand: {demand}. "
                f"Skills Needed: {', '.join(item.get('required_skills', []))}. "
                f"Education: {item.get('education_requirements', {}).get('minimum', '')}."
            )
            
        elif type_label == "skill":
            lt_raw = item.get('learning_time', 'N/A')
            if isinstance(lt_raw, dict):
                learning_time = lt_raw.get('proficiency', 'Variable')
            else:
                learning_time = str(lt_raw)

            careers = item.get('career_applications', []) or item.get('careers_using_this', [])

            text = (
                f"Skill: {title}. "
                f"Category: {item.get('category', '')}. "
                f"Description: {item.get('description', '')} "
                f"Difficulty: {item.get('difficulty_level', '')}. "
                f"Time to learn: {learning_time}. "
                f"Use Cases: {', '.join(item.get('use_cases', []))}. "
                f"Related Careers: {', '.join(careers)}."
            )
            
        elif type_label == "faq":
            text = (
                f"Question: {title} "
                f"Answer: {item.get('answer', '')} "
                f"Category: {item.get('category', '')}."
            )
        else:
            text = str(item)

        # --- 3. METADATA ---
        meta = {
            "type": type_label,
            "title": title
        }
        
        ids.append(item_id)
        documents.append(text)
        embeddings.append(get_embedding(text))
        metadatas.append(meta)

    # --- 4. BATCH UPSERT ---
    if ids:
        try:
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            print(f"✅ Successfully ingested {len(ids)} into '{collection_name}'!")
        except Exception as e:
            print(f"❌ Error upserting batch to ChromaDB: {e}")
    else:
        print("⚠️ No valid items to ingest.")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # List of files and their logical type
    datasets = [
        ("careers_dataset.json", "career"),
        ("skills_dataset.json", "skill"),
        ("faqs_dataset.json", "faq"),
        ("seed_data.json", "skill")
    ]

    for filename, data_type in datasets:
        file_path = BASE_DIR / filename
        
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    # Logic to unwrap data if it's inside a key like "skills": []
                    if isinstance(data, dict):
                        keys = list(data.keys())
                        for k in keys:
                            if isinstance(data[k], list):
                                data = data[k]
                                break
                        if isinstance(data, dict): 
                            print(f"⚠️ Structure warning in {filename}: could not find main list.")
                            continue

                    if isinstance(data, list):
                        ingest_collection("skillsage_vdb", data, data_type)
                    else:
                        print(f"❌ Format error in {filename}: Expected a list.")
            except Exception as e:
                print(f"❌ Error processing {filename}: {e}")
        else:
            print(f"⚠️ File not found: {filename}")

    print("\n🎉 All Data Ingestion Complete!")