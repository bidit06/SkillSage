import os
import io
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from dotenv import load_dotenv

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException, Response, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from PIL import Image
import google.generativeai as genai

# --- CONFIGURATION ---
load_dotenv()
app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
print(TEMPLATE_DIR)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
direct_model = genai.GenerativeModel('gemini-2.0-flash')

# --- RAG INITIALIZATION ---
rag_advisor = None
try:
    from rag_pipeline import CareerAdvisorRAG
    print("🚀 Initializing RAG Advisor...")
    rag_advisor = CareerAdvisorRAG()
    print("✅ RAG Advisor Ready!")
except Exception as e:
    print(f"⚠️ RAG Init Failed: {e}")

# --- DATABASE ---
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.skillsage_db
users_collection = db.users
chats_collection = db.chats

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# --- AUTH HELPER FUNCTIONS ---
def get_password_hash(password): return pwd_context.hash(password)
def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    if not token: return None
    user = await users_collection.find_one({"email": token})
    return user

# --- PYDANTIC MODELS ---
class UserCreate(BaseModel):
    name: str
    email: str
    password: str

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    employment_status: Optional[str] = None
    current_activity: Optional[str] = None
    career_goal: List[str] = []
    qualifications: List[str] = [] 
    skills: List[str] = []
    currently_learning: List[str] = [] 
    dreams: Optional[str] = None

class AnalysisSaveRequest(BaseModel):
    skill_ratings: Dict[str, int]
    custom_missing_skills: List[Dict[str, Any]]

# ==========================================
#               PAGE ROUTES
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse(url="/auth")
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse(url="/auth")
    return templates.TemplateResponse("profile.html", {"request": request})

