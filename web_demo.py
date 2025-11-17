from fastapi import WebSocket, WebSocketDisconnect
from audio_manager import AudioManager
import os
import uvicorn
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import json
import base64
from datetime import datetime, time, timedelta

# Import your existing code
from openai_socket import connect_to_openai, request_response, single_interaction
from state import State

from dotenv import load_dotenv


load_dotenv()

# Globals for your WebSocket connection and conversation task
websocket = None

async def lifespan(app: FastAPI):
    """
    Lifespan event: connect to OpenAI on startup, then close on shutdown.
    """
    global websocket
    try:
        websocket = await connect_to_openai()
        print("Connected to OpenAI successfully")
    except Exception as e:
        print(f"Failed to connect to OpenAI: {e}")
        websocket = None
    yield
    if websocket:
        # await websocket.close()
        try:
            websocket.close()
            await websocket.wait_closed()
        except Exception as e:
            print(f"Failed to close socket: {e}")
            websocket = None

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="templates"), name="static")

async def ensure_connection():
    global websocket

    reconnect_case = False
    # Kiểm tra nếu websocket chưa khởi tạo hoặc đã đóng
    if websocket is None:
        print("WebSocket is None. Reconnecting...")
        reconnect_case = True
    else:
        try:
            print("Send ping to check connection...")
            pong = await websocket.ping()
            await pong  # Đợi phản hồi pong
        except Exception as e:
            print(f"WebSocket ping failed: {e}. Reconnecting...")
            reconnect_case = True
        
    if reconnect_case:
        try:
            websocket = await connect_to_openai()
            print("Reconnected socket")
        except Exception as e:
            print(f"Failed to reconnect socket: {e}")
            return False
    else:
        print("Socket work well")
    return True

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """
    Serve the front-end HTML.
    """
    with open("templates/index.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

@app.post("/record_and_ask")
async def record_and_ask():
    """
    Once the wakeword has been detected, record the user's voice using record_voice_input,
    then send the recorded audio to the LLM.
    """
    from recording import record_voice_input  # your existing recording function
    import base64

    if not await ensure_connection():
        return JSONResponse({"answer": "I'm having trouble connecting to the assistant service. Please try again."})

    recorded_audio = await record_voice_input()
    if recorded_audio is None:
        return JSONResponse({"skip": True})
    encoded_audio = base64.b64encode(recorded_audio).decode('utf-8')

    state = State()
    state.pcm_data = b""

    try:
        await websocket.send(json.dumps({
             'type': 'conversation.item.create',
             'item': {
                 'type': 'message',
                 'role': 'user',
                 'content': [
                     {'type': 'input_audio', 'audio': encoded_audio}
                 ]
             }
        }))
        await request_response(websocket)
        await single_interaction(websocket)
    except Exception as e:
        print(f"Connection error: {e}")
        # websocket = None
        return JSONResponse({"answer": "Connection lost. Please try again."})
        
    current_text = state.text.strip()
    state.text += "\n 1-------------------------------------------------- \n"
    return JSONResponse({"answer": current_text})


@app.websocket("/ws/wakeword")
async def wakeword_ws(ws: WebSocket):
    await ws.accept()
    audio = AudioManager()
    try:
        while True:
            await audio.wake_event.wait()
            await ws.send_json({"wakeword": True})
            audio.wake_event.clear()
    except WebSocketDisconnect:
        return

@app.post("/ask")
async def ask_question(request: Request):
    """
    Handle text queries.
    """
    global websocket
    if not await ensure_connection():
        return JSONResponse({"answer": "I'm having trouble connecting to the assistant service. Please try again."})
    
    data = await request.json()
    user_text = data.get("text", "")
    if not user_text:
        return JSONResponse({"answer": "No text received."})

    state = State()
    state.pcm_data = b""
    state.reset()
    print('Start ask_question')
    try:
        print(f"Received user text: {user_text}")
        await websocket.send(json.dumps({
            'type': 'conversation.item.create',
            'item': {
                'type': 'message',
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': user_text}
                ]
            }
        }))
        print(f"Sent user text to WebSocket: {user_text}")
        await request_response(websocket)
        print(f"request_response: {user_text}")
        print(f"LLM response: {state.text}")
        await single_interaction(websocket)
        print(f"single_interaction: {user_text}")
    except Exception as e:
        print(f"Connection error: {e}")
        # websocket = None
        return JSONResponse({"answer": "Connection lost. Please try again."})

    current_text = state.text.strip()
    state.text += "\n 2-------------------------------------------------- \n"
    return JSONResponse({"answer": current_text})

