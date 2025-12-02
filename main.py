import os
import io
import uuid
from datetime import datetime
from typing import List, Optional, Any
from pathlib import Path
from rag_pipeline import CareerAdvisorRAG
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



# --- CONFIGURATION ---
load_dotenv()
app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Configure Direct Gemini (For Image handling)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
direct_model = genai.GenerativeModel('gemini-2.0-flash')

# --- INITIALIZE RAG ADVISOR ---
print("🚀 Initializing RAG Advisor (This loads the local model)...")
# This loads SentenceTransformer once so it's fast for every request
rag_advisor = CareerAdvisorRAG() 
print("✅ RAG Advisor Ready!")

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
    token = request.cookies.get("access_token")
    if not token:
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

# --- ROUTES: PAGES ---
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/")
    return templates.TemplateResponse("index.html", {"request": request})

# --- ROUTES: AUTH API ---
@app.post("/register")
async def register(user: UserCreate):
    existing_user = await users_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_doc = {
        "name": user.name,
        "email": user.email,
        "hashed_password": get_password_hash(user.password),
        # Default empty profile fields for RAG
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
    
    response.set_cookie(key="access_token", value=user["email"], httponly=True, max_age=3600)
    return {"access_token": user["email"], "token_type": "bearer"}

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

# --- ROUTES: CHAT MESSAGE API (INTEGRATED) ---

@app.post("/chat")
async def chat_endpoint(
    user_message: str = Form(...),
    chat_id: str = Form(None),
    user_upload: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user)
):
    # 1. Handle Chat ID
    if not chat_id or chat_id == "null":
        chat_id = str(uuid.uuid4())
        await chats_collection.insert_one({
            "_id": chat_id,
            "user_email": user["email"],
            "title": user_message[:30] + "...",
            "created_at": datetime.utcnow(),
            "messages": []
        })

    # 2. Save User Message
    user_msg_obj = {
        "sender": "user", 
        "text": user_message, 
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # 3. Determine Logic: RAG vs Direct File
    ai_text = ""
    
    if user_upload:
        # --- PATH A: FILE UPLOAD (Use Direct Gemini) ---
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
            # We use direct model for files as our RAG is text-optimized
            response = direct_model.generate_content(prompt_content)
            ai_text = response.text
        except Exception as e:
            ai_text = f"Error processing file: {str(e)}"
            
    else:
        # --- PATH B: TEXT ONLY (Use RAG Pipeline) ---
        print(f"🧠 Using RAG Pipeline for: {user_message}")
        try:
            # Call the advisor we initialized at the top
            # This searches ChromaDB + User Profile + Gemini
            ai_text = rag_advisor.query_advisor(user["email"], user_message)
        except Exception as e:
            ai_text = f"RAG Error: {str(e)}"

    # 4. Save User Message (Now that we handled file reading)
    await chats_collection.update_one(
        {"_id": chat_id},
        {"$push": {"messages": user_msg_obj}, "$set": {"updated_at": datetime.utcnow()}}
    )

    # 5. Save AI Message
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