@app.get("/chat", response_class=HTMLResponse)
async def chat_interface(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse(url="/auth")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/detailed-skill-analysis", response_class=HTMLResponse)
async def detailed_analysis_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse(url="/auth")
    return templates.TemplateResponse("detailed-skill-analysis.html", {"request": request})

# ==========================================
#               API ROUTES
# ==========================================

@app.post("/register")
async def register(user: UserCreate):
    existing_user = await users_collection.find_one({"email": user.email})
    if existing_user: raise HTTPException(status_code=400, detail="Email already registered")
    user_doc = {
        "name": user.name,
        "email": user.email,
        "hashed_password": get_password_hash(user.password),
        "skills": [],
        "currently_learning": [],
        "career_goal": [],
        "qualifications": [], 
        "skill_ratings": {},
        "custom_missing_skills": []
    }
    await users_collection.insert_one(user_doc)
    return {"message": "User created successfully"}

@app.post("/token")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = await users_collection.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    response.set_cookie(key="access_token", value=user["email"], httponly=False, max_age=3600)
    return {"access_token": user["email"], "token_type": "bearer"}

@app.get("/api/dashboard-data")
async def get_dashboard_data(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    
    cursor = chats_collection.find({"user_email": user["email"]}).sort("updated_at", -1).limit(3)
    recent = []
    async for chat in cursor:
        updated = chat.get("updated_at", datetime.utcnow())
        recent.append({
            "type": "chat",
            "id": str(chat["_id"]),
            "title": chat.get("title", "Conversation"),
            "timestamp": updated.isoformat()
        })

    recommendations = []
    if rag_advisor:
        try:
            recommendations = rag_advisor.get_career_recommendations(user["email"], n_results=3)
        except Exception as e:
            print(f"Rec Engine Error: {e}")

    return {
        "name": user.get("name"),
        "skills": user.get("skills", []),
        "currently_learning": user.get("currently_learning", []),
        "recent_activity": recent,
        "recommendations": recommendations 
    }

@app.get("/api/profile")
async def get_profile_data(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    def ensure_list(val): return val if isinstance(val, list) else ([val] if val else [])
    
    return {
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "location": user.get("location", ""),
        "employment_status": user.get("employment_status", ""),
        "current_activity": user.get("current_activity", ""),
        "career_goal": ensure_list(user.get("career_goal")), 
        "qualifications": ensure_list(user.get("qualifications")), 
        "skills": ensure_list(user.get("skills")),
        "currently_learning": ensure_list(user.get("currently_learning")),
        "dreams": user.get("dreams", "")
    }

@app.put("/api/profile")
async def update_profile(data: UserProfileUpdate, request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    await users_collection.update_one({"email": user["email"]}, {"$set": update_data})
    return {"message": "Profile updated"}

@app.get("/api/detailed-analysis")
async def get_detailed_analysis(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    
    if rag_advisor:
        try:
            analysis = rag_advisor.get_detailed_gap_analysis(user["email"])
            # Merge stored custom gaps
            if user.get("custom_missing_skills"):
                analysis["missing_skills"].extend(user.get("custom_missing_skills", []))
            return analysis
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"error": "Advisor not initialized"}

@app.post("/api/save-analysis")
async def save_detailed_analysis(data: AnalysisSaveRequest, request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    
    # We update mainly the custom_missing_skills list
    await users_collection.update_one(
        {"email": user["email"]},
        {
            "$set": {
                "skill_ratings": data.skill_ratings,
                "custom_missing_skills": data.custom_missing_skills
            }
        }
    )
    return {"message": "Analysis saved successfully"}

# ... (Chat APIs as before)
@app.get("/api/chats")
async def get_chats(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    cursor = chats_collection.find({"user_email": user["email"]}).sort("updated_at", -1)
    chats = []
    async for doc in cursor: chats.append({"id": doc["_id"], "title": doc.get("title", "New Chat")})
    return chats

@app.get("/api/chats/{chat_id}")
async def get_chat_history(chat_id: str, request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    chat = await chats_collection.find_one({"_id": chat_id, "user_email": user["email"]})
    if not chat: raise HTTPException(status_code=404, detail="Chat not found")
    return chat

@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str, user: dict = Depends(get_current_user)):
    result = await chats_collection.delete_one({"_id": chat_id, "user_email": user["email"]})
    if result.deleted_count == 0: raise HTTPException(status_code=404, detail="Chat not found")
    return {"message": "Deleted"}

@app.put("/api/chats/{chat_id}")
async def rename_chat(chat_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)):
    result = await chats_collection.update_one({"_id": chat_id, "user_email": user["email"]}, {"$set": {"title": data.get("title")}})
    if result.matched_count == 0: raise HTTPException(status_code=404, detail="Chat not found")
    return {"message": "Renamed"}

@app.post("/chat")
async def chat_endpoint(request: Request, user_message: str = Form(...), chat_id: str = Form(None), user_upload: Optional[UploadFile] = File(None)):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    if not chat_id or chat_id == "null" or chat_id == "":
        chat_id = str(uuid.uuid4())
        await chats_collection.insert_one({"_id": chat_id, "user_email": user["email"], "title": user_message[:50], "created_at": datetime.utcnow(), "messages": []})
    
    user_msg_obj = {"sender": "user", "text": user_message, "timestamp": datetime.utcnow().isoformat()}
    ai_text = ""
    
    if user_upload:
        file_bytes = await user_upload.read()
        user_msg_obj["file_name"] = user_upload.filename
        prompt_content = [user_message]
        if user_upload.content_type.startswith("image/"): prompt_content.append(Image.open(io.BytesIO(file_bytes)))
        else: prompt_content.append(f"\n[File Content]:\n{file_bytes.decode('utf-8')}")
        try: ai_text = direct_model.generate_content(prompt_content).text
        except Exception as e: ai_text = f"Error: {e}"
    else:
        if rag_advisor:
            try: ai_text = rag_advisor.query_advisor(user["email"], user_message)
            except Exception as e: ai_text = f"RAG Error: {e}"
        else: ai_text = "RAG Initializing..."

    await chats_collection.update_one({"_id": chat_id}, {"$push": {"messages": user_msg_obj}, "$set": {"updated_at": datetime.utcnow()}})
    await chats_collection.update_one({"_id": chat_id}, {"$push": {"messages": {"sender": "ai", "text": ai_text, "timestamp": datetime.utcnow().isoformat()}}})
    return {"chat_id": chat_id, "ai_response": ai_text}