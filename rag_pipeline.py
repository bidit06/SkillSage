import os
import json
import chromadb
import google.generativeai as genai
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple
import logging

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
    
    Combines:
    - User profile from MongoDB
    - Knowledge retrieval from ChromaDB
    - AI generation with Google Gemini
    """
    
    def __init__(self, prompt_mode: str = "balanced"):
        """
        Initialize the RAG system
        
        Args:
            prompt_mode: "concise" | "balanced" | "detailed"
        """
        self.prompt_mode = prompt_mode
        logger.info("🚀 Initializing Career Advisor RAG System...")
        
        # 1. Initialize Google Gemini
        self._init_gemini()
        
        # 2. Initialize Embedding Model
        self._init_embedder()
        
        # 3. Initialize MongoDB
        self._init_mongodb()
        
        # 4. Initialize ChromaDB
        self._init_chromadb()
        
        # 5. Load system prompt
        self.system_prompt = self._load_system_prompt()
        
        logger.info("✅ RAG System initialized successfully!\n")

    def _init_gemini(self):
        """Initialize Google Gemini API"""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("❌ GOOGLE_API_KEY is missing in .env file")
        
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            logger.info("✅ Gemini API configured")
        except Exception as e:
            logger.error(f"❌ Failed to configure Gemini: {e}")
            raise

    def _init_embedder(self):
        """Initialize local embedding model"""
        try:
            logger.info("⏳ Loading embedding model (all-MiniLM-L6-v2)...")
            self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("✅ Embedding model loaded")
        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            raise

    def _init_mongodb(self):
        """Initialize MongoDB connection"""
        mongo_uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
        
        try:
            self.mongo_client = MongoClient(mongo_uri)
            self.user_db = self.mongo_client.skillsage_db
            self.users_col = self.user_db.users
            
            # Test connection
            self.mongo_client.server_info()
            logger.info("✅ Connected to MongoDB")
        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise

    def _init_chromadb(self):
        """Initialize ChromaDB collections"""
        try:
            logger.info("📂 Connecting to ChromaDB...")
            self.chroma_client = chromadb.PersistentClient(path="./skillsage_chroma_db")
            
            # Get the three collections
            self.careers_collection = self.chroma_client.get_or_create_collection(
                name="careers",
                metadata={"hnsw:space": "cosine"}
            )
            
            self.skills_collection = self.chroma_client.get_or_create_collection(
                name="skills",
                metadata={"hnsw:space": "cosine"}
            )
            
            self.faqs_collection = self.chroma_client.get_or_create_collection(
                name="faqs",
                metadata={"hnsw:space": "cosine"}
            )
            
            # Log collection sizes
            careers_count = self.careers_collection.count()
            skills_count = self.skills_collection.count()
            faqs_count = self.faqs_collection.count()
            
            logger.info(f"✅ Connected to ChromaDB")
            logger.info(f"   • Careers: {careers_count} items")
            logger.info(f"   • Skills:  {skills_count} items")
            logger.info(f"   • FAQs:    {faqs_count} items")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to ChromaDB: {e}")
            raise

    def _load_system_prompt(self) -> str:
        """
        Load system prompt based on mode
        
        Returns:
            System prompt string
        """
        if self.prompt_mode == "concise":
            return self._concise_prompt()
        elif self.prompt_mode == "detailed":
            return self._detailed_prompt()
        else:  # balanced (default)
            return self._balanced_prompt()

    def _concise_prompt(self) -> str:
        """Minimal prompt for fast responses"""
        return """You are Orion, an AI Career Advisor.

Provide personalized career guidance using:
- User's profile (skills, goals, background)
- Knowledge base facts (careers, skills, FAQs)
- User's query

Be specific, actionable, and encouraging. Use bullet points for clarity."""

    def _balanced_prompt(self) -> str:
        """Balanced prompt (recommended)"""
        return """You are Orion, an AI Career Advisor providing personalized career guidance.

## YOUR ROLE
- Expert career counselor across multiple industries
- Provide personalized, actionable advice based on user's background
- Encouraging yet realistic about challenges
- Professional but friendly tone

## RESPONSE GUIDELINES

**Structure Your Answers:**
1. Direct answer to the question
2. Why it's relevant to user's profile (reference their skills/goals)
3. Specific requirements or skills needed
4. Realistic expectations (timeline, salary, challenges)
5. 2-3 actionable next steps

**Use the Context:**
- **User Profile**: Reference their specific skills, experience, and career goals
- **Knowledge Base**: Cite facts from retrieved careers, skills, and FAQs
- **Don't** make up information - stick to provided knowledge
- **Acknowledge** when you don't have specific information

