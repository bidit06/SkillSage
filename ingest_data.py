import os
import json
import chromadb
from sentence_transformers import SentenceTransformer
from pymongo import MongoClient
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
CHROMA_DB_PATH = BASE_DIR / "skillsage_chroma_db"
# CRITICAL: Ensure this matches your main.py database
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = "skillsage_db" 

print("="*70)
print(f"🚀 DATA INGESTION - TARGET DB: {DB_NAME}")
print("="*70)

# 1. Initialize MongoDB
try:
    mongo_client = MongoClient(MONGO_URL)
    db = mongo_client[DB_NAME]
    careers_col = db.careers
    # Clear existing careers to prevent duplicates/stale data
    careers_col.delete_many({})
    print(f"✅ MongoDB '{DB_NAME}.careers' collection cleared and ready.")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")
    exit(1)

# 2. Initialize ChromaDB (For Chat Context Only)
try:
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    try: chroma_client.delete_collection("careers")
    except: pass
    chroma_careers = chroma_client.create_collection(name="careers", metadata={"hnsw:space": "cosine"})
    print("✅ ChromaDB initialized for Chat.")
except Exception as e:
    print(f"❌ ChromaDB Error: {e}")
    exit(1)

# Initialize Embedding Model
print("⏳ Loading Embedding Model...")
embedder = SentenceTransformer('all-MiniLM-L6-v2')

def load_json(filename):
    path = BASE_DIR / filename
    if not path.exists(): 
        print(f"⚠️ Warning: {filename} not found")
        return []
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

# --- LOAD DATA ---
career_goals = load_json("career_goals.json")
roadmaps = load_json("roadmap.json")

print(f"\n🔄 Processing Data...")

mongo_docs = []
processed_goals = set()

# --- PHASE 1: INGEST ROADMAPS (High Priority - Has specific Levels) ---
for item in roadmaps:
    name = item.get("career_goal")
    if not name: continue
    
    # Extract skills: { "Python": 9, "SQL": 8 }
    tech_skills = item.get('required_skills', {}).get('technical_skills', [])
    skills_map = {s['skill']: s['required_level'] for s in tech_skills}
    
    doc = {
        "title": name,
        "description": item.get("description"),
        "type": "roadmap",
        "required_skills": skills_map, # Structured map for Radar Chart
        "salary": item.get("estimated_salary_range", {})
    }
    mongo_docs.append(doc)
    processed_goals.add(name.lower().strip())

# --- PHASE 2: INGEST CAREER GOALS (Fallback - Has Tools List) ---
for item in career_goals:
    name = item.get("career_goal_name")
    # If we already have a roadmap for this goal, skip it (roadmap is better)
    if not name or name.lower().strip() in processed_goals: continue
    
    # Career goals file has "tools_and_technologies" (list of strings)
    # We assign a default level of 8 to these skills so they show up on the chart
    tools = item.get('tools_and_technologies', [])
    skills_map = {t: 8 for t in tools[:12]} # Limit to top 12 to fit on chart
    
    doc = {
        "title": name,
        "description": item.get("description"),
        "type": "career_profile",
        "required_skills": skills_map,
        "salary": item.get("salary_range", {})
    }
    mongo_docs.append(doc)

# Insert into MongoDB
if mongo_docs:
    careers_col.insert_many(mongo_docs)
    print(f"✅ Ingested {len(mongo_docs)} career documents into MongoDB.")

# --- PHASE 3: CHROMA INGESTION (For Chat RAG) ---
c_ids, c_docs, c_metas, c_vecs = [], [], [], []

for doc in mongo_docs:
    # Flatten skills for text embedding for the chatbot to read
    skills_str = ", ".join([f"{k} (Level {v})" for k, v in doc['required_skills'].items()])
    
    text = f"""ROLE: {doc['title']}
DESCRIPTION: {doc['description']}
REQUIRED SKILLS: {skills_str}
SALARY: {doc.get('salary', {}).get('india', 'N/A')}
"""
    c_ids.append(f"career_{doc['title'].replace(' ', '_').replace('/', '-')}")
    c_docs.append(text)
    c_metas.append({"title": doc['title']})
    c_vecs.append(embedder.encode(text).tolist())

if c_ids:
    chroma_careers.upsert(ids=c_ids, documents=c_docs, embeddings=c_vecs, metadatas=c_metas)
    print(f"✅ Ingested {len(c_ids)} documents into ChromaDB for Chat.")

print("\n🎉 Migration Complete! Run 'python ingest_data.py' once to apply changes.")