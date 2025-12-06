import os
import json
import chromadb
import google.generativeai as genai
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple, Union, Any
import logging
import random 

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class CareerAdvisorRAG:
    """
    AI Career Advisor RAG System
    """
    
    def __init__(self, prompt_mode: str = "balanced"):
        self.prompt_mode = prompt_mode
        logger.info("🚀 Initializing Career Advisor RAG System...")
        
        self._init_gemini()
        self._init_embedder()
        self._init_mongodb()
        self._init_chromadb()
        self.system_prompt = self._load_system_prompt()
        
        logger.info("✅ RAG System initialized successfully!\n")

    def _init_gemini(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key: raise ValueError("❌ GOOGLE_API_KEY is missing in .env file")
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            logger.info("✅ Gemini API configured")
        except Exception as e:
            logger.error(f"❌ Failed to configure Gemini: {e}")
            raise

    def _init_embedder(self):
        try:
            logger.info("⏳ Loading embedding model (all-MiniLM-L6-v2)...")
            self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("✅ Embedding model loaded")
        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            raise

    def _init_mongodb(self):
        mongo_uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
        try:
            self.mongo_client = MongoClient(mongo_uri)
            self.user_db = self.mongo_client.skillsage_db
            self.users_col = self.user_db.users
            self.mongo_client.server_info()
            logger.info("✅ Connected to MongoDB")
        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise

    def _init_chromadb(self):
        try:
            logger.info("📂 Connecting to ChromaDB...")
            self.chroma_client = chromadb.PersistentClient(path="./skillsage_chroma_db")
            self.careers_collection = self.chroma_client.get_or_create_collection(name="careers", metadata={"hnsw:space": "cosine"})
            self.skills_collection = self.chroma_client.get_or_create_collection(name="skills", metadata={"hnsw:space": "cosine"})
            self.faqs_collection = self.chroma_client.get_or_create_collection(name="faqs", metadata={"hnsw:space": "cosine"})
            logger.info(f"✅ Connected to ChromaDB")
        except Exception as e:
            logger.error(f"❌ Failed to connect to ChromaDB: {e}")
            raise

    def _load_system_prompt(self) -> str:
        if self.prompt_mode == "concise": return self._concise_prompt()
        elif self.prompt_mode == "detailed": return self._detailed_prompt()
        else: return self._balanced_prompt()

    def _concise_prompt(self) -> str:
        return """You are Orion, an AI Career Advisor. Provide personalized guidance using User Profile and Knowledge Base. Be specific and actionable."""

    def _balanced_prompt(self) -> str:
        return """You are Orion, an AI Career Advisor providing personalized career guidance.
## RESPONSE GUIDELINES
1. Direct answer to the question
2. Why it's relevant to user's profile
3. Specific requirements or skills needed
4. Realistic expectations
5. Actionable next steps
Use User Profile and Knowledge Base facts."""

    def _detailed_prompt(self) -> str:
        return """You are Orion, an intelligent AI Career Advisor. Provide highly detailed, data-driven advice tailored to the user."""

    def _get_embedding(self, text: str) -> List[float]:
        try:
            embedding = self.embedder.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"❌ Error generating embedding: {e}")
            return []

    # --------------------------------------------------------------------------
    #  CORE RAG METHODS
    # --------------------------------------------------------------------------

    def get_user_context(self, user_email: str) -> str:
        logger.info(f"🔍 Fetching profile for: {user_email}")
        try:
            user = self.users_col.find_one({"email": user_email})
            if not user: return "**User Profile:** Guest user"
            return f"""## USER PROFILE
**Name:** {user.get('name', 'User')}
**Career Goal:** {user.get('career_goal', 'Exploring')}
**Current Skills:** {', '.join(user.get('skills', []))}
"""
        except Exception as e:
            logger.error(f"❌ Error fetching user context: {e}")
            return "Error loading profile"

    def retrieve_context(self, query: str, n_careers: int = 3, n_skills: int = 5, n_faqs: int = 2) -> Dict[str, List[Dict]]:
        query_embedding = self._get_embedding(query)
        if not query_embedding: return {"careers": [], "skills": [], "faqs": []}
        
        retrieved = {"careers": [], "skills": [], "faqs": []}
        
        def query_col(col, key, n):
            try:
                res = col.query(query_embeddings=[query_embedding], n_results=n)
                if res and res['documents'][0]:
                    for i, doc in enumerate(res['documents'][0]):
                        retrieved[key].append({
                            "content": doc,
                            "metadata": res['metadatas'][0][i],
                            "similarity": round(1 - res['distances'][0][i], 3)
                        })
            except Exception as e: logger.error(f"❌ Error querying {key}: {e}")

        query_col(self.careers_collection, "careers", n_careers)
        query_col(self.skills_collection, "skills", n_skills)
        query_col(self.faqs_collection, "faqs", n_faqs)
        return retrieved

    def format_retrieved_context(self, retrieved: Dict[str, List[Dict]]) -> str:
        parts = []
        if retrieved["careers"]:
            parts.append("## RELEVANT CAREERS\n" + "\n".join([f"- {c['content']}" for c in retrieved["careers"]]))
        if retrieved["skills"]:
            parts.append("\n## RELEVANT SKILLS\n" + "\n".join([f"- {s['content']}" for s in retrieved["skills"]]))
        return "\n".join(parts) if parts else "No specific internal data."

    def query_advisor(self, user_email: str, query: str, conversation_history: Optional[List[Dict]] = None) -> str:
        try:
            user_context = self.get_user_context(user_email)
            kb_context = self.format_retrieved_context(self.retrieve_context(query))
            full_prompt = f"{self.system_prompt}\n---\n{user_context}\n---\n{kb_context}\n---\nUSER QUESTION:\n{query}"
            return self.model.generate_content(full_prompt).text
        except Exception as e:
            return f"Error: {str(e)}"

    # --------------------------------------------------------------------------
    #  ANALYTICAL METHODS (Dashboard & Detailed Analysis)
    # --------------------------------------------------------------------------

    def get_career_recommendations(self, user_email: str, n_results: int = 3) -> List[Dict]:
        """
        Generates Top-K career matches with specific matching skills text.
        Logic: Match % = (Intersection of User Skills & Req Skills) / Total Req Skills
        """
        logger.info(f"🔄 Generating recommendations for: {user_email}")
        user = self.users_col.find_one({"email": user_email})
        if not user: return []

        # Normalize User Skills
        user_skills_list = [s.lower().strip() for s in user.get('skills', [])]
        user_skills_set = set(user_skills_list)
        
        # Build query
        goal_raw = user.get('career_goal', '')
        goal = ", ".join(goal_raw) if isinstance(goal_raw, list) else str(goal_raw)
        user_query = f"I want to be a {goal}. Skills: {', '.join(user_skills_list)}."
        
        query_embedding = self._get_embedding(user_query)
        if not query_embedding: return []

        try:
            results = self.careers_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results, 
                include=["metadatas", "distances", "documents"]
            )
        except Exception as e:
            logger.error(f"❌ Error querying ChromaDB: {e}")
            return []

        recommendations = []
        if results['metadatas'] and results['distances']:
            for i in range(len(results['metadatas'][0])):
                meta = results['metadatas'][0][i]
                
                # Extract required skills for this career
                req_str = meta.get("required_skills", "")
                req_list = [s.lower().strip() for s in req_str.split(",")] if req_str else []
                req_set = set(req_list)
                
                # Strict Math Calculation
                matching = list(req_set.intersection(user_skills_set))
                total_req = len(req_set) if len(req_set) > 0 else 1 # Avoid div/0
                
                match_percentage = round((len(matching) / total_req) * 100)
                
                # Formatter
                matching_text = ", ".join([m.title() for m in matching[:3]]) if matching else "None yet"
                if len(matching) > 3: matching_text += f" +{len(matching)-3} more"

                recommendations.append({
                    "title": meta.get("title", "Unknown Role"),
                    "match_score": match_percentage, # Strict percentage
                    "industry": meta.get("industry", "General"),
                    "matching_skills_text": matching_text
                })

        # Sort by match score instead of vector distance for this view
        recommendations.sort(key=lambda x: x['match_score'], reverse=True)
        return recommendations

    def get_detailed_gap_analysis(self, user_email: str) -> Dict:
        """
        Generates comprehensive gap analysis for all user career goals.
        """
        user = self.users_col.find_one({"email": user_email})
        if not user: return {"error": "User not found"}

        user_skills_set = set([s.lower().strip() for s in user.get('skills', [])])
        
        # Get goals (ensure list)
        raw_goals = user.get('career_goal', [])
        goals = raw_goals if isinstance(raw_goals, list) else [str(raw_goals)]
        goals = [g for g in goals if g] 

        goals_data = []
        all_missing_skills = []

        for goal in goals:
            # 1. Fetch Career Data from Chroma (Find best match for goal title)
            query_vec = self._get_embedding(goal)
            results = self.careers_collection.query(
                query_embeddings=[query_vec], n_results=1, include=["metadatas"]
            )
            
            career_meta = {}
            if results['metadatas'] and results['metadatas'][0]:
                career_meta = results['metadatas'][0][0]
            
            # 2. Analyze Gap (Strict Math)
            req_str = career_meta.get("required_skills", "")
            req_list = [s.lower().strip() for s in req_str.split(",")] if req_str else []
            req_set = set(req_list)
            
            missing = list(req_set - user_skills_set)
            matching = list(req_set.intersection(user_skills_set))
            
            total = len(req_set) if len(req_set) > 0 else 1
            match_pct = round((len(matching) / total) * 100)

            goals_data.append({
                "goal": goal,
                "match_percent": match_pct,
                "total_skills": len(req_set),
                "skills_had": len(matching)
            })

            # 3. Add to aggregate list (Specific to this goal)
            for skill in missing:
                # Intelligent heuristics for prioritization
                priority = "Medium"
                time_estimate = "4-6 weeks"
                
                s_lower = skill.lower()
                
                # Heuristic 1: Foundational/Critical Skills
                if any(x in s_lower for x in ['python', 'java', 'sql', 'statistics', 'algorithms']):
                    priority = "High"
                    time_estimate = "8-12 weeks"
                # Heuristic 2: Tools/Libraries
                elif any(x in s_lower for x in ['pandas', 'numpy', 'git', 'docker', 'aws']):
                    priority = "Medium"
                    time_estimate = "2-4 weeks"
                # Heuristic 3: Concepts
                elif any(x in s_lower for x in ['machine learning', 'deep learning', 'nlp']):
                    priority = "High"
                    time_estimate = "12+ weeks"
                else:
                    priority = "Low"
                    time_estimate = "2-3 weeks"

                all_missing_skills.append({
                    "name": skill.title(),
                    "priority": priority,
                    "for_goal": goal, # Explicitly link skill to goal
                    "time_estimate": time_estimate
                })

        return {
            "user_name": user.get("name", "User"),
            "career_goals": goals, # List of strings for dropdown
            "goals_summary": goals_data,
            "missing_skills": all_missing_skills,
            "skills_have": user.get('skills', []),
            "currently_learning": user.get('currently_learning', []),
            "skill_ratings": user.get('skill_ratings', {})
        }

    def close(self):
        try:
            if hasattr(self, 'mongo_client'): self.mongo_client.close()
        except: pass