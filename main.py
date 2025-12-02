import os
import io
import uuid
from datetime import datetime
from typing import List, Optional, Any
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from dotenv import load_dotenv

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException,  status , Response
from fastapi.responses import HTMLResponse, JSONResponse , RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from PIL import Image
import google.generativeai as genai
app = FastAPI()
# Setup Templates
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
load_dotenv() 
# Configure Gemini
# REPLACE WITH YOUR ACTUAL API KEY
genai.configure(api_key=os.getenv("GOOGLE_API_KEY")) 
model = genai.GenerativeModel('gemini-2.0-flash')
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv # <--- Import this

# --- 1. CONFIGURATION ---



# Load variables from .env file


# ... templates and gemini setup ...

# --- 2. DATABASE & SECURITY SETUP ---

# Get the URL from the .env file
MONGO_URI = os.getenv("MONGO_URL")

# Safety Check: Warn if the URL is missing
if not MONGO_URI:
    print("⚠️ WARNING: MONGO_URL not found in .env file. Using localhost.")
    MONGO_URI = "mongodb://localhost:27017"

# Connect to Cloud
client = AsyncIOMotorClient(MONGO_URI)

# Select your database
db = client.skillsage_db
users_collection = db.users
users_collection = db.users
chats_collection = db.chats


# B. Password Hashing Config
# We use bcrypt to hash passwords so they are unreadable in the DB
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    """Checks if the typed password matches the stored hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Converts a plain password into a secure hash"""
    return pwd_context.hash(password)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Decodes the token to get the user's email.
    For this tutorial, the token IS the email. In production, decode JWT here.
    """
    user = await users_collection.find_one({"email": token})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
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
    # 1. Check for the "Entry Pass" cookie
    token = request.cookies.get("access_token")
    
    # 2. If no cookie, BLOCK ACCESS and Redirect to Login
    if not token:
        return RedirectResponse(url="/")
    
    # 3. If cookie exists, show the page
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
        "hashed_password": get_password_hash(user.password)
    }
    await users_collection.insert_one(user_doc)
    return {"message": "User created"}

@app.post("/token")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    # 1. Verify User
    user = await users_collection.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    # 2. Set a Secure Cookie (The "Entry Pass")
    # This allows the Server to see if you are logged in when you visit /chat
    response.set_cookie(
        key="access_token", 
        value=user["email"], 
        httponly=True,  # JavaScript cannot steal this
        max_age=3600    # Expires in 1 hour
    )
    
    # 3. Return the JSON (Keeps your existing API logic working)
    return {"access_token": user["email"], "token_type": "bearer"}

# --- ROUTES: CHAT HISTORY API (NEW) ---

@app.get("/api/chats")
async def get_user_chats(user: dict = Depends(get_current_user)):
    """Fetch all chat titles/IDs for the sidebar"""
    cursor = chats_collection.find({"user_email": user["email"]}).sort("updated_at", -1)
    chats = []
    async for doc in cursor:
        chats.append({
            "id": doc["_id"],
            "title": doc.get("title", "New Chat")
        })
    return chats

@app.get("/api/chats/{chat_id}")
async def get_chat_history(chat_id: str, user: dict = Depends(get_current_user)):
    """Fetch messages for a specific chat"""
    chat = await chats_collection.find_one({"_id": chat_id, "user_email": user["email"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat

# --- ROUTES: CHAT MESSAGE API (UPDATED) ---

@app.post("/chat")
async def chat_endpoint(
    user_message: str = Form(...),
    chat_id: str = Form(None), # <--- New Field: Which chat is this?
    user_upload: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user) # <--- Require Login
):
    # 1. Handle Chat ID (Create new if None)
    if not chat_id or chat_id == "null":
        chat_id = str(uuid.uuid4())
        # Create new document
        await chats_collection.insert_one({
            "_id": chat_id,
            "user_email": user["email"],
            "title": user_message[:30] + "...", # Set title from first msg
            "created_at": datetime.utcnow(),
            "messages": []
        })

    # 2. Prepare User Message Object
    user_msg_obj = {
        "sender": "user",
        "text": user_message,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    prompt_content = [user_message]
    
    # 3. Handle File Upload
    if user_upload:
        file_bytes = await user_upload.read()
        filename = user_upload.filename or "unknown"
        user_msg_obj["file_name"] = filename # Save filename to DB history
        
        content_type = user_upload.content_type or ""
        if content_type.startswith("image/"):
            image = Image.open(io.BytesIO(file_bytes))
            prompt_content.append(image)
        elif content_type.startswith("text/") or filename.endswith((".py", ".txt", ".md", ".js")):
            text_content = file_bytes.decode("utf-8")
            prompt_content.append(f"\n\n[File: {filename}]\n{text_content}")

    # 4. Save User Message to DB
    await chats_collection.update_one(
        {"_id": chat_id},
        {"$push": {"messages": user_msg_obj}, "$set": {"updated_at": datetime.utcnow()}}
    )

    # 5. Get AI Response
    try:
        response = model.generate_content(prompt_content)
        ai_text = response.text
    except Exception as e:
        ai_text = f"Error: {str(e)}"

    # 6. Save AI Message to DB
    ai_msg_obj = {
        "sender": "ai",
        "text": ai_text,
        "timestamp": datetime.utcnow().isoformat()
    }
    await chats_collection.update_one(
        {"_id": chat_id},
        {"$push": {"messages": ai_msg_obj}}
    )

    # 7. Return Response + Chat ID (so frontend can update URL)
    return {
        "chat_id": chat_id, 
        "ai_response": ai_text
    }