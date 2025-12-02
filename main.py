from typing import Union

from fastapi import FastAPI, Request , Form
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path


templates = Jinja2Templates(directory="templates")

name = "Bidit"
from dotenv import load_dotenv

load_dotenv()
    
from google import genai

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

app = FastAPI()

@app.get("/chat" , response_class= HTMLResponse)
async def chatbox(request : Request):
    context = {
        "request" : request,
        "name" : name
    }

    return templates.TemplateResponse("index.html" ,context)

# Python Snippet
@app.post("/chat")
# FastAPI looks for "user_message" because that matches your argument name
async def chat_endpoint(user_message: str = Form(...)): 
    
    # --- PRINT TO TERMINAL ---
    print(f"Received in Python: {user_message}") 
    # -------------------------


    response = client.models.generate_content(
        model="gemini-2.0-flash", contents=user_message
    )
    print(response.text)