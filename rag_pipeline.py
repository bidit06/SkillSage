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
        # We initialize the standard model here to ensure stability at startup.
        # We will attempt to attach tools dynamically during query time.
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def _init_embedder(self):
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')

    def _init_mongodb(self):
        self.mongo_client = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
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
            career_doc = self.careers_col.find_one({
                "title": {"$regex": f"^{re.escape(goal)}$", "$options": "i"}
            })
            
            # 2. Get Required Skills
            req_skills_map = {}
            if career_doc and "required_skills" in career_doc:
                req_skills_map = career_doc["required_skills"]
            else:
                req_skills_map = {"Technical Skills": 5, "Communication": 5, "Problem Solving": 5}

            # 3. Build Chart Data
            chart_labels = list(req_skills_map.keys())[:12]
            user_data = []
            target_data = []
            
            for skill_name in chart_labels:
                target_level = req_skills_map[skill_name]
                target_data.append(target_level)
                
                # --- MATCHING LOGIC ---
                rating = 0
                tokens = [t.strip().lower() for t in re.split(r'[ /&,]+', skill_name)]
                
                # Check 1: Token match
                for token in tokens:
                    if token in user_ratings:
                        rating = max(rating, user_ratings[token])
                
                # Check 2: Direct name match
                if rating == 0:
                    s_lower = skill_name.lower()
                    if s_lower in user_ratings:
                        rating = user_ratings[s_lower]

                user_data.append(rating)

                # 4. Identify Missing Skills (ONLY if not in profile string list)
                is_missing = False
                has_skill_in_profile = False
                for token in tokens:
                    if any(token == us.lower().strip() for us in user_skills_list):
                        has_skill_in_profile = True
                        break
                
                if not has_skill_in_profile:
                    is_missing = True

                if is_missing:
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

    # --- CHATBOT LOGIC ---
    def query_advisor(self, user_email: str, query: str) -> str:
        """
        Generates a premium, concise response. 
        """
        # 1. Fetch User Profile
        user = self.users_col.find_one({"email": user_email})
        if not user:
            return "I couldn't find your profile. Please log in again."

        profile_context = f"""
        User: {user.get('name', 'User')}
        Goals: {', '.join(user.get('career_goal', []))}
        Skills: {', '.join(user.get('skills', []))}
        Learning: {', '.join(user.get('currently_learning', []))}
        """

        # 2. Retrieve Relevant Career Context (RAG)
        query_vec = self.embedder.encode(query).tolist()
        results = self.chroma_careers.query(
            query_embeddings=[query_vec],
            n_results=3
        )
        
        knowledge_base_context = ""
        if results['documents']:
            knowledge_base_context = "\n".join(results['documents'][0])

        # 3. Premium System Prompt
        system_instruction = """You are Orion, an elite Career Architect.
        
        TONE & STYLE:
        - Speak like a sophisticated, warm human expert.
        - Be ultra-concise. No fluff.
        - NO greetings like "Hello [Name]". Start directly with the value.
        - ABSOLUTELY NO MARKDOWN BOLDING (do not use ** or * for emphasis).
        
        LOGIC:
        1. Context Check: Use the 'Knowledge Base Context' first. If it is empty or irrelevant to the query, use your general knowledge to answer.
        2. Personalization: Weave the user's profile (skills/goals) naturally into the answer.
        3. Learning Resources: If the user asks for resources, tutorials, or how to learn a skill, DO NOT give a text explanation. Instead, provide ONLY a list of 3-5 high-quality YouTube video titles and URLs. Format them simply as "Title - URL".
        
        Your goal is to be the most helpful, direct, and polished advisor they have ever used."""

        final_prompt = f"""{system_instruction}

        [USER PROFILE]
        {profile_context}

        [INTERNAL DB CONTEXT]
        {knowledge_base_context}

        [USER QUERY]
        {query}
        """

        # 4. Generate Response with fallback
        try:
            # First try generating with search capability if available
            try:
                response = self.model.generate_content(final_prompt, tools='google_search_retrieval')
            except Exception:
                # If search tool fails/not supported, fallback to standard generation
                response = self.model.generate_content(final_prompt)
            
            return response.text
        except Exception as e:
            logger.error(f"Gemini Generation Error: {e}")
            return "I'm focusing my thoughts. Please ask me that again in a moment."