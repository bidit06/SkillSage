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
from bson import ObjectId

load_dotenv()
app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

rag_advisor = None
try:
    from rag_pipeline import CareerAdvisorRAG
    print("🚀 Initializing RAG Advisor...")
    rag_advisor = CareerAdvisorRAG()
    print("✅ RAG Advisor Ready!")
except Exception as e:
    print(f"⚠️ RAG Init Failed: {e}")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client.skillsage_db
users_collection = db.users
chats_collection = db.chats
world_chats_collection = db.world_chats
saved_messages_collection = db.saved_messages

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def get_password_hash(password): return pwd_context.hash(password)
def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token: return None
    user = await users_collection.find_one({"email": token})
    return user

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

class SkillAction(BaseModel):
    skill: str
    action: str
    active: bool

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request): return templates.TemplateResponse("home.html", {"request": request})

@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request): return templates.TemplateResponse("auth.html", {"request": request})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth", status_code=302)
    response.delete_cookie("access_token", path="/")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    if not await get_current_user(request): return RedirectResponse("/auth")
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    if not await get_current_user(request): return RedirectResponse("/auth")
    return templates.TemplateResponse("profile.html", {"request": request})

@app.get("/detailed-skill-analysis", response_class=HTMLResponse)
async def detailed_analysis_page(request: Request):
    if not await get_current_user(request): return RedirectResponse("/auth")
    return templates.TemplateResponse("detailed-skill-analysis.html", {"request": request})

@app.get("/world-chat", response_class=HTMLResponse)
async def world_chat_page(request: Request):
    if not await get_current_user(request): return RedirectResponse("/auth")
    return templates.TemplateResponse("world-chat.html", {"request": request})

@app.get("/saved-chats", response_class=HTMLResponse)
async def saved_chats_page(request: Request):
    if not await get_current_user(request): return RedirectResponse("/auth")
    return templates.TemplateResponse("saved-chats.html", {"request": request})

@app.post("/register")
async def register(user: UserCreate):
    if await users_collection.find_one({"email": user.email}):
        raise HTTPException(400, "Email exists")
    await users_collection.insert_one({
        "name": user.name, "email": user.email, 
        "hashed_password": get_password_hash(user.password),
        "skills": [], "career_goal": [], "qualifications": [], 
        "skill_ratings": {}, "custom_missing_skills": []
    })
    return {"message": "User created"}

@app.post("/token")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = await users_collection.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(400, "Invalid credentials")
    response.set_cookie(key="access_token", value=user["email"], httponly=False, path="/", samesite="lax", secure=False)
    return {"access_token": user["email"], "token_type": "bearer"}

