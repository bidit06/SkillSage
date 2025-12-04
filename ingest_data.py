import os
import json
import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path
from typing import List, Dict, Any

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
CHROMA_DB_PATH = BASE_DIR / "skillsage_chroma_db"

print("="*70)
print("🚀 CAREER ADVISOR - DATA INGESTION SCRIPT")
print("="*70)
print(f"\n📂 Database Path: {CHROMA_DB_PATH}\n")

# Initialize ChromaDB (Persistent)
try:
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    print("✅ ChromaDB client initialized")
except Exception as e:
    print(f"❌ Failed to initialize ChromaDB: {e}")
    exit(1)

# Initialize Embedding Model (Local)
try:
    print("⏳ Loading embedding model (all-MiniLM-L6-v2)...")
    embedder = SentenceTransformer('all-MiniLM-L6-v2')
    print("✅ Embedding model loaded successfully\n")
except Exception as e:
    print(f"❌ Failed to load embedding model: {e}")
    exit(1)


def get_embedding(text: str) -> List[float]:
    """
    Generate embedding vector for given text
    
    Args:
        text: Input text to embed
        
    Returns:
        List of floats representing the embedding
    """
    try:
        return embedder.encode(text).tolist()
    except Exception as e:
        print(f"⚠️ Error generating embedding: {e}")
        return []


