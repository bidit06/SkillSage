import os
import json
import chromadb
import google.generativeai as genai
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class CareerAdvisorRAG:
    def __init__(self):
        # 1. Initialize Google Gemini
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is missing in .env")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # 2. Initialize Local Embeddings
        print("⏳ Loading local embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        print("✅ Model loaded.")

        # 3. Initialize MongoDB (Sync Driver)
        # FIX: Using MONGO_URL to match main.py
        mongo_uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
        self.mongo_client = MongoClient(mongo_uri)
        self.user_db = self.mongo_client.skillsage_db
        self.users_col = self.user_db.users
        print("✅ Connected to MongoDB (Sync).")
        
        # 4. Initialize Local ChromaDB
        print("📂 Connecting to Local ChromaDB...")
        self.chroma_client = chromadb.PersistentClient(path="./skillsage_chroma_db")
        
        self.kb_collection = self.chroma_client.get_or_create_collection(
            name="skillsage_vdb", 
            metadata={"hnsw:space": "cosine"}
        )
        
        # Collection for Careers
        self.careers_collection = self.chroma_client.get_or_create_collection(
            name="skillsage_careers_vdb",
            metadata={"hnsw:space": "cosine"}
        )
        print("✅ Connected to Vector Database.")

    def _get_embedding(self, text):
        embedding = self.embedder.encode(text)
        return embedding.tolist()

    def get_user_context(self, user_email):
        """
        Fetches user profile from MongoDB to personalize the answer.
        """
        print(f"🔍 Fetching profile for: {user_email}")
        user = self.users_col.find_one({"email": user_email})
        
        if not user:
            print("⚠️ User not found in DB.")
            return "User Profile: Guest (No specific data)."
        
        # Construct a rich profile string
        context = (
            f"User Name: {user.get('name', 'User')}\n"
            f"Current Role: {user.get('current_activity', 'Not specified')}\n"
            f"Career Goal: {user.get('career_goal', 'Not specified')}\n"
            f"Current Skills: {', '.join(user.get('skills', []))}\n"
            f"Experience Level: {user.get('employment_status', 'Not specified')}\n"
            f"Location: {user.get('location', 'Not specified')}"
        )
        print("✅ User Context Loaded.")
        return context

    def query_advisor(self, user_email, query):
        # 1. Get User Context (Personalization)
        user_context = self.get_user_context(user_email)
        
        # 2. Embed Query & Retrieve RAG Data
        query_embedding = self._get_embedding(query)
        results = self.kb_collection.query(
            query_embeddings=[query_embedding],
            n_results=3
        )
        
        found_docs = results['documents'][0]
        if found_docs:
            kb_context = "\n".join(found_docs)
        else:
            kb_context = "No specific internal data found on this topic."
        
        # 3. Hybrid Prompt (Profile + RAG + General Knowledge)
        full_prompt = f"""
        You are 'Orion', an expert AI Career Advisor.
        
        --- 👤 USER PROFILE (Personalize for this person) ---
        {user_context}
        
        --- 📚 INTERNAL KNOWLEDGE BASE (Use if relevant) ---
        {kb_context}
        
        --- ❓ USER QUESTION ---
        {query}
        
        --- 🧠 INSTRUCTIONS ---
        1. **Personalize**: Address the user by name. Relate your advice to their 'Current Skills' and 'Career Goal'.
        2. **Synthesize**: Combine the 'Internal Knowledge Base' facts with your own general expert knowledge.
        3. **Gap Analysis**: If they ask about a role, compare it to their 'Current Skills' and suggest what they are missing.
        4. **Tone**: Encouraging, professional, and actionable.
        5. **Format**: Use clean Markdown (bullet points, bold text) for readability.
        """
        
        # 4. Generate Response
        try:
            response = self.model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            return f"I encountered an error generating the response: {str(e)}"

    # ... (Keep the rest of the ingestion logic/gap analysis functions if needed) ...
    # You can copy the 'ingest_careers_from_json', 'get_career_recommendations', 
    # and 'analyze_skill_gap' methods from the previous code here.