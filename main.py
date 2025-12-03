import os
import io
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from dotenv import load_dotenv

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from PIL import Image
import google.generativeai as genai

# --- NEW IMPORT: IMPORT YOUR RAG PIPELINE ---
# Ensure rag_pipeline.py is in the 'backend' folder
try:
    from .rag_pipeline import CareerAdvisorRAG 
except ImportError:
    from rag_pipeline import CareerAdvisorRAG

# --- CONFIGURATION ---
load_dotenv()
app = FastAPI()

# 1. TEMPLATE DIRECTORY SETUP
# This is crucial for your structure
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Configure Direct Gemini (For Image handling)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
direct_model = genai.GenerativeModel('gemini-2.0-flash')
2
# --- INITIALIZE RAG ADVISOR ---
print("🚀 Initializing RAG Advisor...")
try:
    rag_advisor = CareerAdvisorRAG() 
    print("✅ RAG Advisor Ready!")
except Exception as e:
    print(f"⚠️ RAG Init Failed (Check paths): {e}")
    rag_advisor = None

# --- DATABASE ---
MONGO_URI = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URI)
db = client.skillsage_db
users_collection = db.users
chats_collection = db.chats

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- AUTH HELPERS ---
def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

async def get_current_user(request: Request):
    """
    Checks for the 'access_token' cookie.
    If missing, returns None (caller must handle redirect).
    """
    token = request.cookies.get("access_token")
    if not token:
        # Check Authorization header as fallback (for API calls)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = await users_collection.find_one({"email": token})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

# --- MODELS ---
class UserCreate(BaseModel):
    name: str
    email: str
    password: str

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    employment_status: Optional[str] = None
    current_activity: Optional[str] = None
    career_goal: Optional[str] = None
    skills: List[str] = []
    currently_learning: Optional[str] = None
    dreams: Optional[str] = None

# ==========================================
#               PAGE ROUTES
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Landing Page (Public)"""
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request):
    """Login/Signup Page (Public)"""
    return templates.TemplateResponse("auth.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Dashboard (Protected)"""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/auth")
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    """Profile Page (Protected)"""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/auth")
    return templates.TemplateResponse("profile.html", {"request": request})

@app.get("/chat", response_class=HTMLResponse)
async def chat_interface(request: Request):
    """Chat Interface (Protected)"""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/auth")
    return templates.TemplateResponse("index.html", {"request": request})

# ==========================================
#               API ROUTES
# ==========================================

@app.post("/register")
async def register(user: UserCreate):
    existing_user = await users_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_doc = {
        "name": user.name,
        "email": user.email,
        "hashed_password": get_password_hash(user.password),
        "skills": [],
        "experience": "Not specified",
        "career_goal": "Not specified"
    }
    await users_collection.insert_one(user_doc)
    return {"message": "User created"}

@app.post("/token")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = await users_collection.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    # Set Cookie for Browser Access
    response.set_cookie(key="access_token", value=user["email"], httponly=False, max_age=3600)
    
    return {"access_token": user["email"], "token_type": "bearer"}

@app.get("/api/dashboard-data")
async def get_dashboard_data(user: dict = Depends(get_current_user)):
    user_name = user.get("name", "User")
    user_skills = user.get("skills", []) 
    
    cursor = chats_collection.find({"user_email": user["email"]}).sort("updated_at", -1).limit(3)
    recent_activity = []
    async for chat in cursor:
        updated_at = chat.get("updated_at", datetime.utcnow())
        recent_activity.append({
            "type": "chat",
            "title": chat.get("title", "New Conversation"),
            "timestamp": updated_at.isoformat()
        })

    return {
        "name": user_name,
        "skills": user_skills,
        "recent_activity": recent_activity
    }

@app.get("/api/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    profile_data = {
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "location": user.get("location", ""),
        "employment_status": user.get("employment_status", ""),
        "current_activity": user.get("current_activity", ""),
        "career_goal": user.get("career_goal", ""),
        "skills": user.get("skills", []),
        "currently_learning": user.get("currently_learning", ""),
        "dreams": user.get("dreams", "")
    }
    return profile_data

@app.put("/api/profile")
async def update_profile(data: UserProfileUpdate, user: dict = Depends(get_current_user)):
    update_dict = {
        "name": data.name,
        "location": data.location,
        "employment_status": data.employment_status,
        "current_activity": data.current_activity,
        "career_goal": data.career_goal,
        "skills": data.skills,
        "currently_learning": data.currently_learning,
        "dreams": data.dreams
    }
    update_dict = {k: v for k, v in update_dict.items() if v is not None}
    await users_collection.update_one(
        {"email": user["email"]},
        {"$set": update_dict}
    )
    return {"message": "Profile updated successfully"}

@app.get("/api/chats")
async def get_user_chats(user: dict = Depends(get_current_user)):
    cursor = chats_collection.find({"user_email": user["email"]}).sort("updated_at", -1)
    chats = []
    async for doc in cursor:
        chats.append({"id": doc["_id"], "title": doc.get("title", "New Chat")})
    return chats

@app.get("/api/chats/{chat_id}")
async def get_chat_history(chat_id: str, user: dict = Depends(get_current_user)):
    chat = await chats_collection.find_one({"_id": chat_id, "user_email": user["email"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat

@app.post("/chat")
async def chat_endpoint(
    user_message: str = Form(...),
    chat_id: str = Form(None),
    user_upload: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user)
):
    if not chat_id or chat_id == "null" or chat_id == "":
        chat_id = str(uuid.uuid4())
        await chats_collection.insert_one({
            "_id": chat_id,
            "user_email": user["email"],
            "title": user_message[:30] + "...",
            "created_at": datetime.utcnow(),
            "messages": []
        })

    user_msg_obj = {
        "sender": "user", 
        "text": user_message, 
        "timestamp": datetime.utcnow().isoformat()
    }
    
    ai_text = ""
    
    if user_upload:
        print(f"📂 Processing File Upload: {user_upload.filename}")
        file_bytes = await user_upload.read()
        filename = user_upload.filename
        user_msg_obj["file_name"] = filename
        
        prompt_content = [user_message]
        
        if user_upload.content_type.startswith("image/"):
            image = Image.open(io.BytesIO(file_bytes))
            prompt_content.append(image)
        else:
            text_content = file_bytes.decode("utf-8")
            prompt_content.append(f"\n[File Content]:\n{text_content}")
            
        try:
            response = direct_model.generate_content(prompt_content)
            ai_text = response.text
        except Exception as e:
            ai_text = f"Error processing file: {str(e)}"
            
    else:
        print(f"🧠 Using RAG Pipeline for: {user_message}")
        if rag_advisor:
            try:
                ai_text = rag_advisor.query_advisor(user["email"], user_message)
            except Exception as e:
                ai_text = f"RAG Error: {str(e)}"
        else:
            ai_text = "RAG System not initialized. Check server logs."

    await chats_collection.update_one(
        {"_id": chat_id},
        {"$push": {"messages": user_msg_obj}, "$set": {"updated_at": datetime.utcnow()}}
    )

    ai_msg_obj = {
        "sender": "ai", 
        "text": ai_text, 
        "timestamp": datetime.utcnow().isoformat()
    }
    await chats_collection.update_one(
        {"_id": chat_id},
        {"$push": {"messages": ai_msg_obj}}
    )

    return {"chat_id": chat_id, "ai_response": ai_text}