def format_career_content(item: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """
    Format career data into text and metadata
    
    Args:
        item: Career dictionary
        
    Returns:
        Tuple of (formatted_text, metadata)
    """
    title = item.get('career_title', 'Unknown Career')
    
    # Extract nested fields safely
    salary_range = item.get('salary_range', {})
    salary = salary_range.get('mid_level', 'N/A') if isinstance(salary_range, dict) else 'N/A'
    
    job_market = item.get('job_market', {})
    demand = job_market.get('demand', 'N/A') if isinstance(job_market, dict) else 'N/A'
    growth_rate = job_market.get('growth_rate', 'N/A') if isinstance(job_market, dict) else 'N/A'
    
    edu_req = item.get('education_requirements', {})
    min_edu = edu_req.get('minimum', 'N/A') if isinstance(edu_req, dict) else 'N/A'
    
    work_env = item.get('work_environment', {})
    work_type = work_env.get('type', 'N/A') if isinstance(work_env, dict) else 'N/A'
    
    # Build comprehensive text for embedding
    text = f"""Career: {title}
Category: {item.get('category', 'N/A')}
Description: {item.get('description', 'No description available')}
Required Skills: {', '.join(item.get('required_skills', [])[:20])}
Optional Skills: {', '.join(item.get('optional_skills', [])[:15])}
Minimum Education: {min_edu}
Experience Level: {item.get('experience_level', 'N/A')}
Responsibilities: {'; '.join(item.get('responsibilities', [])[:10])}
Salary Range: {salary}
Job Market Demand: {demand}
Growth Rate: {growth_rate}
Industries: {', '.join(item.get('industries', [])[:10])}
Work Environment: {work_type}
Related Careers: {', '.join(item.get('related_careers', [])[:8])}
Pros: {'; '.join(item.get('pros', [])[:5])}
Cons: {'; '.join(item.get('cons', [])[:5])}"""
    
    # Build metadata
    metadata = {
        "type": "career",
        "title": title,
        "category": item.get('category', ''),
        "demand": demand,
        "experience_level": item.get('experience_level', ''),
        "required_skills_count": len(item.get('required_skills', [])),
        "work_type": work_type
    }
    
    return text, metadata


def format_skill_content(item: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """
    Format skill data into text and metadata
    
    Args:
        item: Skill dictionary
        
    Returns:
        Tuple of (formatted_text, metadata)
    """
    title = item.get('skill_name', 'Unknown Skill')
    
    # Extract learning time
    lt_raw = item.get('learning_time', {})
    if isinstance(lt_raw, dict):
        learning_time = lt_raw.get('proficiency', 'Variable')
    else:
        learning_time = str(lt_raw)
    
    # Extract careers (handle multiple possible field names)
    careers = (item.get('career_applications', []) or 
               item.get('careers_using_this', []) or 
               [])
    
    text = f"""Skill: {title}
Category: {item.get('category', 'N/A')}
Subcategory: {item.get('subcategory', 'N/A')}
Description: {item.get('description', 'No description available')}
Difficulty Level: {item.get('difficulty_level', 'N/A')}
Learning Time to Proficiency: {learning_time}
Use Cases: {', '.join(item.get('use_cases', [])[:15])}
Related Skills: {', '.join(item.get('related_skills', [])[:15])}
Career Applications: {', '.join(careers[:15])}
Tools and Frameworks: {', '.join(item.get('tools_frameworks', [])[:10])}
Industry Demand: {item.get('industry_demand', 'N/A')}
Prerequisites: {', '.join(item.get('prerequisites', [])[:8])}
Certifications: {', '.join(item.get('certifications', [])[:5])}
Future Relevance: {item.get('future_relevance', 'N/A')}"""
    
    metadata = {
        "type": "skill",
        "title": title,
        "category": item.get('category', ''),
        "subcategory": item.get('subcategory', ''),
        "difficulty": item.get('difficulty_level', ''),
        "industry_demand": item.get('industry_demand', ''),
        "skill_type": item.get('skill_type', '')
    }
    
    return text, metadata


def format_faq_content(item: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """
    Format FAQ data into text and metadata
    
    Args:
        item: FAQ dictionary
        
    Returns:
        Tuple of (formatted_text, metadata)
    """
    title = item.get('question', 'Unknown Question')
    
    text = f"""Question: {title}
Category: {item.get('category', 'N/A')}
Answer: {item.get('answer', 'No answer available')}
Keywords: {', '.join(item.get('keywords', [])[:15])}
Related Questions: {', '.join(item.get('related_questions', [])[:5])}
Applicable Careers: {', '.join(item.get('applicable_careers', [])[:10])}
Applicable Skills: {', '.join(item.get('applicable_skills', [])[:10])}
Difficulty Level: {item.get('difficulty', 'N/A')}"""
    
    metadata = {
        "type": "faq",
        "title": title,
        "question": title,
        "category": item.get('category', ''),
        "difficulty": item.get('difficulty', ''),
        "popularity": item.get('popularity', 0)
    }
    
    return text, metadata


def ingest_collection(collection_name: str, data: List[Dict], type_label: str):
    """
    Ingest data into specified ChromaDB collection
    
    Args:
        collection_name: Name of the collection (careers/skills/faqs)
        data: List of items to ingest
        type_label: Type identifier (career/skill/faq)
    """
    # Get or create collection with cosine similarity
    try:
        collection = chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        print(f"❌ Error creating collection '{collection_name}': {e}")
        return
    
    ids = []
    documents = []
    embeddings = []
    metadatas = []
    
    seen_ids_in_batch = set()
    skipped = 0
    
    print(f"🔄 Processing {len(data)} items for '{collection_name}'...")

    for idx, item in enumerate(data):
        # --- 1. GENERATE UNIQUE ID ---
        if 'career_id' in item:
            item_id = item['career_id']
        elif 'skill_id' in item:
            item_id = item['skill_id']
        elif 'faq_id' in item:
            item_id = item['faq_id']
        elif 'skill_name' in item:  # Fallback for seed data
            clean_name = item['skill_name'].lower().replace(" ", "_").replace("-", "_")
            item_id = f"seed_{clean_name}"
        else:
            print(f"   ⚠️ Item {idx+1}: No identifiable ID, skipping")
            skipped += 1
            continue

        # Check for duplicates in current batch
        if item_id in seen_ids_in_batch:
            skipped += 1
            continue
        
        seen_ids_in_batch.add(item_id)

        # --- 2. FORMAT CONTENT BASED ON TYPE ---
        try:
            if type_label == "career":
                text, meta = format_career_content(item)
            elif type_label == "skill":
                text, meta = format_skill_content(item)
            elif type_label == "faq":
                text, meta = format_faq_content(item)
            else:
                print(f"   ⚠️ Unknown type '{type_label}' for item {idx+1}")
                skipped += 1
                continue
        except Exception as e:
            print(f"   ⚠️ Error formatting item {idx+1}: {e}")
            skipped += 1
            continue

        # --- 3. GENERATE EMBEDDING ---
        embedding = get_embedding(text)
        if not embedding:
            print(f"   ⚠️ Failed to generate embedding for item {idx+1}")
            skipped += 1
            continue

        # --- 4. ADD TO BATCH ---
        ids.append(item_id)
        documents.append(text)
        embeddings.append(embedding)
        metadatas.append(meta)

    # --- 5. BATCH UPSERT TO CHROMADB ---
    if ids:
        try:
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            print(f"✅ Successfully ingested {len(ids)} items into '{collection_name}'")
            print(f"   Total items in collection: {collection.count()}")
            if skipped > 0:
                print(f"   ⚠️ Skipped {skipped} items due to errors/duplicates")
        except Exception as e:
            print(f"❌ Error upserting to ChromaDB: {e}")
    else:
        print(f"⚠️ No valid items to ingest for '{collection_name}'")


def load_json_file(file_path: Path) -> List[Dict]:
    """
    Load and parse JSON file, handling nested structures
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        List of dictionaries
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            # Handle nested structures like {"skills": [...]}
            if isinstance(data, dict):
                # Try common wrapper keys
                for key in ['careers', 'skills', 'faqs', 'data', 'items']:
                    if key in data and isinstance(data[key], list):
                        return data[key]
                
                # If no common key, try first list value
                for value in data.values():
                    if isinstance(value, list):
                        return value
                
                print(f"   ⚠️ Data is a dict but no list found inside")
                return []
            
            elif isinstance(data, list):
                return data
            
            else:
                print(f"   ⚠️ Unexpected data type: {type(data)}")
                return []
                
    except json.JSONDecodeError as e:
        print(f"   ❌ JSON parsing error: {e}")
        return []
    except Exception as e:
        print(f"   ❌ Error reading file: {e}")
        return []


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    
    # Define datasets: (filename, collection_name, type_label)
    datasets = [
        ("careers_dataset.json", "careers", "career"),
        ("skills_dataset.json", "skills", "skill"),
        ("faqs_dataset.json", "faqs", "faq"),
        ("seed_data.json", "skills", "skill")  # Merge with skills collection
    ]

    total_processed = 0
    total_ingested = 0

    for filename, collection_name, data_type in datasets:
        file_path = BASE_DIR / filename
        
        print(f"\n{'='*70}")
        print(f"📄 FILE: {filename}")
        print(f"📦 COLLECTION: {collection_name}")
        print(f"🏷️  TYPE: {data_type}")
        print('='*70)
        
        if not file_path.exists():
            print(f"⚠️ File not found: {filename} (skipping)\n")
            continue
        
        # Load data
        data = load_json_file(file_path)
        
        if not data:
            print(f"⚠️ No data loaded from {filename} (skipping)\n")
            continue
        
        print(f"📊 Loaded {len(data)} items from file")
        total_processed += len(data)
        
        # Ingest into ChromaDB
        ingest_collection(collection_name, data, data_type)
        
        print()

    # --- FINAL SUMMARY ---
    print("\n" + "="*70)
    print("🎉 DATA INGESTION COMPLETE!")
    print("="*70)
    
    try:
        careers_count = chroma_client.get_collection("careers").count()
        skills_count = chroma_client.get_collection("skills").count()
        faqs_count = chroma_client.get_collection("faqs").count()
        total_in_db = careers_count + skills_count + faqs_count
        
        print(f"\n📊 FINAL DATABASE STATE:")
        print(f"   • Careers Collection:  {careers_count:>4} items")
        print(f"   • Skills Collection:   {skills_count:>4} items")
        print(f"   • FAQs Collection:     {faqs_count:>4} items")
        print(f"   {'─'*40}")
        print(f"   • Total in Database:   {total_in_db:>4} items")
        print(f"   • Files Processed:     {total_processed:>4} items")
        
    except Exception as e:
        print(f"\n⚠️ Could not retrieve collection counts: {e}")
    
    print("\n✅ Vector database is ready for RAG queries!")
    print(f"📂 Location: {CHROMA_DB_PATH}")
    print("="*70 + "\n")