**Best Practices:**
✅ Personalize using user's profile
✅ Provide specific numbers (salary ranges, timelines, percentages)
✅ Highlight existing strengths they can leverage
✅ Offer concrete action items
✅ Use bullet points and bold for key information

❌ Don't make guarantees about outcomes
❌ Don't ignore user's context
❌ Don't use jargon without explanation
❌ Don't be vague or generic

**Formatting:**
- Use **bold** for important points
- Use bullet lists for multiple items
- Use numbered lists for sequential steps
- Keep paragraphs short (2-3 sentences max)

Your mission: Help users gain clarity, confidence, and concrete plans for their career goals."""

    def _detailed_prompt(self) -> str:
        """Full detailed prompt"""
        return """You are Orion, an intelligent AI Career Advisor designed to help users discover their ideal career paths and develop their professional skills. You are knowledgeable, empathetic, encouraging, and data-driven.

## YOUR ROLE
- Professional career counselor with expertise in multiple industries, skill development, and career transitions
- Provide personalized, actionable advice based on the user's background, skills, and aspirations
- Encouraging and supportive while being realistic about career paths and requirements
- Speak in a friendly, conversational tone without being overly casual

## COMMUNICATION STYLE
- Clear and concise: Get to the point while being thorough
- Structured: Use bullet points, numbered lists, and headers for clarity
- Encouraging: Highlight user's strengths and growth potential
- Realistic: Be honest about challenges and required effort
- Actionable: Always provide next steps and concrete recommendations

## HOW TO USE PROVIDED CONTEXT

### USER PROFILE CONTEXT
This contains the user's background. Use it to:
- Personalize ALL responses based on their skills and experience
- Reference their specific background when making recommendations
- Tailor advice to their experience level
- Consider their stated goals and interests
- Acknowledge their existing strengths

### KNOWLEDGE BASE CONTEXT
Retrieved from vector database. Use it to:
- Provide factual information about careers and skills
- Cite specific requirements, salary ranges, and market demand
- Don't make up information - rely on provided knowledge
- If context doesn't contain relevant info, acknowledge limitations
- Combine multiple pieces of context for comprehensive answers

### USER QUERY
The specific question. Respond by:
- Answering the exact question asked
- Providing relevant additional context when helpful
- Asking clarifying questions if the query is vague

## RESPONSE STRUCTURE

**For Career Exploration Queries:**
1. Brief overview of the career/field
2. Required skills and qualifications
3. Why it might be a good fit (based on user profile)
4. Realistic expectations (challenges, timeline, salary)
5. Concrete next steps

**For Skill Development Queries:**
1. Explanation of the skill and its importance
2. Where/how it's used in careers
3. Learning path tailored to user's current level
4. Recommended resources
5. Timeline and milestones

**For Career Transition Queries:**
1. Acknowledge their current position
2. Gap analysis (what they have vs what they need)
3. Transferable skills they can leverage
4. Step-by-step transition plan
5. Realistic timeline and expectations

## BEST PRACTICES

✅ DO:
- Start with the most important information
- Use the user's name occasionally if provided
- Highlight their existing strengths
- Provide specific numbers (salary, timelines, percentages)
- Offer 2-3 concrete action items
- Link related careers or skills
- Be encouraging about their potential
- Acknowledge uncertainties honestly

❌ DON'T:
- Make promises or guarantees about career outcomes
- Recommend careers without explaining why
- Ignore the user's profile context
- Use overly technical jargon without explanation
- Be vague or generic
- Overwhelm with too much information
- Make up statistics or facts not in knowledge base

## FORMATTING
- Use **bold** for key points and emphasis
- Use bullet points (-) for lists
- Use numbered lists (1, 2, 3) for sequential steps
- Keep paragraphs short (2-3 sentences maximum)
- Highlight salary ranges, timelines, and statistics in bold

Remember: Your mission is to help users gain clarity about their career path, confidence in their abilities, and a concrete plan to achieve their professional goals."""

    def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        try:
            embedding = self.embedder.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"❌ Error generating embedding: {e}")
            return []

    def get_user_context(self, user_email: str) -> str:
        """
        Fetch user profile from MongoDB
        
        Args:
            user_email: User's email address
            
        Returns:
            Formatted user context string
        """
        logger.info(f"🔍 Fetching profile for: {user_email}")
        
        try:
            user = self.users_col.find_one({"email": user_email})
            
            if not user:
                logger.warning("⚠️ User not found in database")
                return "**User Profile:** Guest user (no profile data available)"
            
            # Build comprehensive profile context
            context = f"""## USER PROFILE

