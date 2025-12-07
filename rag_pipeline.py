import os
import json
import chromadb
import google.generativeai as genai
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from typing import Dict, List, Any
import logging
from pathlib import Path
import re

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

class CareerAdvisorRAG:
    def __init__(self):
        logger.info("🚀 Initializing Career Advisor RAG System...")
        self._init_gemini()
        self._init_embedder()
        self._init_mongodb()
        self._init_chromadb()
        self.skill_durations = self._load_skill_durations()
        
    def _init_gemini(self):
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def _init_embedder(self):
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')

    def _init_mongodb(self):
        self.mongo_client = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
        # FIXED: Changed to 'skillsage_db' to match main.py and user request
        self.user_db = self.mongo_client.skillsage_db
        self.users_col = self.user_db.users
        self.careers_col = self.user_db.careers 

    def _init_chromadb(self):
        base_dir = Path(__file__).resolve().parent
        db_path = base_dir / "skillsage_chroma_db"
        self.chroma_client = chromadb.PersistentClient(path=str(db_path))
        self.chroma_careers = self.chroma_client.get_or_create_collection(name="careers")

    def _load_skill_durations(self) -> Dict[str, int]:
        try:
            path = Path(__file__).resolve().parent / "learning_path.json"
            if not path.exists(): return {}
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            duration_map = {}
            for step in data:
                weeks = step.get('duration_weeks', 4)
                for skill in step.get('skills_covered', []):
                    s_key = skill.lower().strip()
                    if weeks > duration_map.get(s_key, 0):
                        duration_map[s_key] = weeks
            return duration_map
        except: return {}

    # --- CORE LOGIC: MongoDB for Charts ---
    def get_detailed_gap_analysis(self, user_email: str) -> Dict:
        user = self.users_col.find_one({"email": user_email})
        if not user: return {"error": "User not found"}

        user_skills_list = user.get('skills', [])
        # Normalize user ratings for easier lookup
        user_ratings = {k.lower().strip(): v for k, v in user.get('skill_ratings', {}).items()}
        
        raw_goals = user.get('career_goal', [])
        goals = [g.strip() for g in (raw_goals if isinstance(raw_goals, list) else [str(raw_goals)]) if g]

        goals_data = []
        all_missing_skills = []

        for goal in goals:
            # 1. Fetch Exact Career from MongoDB
            # Use regex for case-insensitive matching (e.g. "Data Scientist" matches "data scientist")
            career_doc = self.careers_col.find_one({
                "title": {"$regex": f"^{re.escape(goal)}$", "$options": "i"}
            })
            
            # 2. Get Required Skills
            req_skills_map = {}
            if career_doc and "required_skills" in career_doc:
                req_skills_map = career_doc["required_skills"]
            else:
                # Fallback to prevent "Loading..." hang if goal not found
                req_skills_map = {"Technical Skills": 5, "Communication": 5, "Problem Solving": 5}

            # 3. Build Chart Data
            # Take top 12 skills max for UI clarity
            chart_labels = list(req_skills_map.keys())[:12]
            user_data = []
            target_data = []
            
            for skill_name in chart_labels:
                target_level = req_skills_map[skill_name]
                target_data.append(target_level)
                
                # --- MATCHING LOGIC ---
                rating = 0
                
                # Tokenize (e.g., "C++ / C#" -> ["c++", "c#"])
                tokens = [t.strip().lower() for t in re.split(r'[ /&,]+', skill_name)]
                
                # Check 1: Do any tokens match a user skill exactly?
                for token in tokens:
                    if token in user_ratings:
                        rating = max(rating, user_ratings[token])
                
                # Check 2: Direct name match
                if rating == 0:
                    s_lower = skill_name.lower()
                    if s_lower in user_ratings:
                        rating = user_ratings[s_lower]

                user_data.append(rating)

                # 4. Identify Missing Skills
                # Missing if (Not in profile) OR (Rating is 0) OR (Rating < Target - 2)
                is_missing = False
                
                # Check if user essentially "has" the skill (string check)
                has_skill_in_profile = False
                for token in tokens:
                    # Check against the raw list of user skills
                    if any(token == us.lower().strip() for us in user_skills_list):
                        has_skill_in_profile = True
                        break
                
                if not has_skill_in_profile or rating == 0 or rating < (target_level - 2):
                    is_missing = True

                if is_missing:
                    # Avoid duplicates
                    if not any(m['name'] == skill_name and m['for_goal'] == goal for m in all_missing_skills):
                        all_missing_skills.append({
                            "name": skill_name,
                            "priority": "High" if target_level >= 9 else "Medium",
                            "for_goal": goal,
                            "time_estimate": self._estimate_learning_time(skill_name)
                        })

            goals_data.append({
                "goal": goal,
                "required_skills": chart_labels,
                "user_ratings": user_data,
                "target_data": target_data
            })

        return {
            "goals_summary": goals_data,
            "missing_skills": all_missing_skills,
            "skills_have": user_skills_list,
            "skill_ratings": user.get('skill_ratings', {})
        }

    def _estimate_learning_time(self, skill: str) -> str:
        s_lower = skill.lower().strip()
        if s_lower in self.skill_durations: return f"{self.skill_durations[s_lower]} weeks"
        for k, v in self.skill_durations.items():
            if k in s_lower: return f"{v} weeks"
        return "4-6 weeks"

    def query_advisor(self, user_email, query):
        # Retrieve context from Chroma (Chat Only)
        user = self.users_col.find_one({"email": user_email})
        query_vec = self.embedder.encode(query).tolist()
        results = self.chroma_careers.query(query_embeddings=[query_vec], n_results=2)
        context = ""
        if results['documents']: context = "\n".join(results['documents'][0])
        prompt = f"User: {user.get('name')}\nContext: {context}\nQuery: {query}"
        return self.model.generate_content(prompt).text