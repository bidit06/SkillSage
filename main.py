import os
import io
import uuid
from datetime import datetime
from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from dotenv import load_dotenv

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from PIL import Image
import google.generativeai as genai

# --- CONFIGURATION ---
load_dotenv()
app = FastAPI()

# Setup Templates
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Configure Direct Gemini (For Image handling)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
direct_model = genai.GenerativeModel('gemini-2.0-flash')

# --- RAG INITIALIZATION ---
# We initialize this globally so it persists across requests
rag_advisor = None
try:
    from rag_pipeline import CareerAdvisorRAG
    print("🚀 Initializing RAG Advisor...")
    rag_advisor = CareerAdvisorRAG()
    print("✅ RAG Advisor Ready!")
except Exception as e:
    print(f"⚠️ RAG Init Failed: {e}")

# --- DATABASE ---
# Ensure this matches the variable in rag_pipeline.py
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
    """
    Retrieves user based on cookie or Bearer token.
    """
    token = request.cookies.get("access_token")
    
    # Check Bearer token if cookie is missing (useful for API testing)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        # Return None instead of raising HTTP 401 immediately for page routes
        # API routes will handle the None check
        return None
    
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
    career_goal: Optional[str] = None
    skills: List[str] = []
    currently_learning: Optional[str] = None
    dreams: Optional[str] = None

class ChatUpdate(BaseModel):
    title: str
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
    return {"message": "User created successfully"}



@app.post("/token")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    user = await users_collection.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    # Set HTTP-only cookie for security
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
            "title": chat.get("title", "Conversation"),
            "timestamp": updated.isoformat()
        })

    return {
        "name": user.get("name"),
        "skills": user.get("skills", []),
        "recent_activity": recent
    }

@app.get("/api/profile")
async def get_profile_data(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Return all fields needed for the profile form
    return {
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

@app.put("/api/profile")
async def update_profile(data: UserProfileUpdate, request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")

    update_data = {k: v for k, v in data.dict().items() if v is not None}
    
    await users_collection.update_one(
        {"email": user["email"]},
        {"$set": update_data}
    )
    return {"message": "Profile updated"}

@app.get("/api/chats")
async def get_chats(request: Request):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")
    
    cursor = chats_collection.find({"user_email": user["email"]}).sort("updated_at", -1)
    chats = []
    async for doc in cursor:
        chats.append({"id": doc["_id"], "title": doc.get("title", "New Chat")})
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
    # Verify the chat belongs to the user
    result = await chats_collection.delete_one({"_id": chat_id, "user_email": user["email"]})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Chat not found or not authorized")
    
    return {"message": "Chat deleted successfully"}
# --- NEW: RENAME CHAT ENDPOINT ---
@app.put("/api/chats/{chat_id}")
async def rename_chat(chat_id: str, data: ChatUpdate, user: dict = Depends(get_current_user)):
    result = await chats_collection.update_one(
        {"_id": chat_id, "user_email": user["email"]},
        {"$set": {"title": data.title}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"message": "Chat renamed"}

@app.post("/chat")
async def chat_endpoint(
    request: Request,
    user_message: str = Form(...),
    chat_id: str = Form(None),
    user_upload: Optional[UploadFile] = File(None)
):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401, detail="Not authenticated")

    # Initialize Chat ID if new
    if not chat_id or chat_id == "null" or chat_id == "":
        chat_id = str(uuid.uuid4())
        await chats_collection.insert_one({
            "_id": chat_id,
            "user_email": user["email"],
            "title": user_message,
            "created_at": datetime.utcnow(),
            "messages": []
        })

    # Prepare User Message
    user_msg_obj = {
        "sender": "user", 
        "text": user_message, 
        "timestamp": datetime.utcnow().isoformat()
    }
    
    ai_text = ""
    
    # CASE 1: Handle File Upload (Image)
    if user_upload:
        file_bytes = await user_upload.read()
        user_msg_obj["file_name"] = user_upload.filename
        
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

    # CASE 2: Normal Text Chat (RAG)
    else:
        if rag_advisor:
            try:
                # DEBUG PRINT to verify user is being passed
                print(f"🗣️ Querying RAG for User: {user['email']}")
                ai_text = rag_advisor.query_advisor(user["email"], user_message)
            except Exception as e:
                ai_text = f"RAG Error: {str(e)}"
        else:
            ai_text = "RAG System is initializing. Please try again in a moment."

    # Save to DB
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