**Name:** {user.get('name', 'User')}
**Current Role/Activity:** {user.get('current_activity', 'Not specified')}
**Career Goal:** {user.get('career_goal', 'Exploring career options')}
**Current Skills:** {', '.join(user.get('skills', ['None listed']))}
**Experience Level:** {user.get('employment_status', 'Not specified')}
**Education:** {user.get('education', 'Not specified')}
**Location:** {user.get('location', 'Not specified')}
**Interests:** {', '.join(user.get('interests', ['Not specified']))}
"""
            
            logger.info("✅ User context loaded")
            return context
            
        except Exception as e:
            logger.error(f"❌ Error fetching user context: {e}")
            return "**User Profile:** Unable to load profile data"

    def retrieve_context(
        self, 
        query: str, 
        n_careers: int = 3,
        n_skills: int = 5,
        n_faqs: int = 2,
        similarity_threshold: float = 0.7
    ) -> Dict[str, List[Dict]]:
        """
        Retrieve relevant context from ChromaDB collections
        
        Args:
            query: User's query
            n_careers: Number of careers to retrieve
            n_skills: Number of skills to retrieve
            n_faqs: Number of FAQs to retrieve
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            Dictionary with retrieved contexts
        """
        query_embedding = self._get_embedding(query)
        
        if not query_embedding:
            logger.error("❌ Failed to generate query embedding")
            return {"careers": [], "skills": [], "faqs": []}
        
        retrieved = {
            "careers": [],
            "skills": [],
            "faqs": []
        }
        
        # Query Careers Collection
        try:
            careers_results = self.careers_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_careers
            )
            
            if careers_results and careers_results['documents'][0]:
                for i, doc in enumerate(careers_results['documents'][0]):
                    distance = careers_results['distances'][0][i] if careers_results.get('distances') else 1.0
                    metadata = careers_results['metadatas'][0][i] if careers_results.get('metadatas') else {}
                    
                    # Filter by similarity threshold
                    if distance < similarity_threshold:
                        retrieved["careers"].append({
                            "content": doc,
                            "metadata": metadata,
                            "similarity": round(1 - distance, 3)
                        })
            
            logger.info(f"   ✅ Retrieved {len(retrieved['careers'])} careers")
        except Exception as e:
            logger.error(f"   ❌ Error querying careers: {e}")
        
        # Query Skills Collection
        try:
            skills_results = self.skills_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_skills
            )
            
            if skills_results and skills_results['documents'][0]:
                for i, doc in enumerate(skills_results['documents'][0]):
                    distance = skills_results['distances'][0][i] if skills_results.get('distances') else 1.0
                    metadata = skills_results['metadatas'][0][i] if skills_results.get('metadatas') else {}
                    
                    if distance < similarity_threshold:
                        retrieved["skills"].append({
                            "content": doc,
                            "metadata": metadata,
                            "similarity": round(1 - distance, 3)
                        })
            
            logger.info(f"   ✅ Retrieved {len(retrieved['skills'])} skills")
        except Exception as e:
            logger.error(f"   ❌ Error querying skills: {e}")
        
        # Query FAQs Collection
        try:
            faqs_results = self.faqs_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_faqs
            )
            
            if faqs_results and faqs_results['documents'][0]:
                for i, doc in enumerate(faqs_results['documents'][0]):
                    distance = faqs_results['distances'][0][i] if faqs_results.get('distances') else 1.0
                    metadata = faqs_results['metadatas'][0][i] if faqs_results.get('metadatas') else {}
                    
                    if distance < similarity_threshold:
                        retrieved["faqs"].append({
                            "content": doc,
                            "metadata": metadata,
                            "similarity": round(1 - distance, 3)
                        })
            
            logger.info(f"   ✅ Retrieved {len(retrieved['faqs'])} FAQs")
        except Exception as e:
            logger.error(f"   ❌ Error querying FAQs: {e}")
        
        return retrieved

    def format_retrieved_context(self, retrieved: Dict[str, List[Dict]]) -> str:
        """
        Format retrieved context into readable string
        
        Args:
            retrieved: Dictionary with retrieved data
            
        Returns:
            Formatted context string
        """
        context_parts = []
        
        # Format Careers
        if retrieved["careers"]:
            context_parts.append("## RELEVANT CAREERS FROM KNOWLEDGE BASE\n")
            for i, career in enumerate(retrieved["careers"], 1):
                similarity = career.get("similarity", 0)
                context_parts.append(f"### Career Option {i} (Relevance: {similarity:.1%})\n")
                context_parts.append(career["content"])
                context_parts.append("")
        
        # Format Skills
        if retrieved["skills"]:
            context_parts.append("\n## RELEVANT SKILLS FROM KNOWLEDGE BASE\n")
            for i, skill in enumerate(retrieved["skills"], 1):
                similarity = skill.get("similarity", 0)
                context_parts.append(f"### Skill {i} (Relevance: {similarity:.1%})\n")
                context_parts.append(skill["content"])
                context_parts.append("")
        
        # Format FAQs
        if retrieved["faqs"]:
            context_parts.append("\n## RELEVANT Q&As FROM KNOWLEDGE BASE\n")
            for i, faq in enumerate(retrieved["faqs"], 1):
                similarity = faq.get("similarity", 0)
                context_parts.append(f"### Related Question {i} (Relevance: {similarity:.1%})\n")
                context_parts.append(faq["content"])
                context_parts.append("")
        
        if not context_parts:
            return "No specific internal data found on this topic in our knowledge base."
        
        return "\n".join(context_parts)

    def query_advisor(
        self, 
        user_email: str, 
        query: str, 
        conversation_history: Optional[List[Dict]] = None
    ) -> str:
        """
        Main method to query the AI Career Advisor
        
        Args:
            user_email: User's email for personalization
            query: User's question
            conversation_history: Optional list of previous messages
                Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
            
        Returns:
            AI-generated response
        """
        logger.info(f"\n💬 Processing query: '{query[:60]}...'")
        
        try:
            # 1. Get User Context
            user_context = self.get_user_context(user_email)
            
            # 2. Retrieve Relevant Knowledge
            logger.info("🔍 Searching knowledge base...")
            retrieved = self.retrieve_context(query)
            kb_context = self.format_retrieved_context(retrieved)
            
            # 3. Format Conversation History
            history_text = ""
            if conversation_history and len(conversation_history) > 0:
                history_text = "\n## CONVERSATION HISTORY (Recent Messages)\n\n"
                # Include last 5 messages for context
                for msg in conversation_history[-5:]:
                    role = msg.get("role", "user").upper()
                    content = msg.get("content", "")
                    history_text += f"**{role}:** {content}\n\n"
            
            # 4. Build Complete Prompt
            full_prompt = f"""{self.system_prompt}

