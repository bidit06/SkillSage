import os
import json
import chromadb
from chromadb.config import Settings
import google.generativeai as genai
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class CareerAdvisorRAG:
    def __init__(self):
        # 1. Initialize Google Gemini
        # Using a specific model version for better stability
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # 2. Initialize Local Embeddings
        print("⏳ Loading local embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        print("✅ Model loaded.")

        # 3. Initialize MongoDB
        self.mongo_client = MongoClient(os.getenv("MONGO_URI"))
        self.user_db = self.mongo_client.skillsage_db
        self.users_col = self.user_db.users
        
        # 4. Initialize Local ChromaDB
        print("📂 Connecting to Local ChromaDB...")
        self.chroma_client = chromadb.PersistentClient(path="./skillsage_chroma_db")
        
        self.kb_collection = self.chroma_client.get_or_create_collection(
            name="skillsage_vdb", 
            metadata={"hnsw:space": "cosine"}
        )
        print("✅ Connected to Vector Database.")

    def _get_embedding(self, text):
        embedding = self.embedder.encode(text)
        return embedding.tolist()

    def ingest_from_json(self, json_file_path):
        try:
            with open(json_file_path, 'r') as f:
                data = json.load(f)
            
            if isinstance(data, dict) and "skills" in data:
                schema_data_list = data["skills"]
            elif isinstance(data, list):
                schema_data_list = data
            else:
                print("❌ JSON format not recognized.")
                return

            print(f"🔄 Processing {len(schema_data_list)} items from {json_file_path}...")
            
            ids = []
            documents = []
            metadatas = []
            embeddings = []
            
            # TRACK SEEN IDs TO PREVENT DUPLICATES
            seen_ids = set()

            for item in schema_data_list:
                skill_name = item.get('skill_name', 'Unknown Skill')
                
                # --- DUPLICATE CHECK FIX ---
                if skill_name in seen_ids:
                    print(f"⚠️ Skipping duplicate skill: {skill_name}")
                    continue
                seen_ids.add(skill_name)
                # ---------------------------

                semantic_text = (
                    f"Skill: {skill_name}. "
                    f"Category: {item.get('category', 'General')}. "
                    f"Description: {item.get('description', '')} "
                    f"Difficulty: {item.get('difficulty_level', 'Medium')}. "
                    f"Time to learn: {item.get('learning_time', 'Variable')}. "
                    f"Industry Demand: {item.get('industry_demand', 'Medium')}. "
                    f"Used in careers: {', '.join(item.get('careers_using_this', []))}. "
                    f"Use cases: {', '.join(item.get('use_cases', []))}."
                )

                vector = self._get_embedding(semantic_text)

                ids.append(skill_name)
                documents.append(semantic_text)
                embeddings.append(vector)
                metadatas.append({
                    "category": item.get('category', 'General'),
                    "difficulty": item.get('difficulty_level', 'Medium'),
                    "demand": item.get('industry_demand', 'Medium')
                })

            if ids:
                self.kb_collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                print(f"✅ Successfully ingested {len(ids)} unique skills!")
            else:
                print("⚠️ No new unique skills found to ingest.")

        except Exception as e:
            print(f"❌ Error during ingestion: {str(e)}")

    def get_user_context(self, user_email):
        user = self.users_col.find_one({"email": user_email})
        if not user:
            return "User profile not found. Treat as a generic user."
        
        return (
            f"User Profile: {user.get('name', 'User')}. "
            f"Skills: {', '.join(user.get('skills', []))}. "
            f"Experience: {user.get('experience', 'Not specified')}. "
            f"Goal: {user.get('career_goal', 'Not specified')}."
        )

    def query_advisor(self, user_email, query):
        # 1. Get User Context
        user_context = self.get_user_context(user_email)
        
        # 2. Embed Query
        query_embedding = self._get_embedding(query)
        
        # 3. Retrieve from Chroma
        print(f"\n🔍 Searching Knowledge Base for: '{query}'...")
        results = self.kb_collection.query(
            query_embeddings=[query_embedding],
            n_results=3
        )
        
        # --- DEBUG PRINT START ---
        # This will show you EXACTLY what Chroma found (or if it found nothing)
        print("📊 Retrieval Results:")
        found_docs = results['documents'][0]
        for i, doc in enumerate(found_docs):
            print(f"   [Result {i+1}]: {doc[:100]}...") # Print first 100 chars
        # --- DEBUG PRINT END ---
        
        if not found_docs:
            print("⚠️ No relevant documents found in ChromaDB!")
            kb_context = "No specific data found in the Knowledge Base."
        else:
            kb_context = "\n".join(found_docs)
        
        # 4. Construct Prompt (Made stricter)
        full_prompt = f"""
        You are SkillSage, an AI Career Advisor.
        
        --- USER PROFILE ---
        {user_context}
        
        --- KNOWLEDGE BASE (SOURCE OF TRUTH) ---
        {kb_context}
        
        --- USER QUESTION ---
        {query}
        
        --- INSTRUCTIONS ---
        1. Answer ONLY using information from the 'KNOWLEDGE BASE' section above.
        2. If the Knowledge Base is empty or doesn't contain the answer, say: "I'm sorry, my internal database doesn't have information on that specific skill yet."
        3. Do NOT use your outside training data to make up skills.
        """
        
        # 5. Generate
        response = self.model.generate_content(full_prompt)
        return response.text

if __name__ == "__main__":
    advisor = CareerAdvisorRAG()

    # 1. LOAD DATA (It will now skip duplicates instead of crashing)
    #advisor.ingest_from_json("seed_data.json")

    # 2. TEST QUERY
    print("\n💬 Testing Query...")
    # Ensure you are using a valid email or the fallback will trigger
    response = advisor.query_advisor("test@example.com", "I want to learn Python. Is it good for Data Science?")
    print(f"\n🤖 SkillSage: {response}")