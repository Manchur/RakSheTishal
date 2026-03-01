import asyncio
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from gemini_automation import GeminiAutomation

app = FastAPI(title="Gemini API Wrapper")
bot = None
session_started = False

class ChatRequest(BaseModel):
    prompt: str
    gem_url: str = "https://gemini.google.com/gem/2e46e3839cf7"
    file_path: str = None

@app.on_event("startup")
async def startup_event():
    global bot
    # Runs the browser off-screen but "headful" to bypass bot detection
    bot = GeminiAutomation(headless=True)
    print("API Started. Waiting for first chat request to initialize context.")

@app.get("/health")
async def health():
    return {"status": "ok", "session_started": session_started}

@app.post("/reset")
async def reset_session():
    # Properly tell Playwright to click the New Chat button
    # rather than destroying our internal state variable
    if bot and getattr(bot, 'page', None):
        await bot.new_chat()
    return {"status": "reset"}

@app.post("/chat")
async def chat(req: ChatRequest):
    global session_started
    
    # Lazy initialization of the browser session on the first chat request
    if not session_started or getattr(bot, 'page', None) is None or bot.page.is_closed():
        print(f"Initializing/Re-initializing browser session for Gem: {req.gem_url}")
        success = await bot.start_session(gem_id=req.gem_url)
        if not success:
            session_started = False
            raise HTTPException(status_code=500, detail="Failed to initialize browser session. Ensure login.")
        session_started = True

    print(f"Sending prompt to Gem: {req.prompt[:50]}...")
    response = await bot.send_message(req.prompt, file_path=req.file_path)
    
    # Auto-recovery if session dropped mid-flight
    if response == "Error: Session not started.":
        print("Session dropped! Attempting auto-recovery...")
        session_started = False
        success = await bot.start_session(gem_id=req.gem_url)
        if success:
            session_started = True
            response = await bot.send_message(req.prompt, file_path=req.file_path)
        else:
            raise HTTPException(status_code=500, detail="Session died and failed to recover.")

    return {"response": response}

@app.post("/shutdown")
async def shutdown():
    global bot
    if bot:
        try:
            await bot.close_session()
            print("Browser session closed cleanly.")
        except Exception as e:
            print(f"Error closing browser: {e}")
            
    # Schedule process termination slightly after returning response
    import os
    import threading
    import time
    def seppuku():
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=seppuku).start()
    
    return {"status": "shutting down"}

if __name__ == "__main__":
    uvicorn.run("gemini_api:app", host="127.0.0.1", port=8001, reload=False)