---

{user_context}

---

{kb_context}

---

{history_text}

---

## USER'S CURRENT QUESTION
{query}

---

As Orion, provide a helpful, personalized response following all guidelines above:
"""
            
            # 5. Generate Response with Gemini
            logger.info("🤖 Generating response with Gemini AI...")
            
            response = self.model.generate_content(full_prompt)
            
            logger.info("✅ Response generated successfully\n")
            return response.text
            
        except Exception as e:
            logger.error(f"❌ Error generating response: {e}")
            return (
                "I apologize, but I encountered an error processing your question. "
                "Please try rephrasing your question or contact support if the issue persists. "
                f"Error details: {str(e)}"
            )

    def close(self):
        """Clean up resources"""
        try:
            if hasattr(self, 'mongo_client'):
                self.mongo_client.close()
                logger.info("✅ MongoDB connection closed")
        except Exception as e:
            logger.error(f"❌ Error closing connections: {e}")


# --- UTILITY FUNCTIONS ---

def create_advisor(prompt_mode: str = "balanced") -> CareerAdvisorRAG:
    """
    Factory function to create advisor instance
    
    Args:
        prompt_mode: "concise" | "balanced" | "detailed"
        
    Returns:
        CareerAdvisorRAG instance
    """
    return CareerAdvisorRAG(prompt_mode=prompt_mode)


# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 TESTING RAG PIPELINE")
    print("="*70 + "\n")
    
    # Initialize advisor
    advisor = create_advisor(prompt_mode="balanced")
    
    # Example queries
    test_queries = [
        "I want to become a data scientist. What skills do I need?",
        "How do I transition from software development to machine learning?",
        "What is Python used for in data science?"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{'─'*70}")
        print(f"QUERY {i}: {query}")
        print('─'*70)
        
        response = advisor.query_advisor(
            user_email="test@example.com",
            query=query
        )
        
        print("\n" + "🤖 ORION'S RESPONSE ".center(70, '─'))
        print(response)
        print()
    
    # Close connections
    advisor.close()
    
    print("\n" + "="*70)
    print("✅ Testing complete!")
    print("="*70 + "\n")