@app.post("/ask_audio")
async def ask_audio(file: UploadFile = File(...)):
    """
    Handle audio queries.
    """
    global websocket
    audio_bytes = await file.read()
    encoded_audio = base64.b64encode(audio_bytes).decode('utf-8')

    state = State()
    state.pcm_data = b""

    await websocket.send(json.dumps({
         'type': 'conversation.item.create',
         'item': {
             'type': 'message',
             'role': 'user',
             'content': [
                 {'type': 'input_audio', 'audio': encoded_audio}
             ]
         }
    }))
    await request_response(websocket)
    await single_interaction(websocket)

    current_text = state.text.strip()
    state.text += "\n 3-------------------------------------------------- \n"
    return JSONResponse({"answer": current_text})


@app.get("/media_paths")
async def get_media_paths():
    """
    Returns the last retrieved media paths.
    This endpoint is intended for use by the UI only.
    """
    state = State()
    if not state.last_media_paths:
        return JSONResponse({"error": "No media paths retrieved yet."})
    # Optionally, once fetched you can clear the state.
    media_data = state.last_media_paths

    return JSONResponse({"media_paths": media_data})

@app.get("/summary")
async def summary():
    """
    Returns a summary of the important events within the last 24 hours.
    The endpoint calculates the start (24 hours ago) and current date/time,
    formats them into words, and then sends a text query to the LLM to summarize events.
    """
    if not await ensure_connection():
        return JSONResponse({"summary": "I'm having trouble connecting to the assistant service. Please try again."})
    timeframe = os.getenv("SUMMARY_TIMEFRAME", "daily").lower()
    now = datetime.now()

    if timeframe == "daily":
        # For daily summaries, use fixed times on the current day.
        current_date = now.date()
        start = datetime.combine(current_date, time(0, 0))
        end = datetime.combine(current_date, time(19, 0))
    elif timeframe == "weekly":
        # For weekly summaries, use the past 7 days (relative to now)
        start = now - timedelta(days=7)
        end = now
    elif timeframe == "monthly":
        # For monthly summaries, use the past 30 days (relative to now)
        start = now - timedelta(days=30)
        end = now
    else:
        # Fallback to daily if an unrecognized value is provided
        current_date = now.date()
        start = datetime.combine(current_date, time(7, 0))
        end = datetime.combine(current_date, time(19, 0))

    summary_query = (
        f"Please provide a summary of the important events from {start} to {end}. "
        f"Only include major events that would be relevant to a smart home assistant user."
    )

    state = State()
    state.pcm_data = b""
    state.reset()
    state.text = ""
    state.last_media_paths = []
    try:
    # Send the summary query to the LLM
        await websocket.send(json.dumps({
            'type': 'conversation.item.create',
            'item': {
                'type': 'message',
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': summary_query }
                ]
            }
        }))
        await request_response(websocket)
        await single_interaction(websocket, text_only=True)
    except Exception as e:
        print(f"Connection error: {e}")
        # websocket = None
        return JSONResponse({"summary": "Connection lost. Please try again."})
    summary_answer = state.text.strip()
    state.text += "\n 4-------------------------------------------------- \n"
    return JSONResponse({"summary": summary_answer})

if __name__ == "__main__":
    uvicorn.run("web_demo:app", host="0.0.0.0", port=8000, reload=True)