@app.get("/api/dashboard-data")
async def get_dashboard_data(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    
    cursor = chats_collection.find({"user_email": user["email"]}).sort("updated_at", -1).limit(3)
    recent = [{"id": str(c["_id"]), "title": c.get("title", "Chat"), "timestamp": c.get("updated_at")} async for c in cursor]

    recs = []
    if rag_advisor:
        try: recs = rag_advisor.get_career_recommendations(user["email"], 3)
        except: pass
    
    return {
        "name": user.get("name"),
        "skills": user.get("skills", []),
        "currently_learning": user.get("currently_learning", []),
        "recent_activity": recent,
        "recommendations": recs
    }

@app.get("/api/profile")
async def get_profile_data(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    
    def as_list(x): return x if isinstance(x, list) else ([x] if x else [])
    
    return {
        "name": user.get("name"), "email": user.get("email"),
        "location": user.get("location"), "employment_status": user.get("employment_status"),
        "current_activity": user.get("current_activity"), "dreams": user.get("dreams"),
        "career_goal": as_list(user.get("career_goal")),
        "qualifications": as_list(user.get("qualifications")),
        "skills": as_list(user.get("skills")),
        "currently_learning": as_list(user.get("currently_learning"))
    }

@app.put("/api/profile")
async def update_profile(data: UserProfileUpdate, request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    
    if "skills" in update_data:
        current_ratings = user.get("skill_ratings", {})
        new_skills_set = set(update_data["skills"])
        clean_ratings = {k: v for k, v in current_ratings.items() if k in new_skills_set}
        update_data["skill_ratings"] = clean_ratings
    
    await users_collection.update_one({"email": user["email"]}, {"$set": update_data})
    return {"message": "Updated"}

@app.post("/api/skills/action")
async def skill_action(data: SkillAction, request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    
    if data.action == "learned":
        if data.active:
            await users_collection.update_one({"email": user["email"]}, {"$addToSet": {"skills": data.skill}, "$pull": {"currently_learning": data.skill}})
            await users_collection.update_one({"email": user["email"], f"skill_ratings.{data.skill}": {"$exists": False}}, {"$set": {f"skill_ratings.{data.skill}": 1}})
        else:
            await users_collection.update_one({"email": user["email"]}, {"$pull": {"skills": data.skill}, "$unset": {f"skill_ratings.{data.skill}": ""}})
        
    elif data.action == "learning":
        if data.active:
            await users_collection.update_one({"email": user["email"]}, {"$addToSet": {"currently_learning": data.skill}, "$pull": {"skills": data.skill}, "$unset": {f"skill_ratings.{data.skill}": ""}})
        else:
            await users_collection.update_one({"email": user["email"]}, {"$pull": {"currently_learning": data.skill}})
    
    return {"message": "Updated"}

@app.get("/api/detailed-analysis")
async def get_detailed_analysis(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    if not rag_advisor: return {"error": "AI not ready"}
    
    analysis = rag_advisor.get_detailed_gap_analysis(user["email"])
    if user.get("custom_missing_skills"):
        analysis["missing_skills"].extend(user["custom_missing_skills"])
    analysis["currently_learning"] = user.get("currently_learning", [])
    return analysis

@app.post("/api/save-analysis")
async def save_analysis(data: AnalysisSaveRequest, request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    
    await users_collection.update_one({"email": user["email"]}, {"$set": {"skill_ratings": data.skill_ratings, "custom_missing_skills": data.custom_missing_skills}})
    return {"message": "Saved"}

# --- WORLD CHAT API ---
@app.get("/api/world-chat")
async def get_world_chat_messages(request: Request):
    if not await get_current_user(request): raise HTTPException(401)
    cursor = world_chats_collection.find().sort("timestamp", -1).limit(100)
    messages = []
    async for doc in cursor:
        messages.append({"user": doc.get("user", "Anonymous"), "email": doc.get("email"), "text": doc.get("text", ""), "timestamp": doc.get("timestamp")})
    return messages[::-1]

@app.post("/api/world-chat")
async def post_world_chat_message(request: Request, data: dict = Body(...)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    
    msg = {"user": user.get("name", "Unknown"), "email": user["email"], "text": data.get("message"), "timestamp": datetime.utcnow().isoformat()}
    await world_chats_collection.insert_one(msg)
    return {"status": "ok"}

# --- UPDATED TOGGLE SAVED MESSAGE API ---
@app.post("/api/toggle-saved-message")
async def toggle_saved_message(request: Request, data: dict = Body(...)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    
    existing = await saved_messages_collection.find_one({"user_email": user["email"], "text": data.get("text")})
    
    if existing:
        await saved_messages_collection.delete_one({"_id": existing["_id"]})
        return {"status": "removed"}
    else:
        # Save with Chat Title (default to "General" if missing)
        chat_title = data.get("chat_title", "General Chat")
        await saved_messages_collection.insert_one({
            "user_email": user["email"],
            "text": data.get("text"),
            "chat_title": chat_title,
            "saved_at": datetime.utcnow()
        })
        return {"status": "saved"}

@app.get("/api/saved-messages")
async def get_saved_messages(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    
    cursor = saved_messages_collection.find({"user_email": user["email"]}).sort("saved_at", -1)
    messages = []
    async for doc in cursor:
        messages.append({
            "id": str(doc["_id"]),
            "text": doc["text"],
            "chat_title": doc.get("chat_title", "General Chat"),
            "saved_at": doc["saved_at"]
        })
    return messages

@app.delete("/api/saved-messages/{msg_id}")
async def delete_saved_message(msg_id: str, request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    
    result = await saved_messages_collection.delete_one({"_id": ObjectId(msg_id), "user_email": user["email"]})
    if result.deleted_count == 0: raise HTTPException(404, "Message not found")
    return {"status": "deleted"}

# --- CHAT APIS ---
@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    if not await get_current_user(request): return RedirectResponse("/auth")
    return templates.TemplateResponse("index.html", {"request": request})

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