from asyncio import Queue
import asyncio
import websockets
import json
import os
from dotenv import load_dotenv
from state import State
from recording import record_voice_input
import base64
from database import query_database, DB_TABLE_NAME
from audio_manager import AudioManager

audio = AudioManager()

recv_lock = asyncio.Lock()


load_dotenv()

# Load the system prompt from the prompt file.
with open("prompt.txt", "r") as f:
    SYSTEM_PROMPT = f.read().strip()


OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
model=os.getenv('MODEL')
OPENAI_REALTIME_ENDPOINT = 'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01'

tool_specification = [
    {
        "type": "function",
        "name": "query_database",
        "description": "Executes a SQL query on the smart home events database using psycopg2 and returns the results. Provide the SQL query and parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The SQL query string with placeholders."
                },
            },
            "required": ["query"]
        }
    },
    {
        "type": "function",
        "name": "retrieve_media_paths",
        "description": "Retrieves the hidden snapshot_path and video_path for a given event using its event_id. These values must not be spoken aloud.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "The unique identifier for the event."
                }
            },
            "required": ["event_id"]
        }
    }
]

async def connect_to_openai():
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'OpenAI-Beta': 'realtime=v1',
        'Connection': 'keep-alive',
    }

    websocket = await websockets.connect(OPENAI_REALTIME_ENDPOINT, additional_headers=headers, ping_interval=10, ping_timeout=30)

    # Configure the session with the tool
    await websocket.send(json.dumps({
        'type': 'session.update',
         "session": {
             "modalities": ["audio", "text"],
             "instructions": SYSTEM_PROMPT,
             "voice": os.getenv('VOICE', 'ash'),
             "input_audio_format": "pcm16",
             "output_audio_format": "pcm16",
             "tools": tool_specification,
             "turn_detection": None,
        }
    }))
    return websocket

async def request_response(websocket, additional_msg=""):
    msg = SYSTEM_PROMPT + "\n\n" + additional_msg
    await websocket.send(json.dumps({
        'type': 'response.create',
        "response": {
            "modalities": ["audio", "text"],
            "instructions": msg,
            "voice": os.getenv('VOICE', 'ash'),
            "tools": tool_specification,
            "tool_choice": "auto",
        },
    }))

async def record_and_send(websocket):
    audio_data = await record_voice_input()
    encoded_audio = base64.b64encode(audio_data).decode('utf-8')
    await websocket.send(json.dumps({
        'type': 'conversation.item.create',
        'item': {
            'type': 'message',
            'role': 'user',
            'content': [
                {
                    'type': 'input_audio',
                    'audio': encoded_audio
                }
            ]
        }
    }))
    await request_response(websocket)


def play_audio_response():
    """
    Spawn a background thread to play the latest PCM audio response,
    allowing interruption on hotword detection.
    """
    state = State()
    if state.pcm_data:
        audio.stop_playback_event.clear()
        audio.play(state.pcm_data)
        state.pcm_data = b""

async def process_function_call(response, websocket):
    state = State()
    tool_name = response.get('name')
    tool_arguments = json.loads(response.get('arguments', '{}'))
    print(f"Using function {tool_name} with arguments {tool_arguments}")

    if tool_name == 'request_user_response':
        await record_and_send(websocket)
        tool_output = ''
    elif tool_name == 'end_conversation':
        state.end_conversation = True
        tool_output = ''
    elif tool_name == 'query_database':
        query = tool_arguments.get('query')
        result = query_database(query)
        # Filter out raw SQL and error details from user-facing responses
        if isinstance(result, dict) and 'error' in result:
            tool_output = "I can't access the database right now. But I'll keep trying."
        else:
            # Return structured data instead of raw query results
            tool_output = json.dumps(result, default=str)
    elif tool_name == 'retrieve_media_paths':
        event_id = tool_arguments.get('event_id')
        if not event_id:
            # Return an error if no event_id provided
            tool_output = json.dumps({"error": "Missing event_id"})
        else:
            query = f"SELECT snapshot_path, video_path FROM {DB_TABLE_NAME} WHERE event_id = '{event_id}';"
            result = query_database(query)
            state.last_media_paths.append(result)
            tool_output = "Media retrieved successfully."
    else:
        raise ValueError(f"Unknown tool: {tool_name}")

    print(f"Tool output: {tool_output}")

    # Send the tool output back to the conversation.
    # (For retrieve_media_paths, this will be the dummy message)
    if tool_output:
        await websocket.send(json.dumps({
            'type': 'conversation.item.create',
            'item': {
                'type': 'function_call_output',
                'call_id': response['call_id'],
                'output': tool_output
            }
        }))
        # Request a new response from the LLM.
        await request_response(websocket)

async def process_message(message, websocket, text_only=False):
    state = State()
    response = json.loads(message)
    response_type = response.get('type')
    # print(response_type)

    # if response_type == 'response.done':
    #     return True
    if response_type == "response.audio_transcript.delta":
        state.text += response['delta']
    elif response_type == 'response.audio.delta':
        delta = response['delta']
        state.pcm_data += base64.b64decode(delta)
    elif response_type == 'response.text.delta':
        state.text += response['delta']
    elif response_type in ('response.audio.done', 'response.audio_transcript.done'):
        print(state.text)
        # Drain the websocket
        while True:
            try:
                drained = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                # print(drained)
            except asyncio.TimeoutError:
                break
        if not text_only:
            play_audio_response()
        return True
        # state.text = ""
    elif response_type == 'response.function_call_arguments.done':
        await process_function_call(response, websocket)

    return False

async def message_listener(websocket, queue):
    state = State()
    try:
        async for message in websocket:
            await queue.put(message)
    except websockets.exceptions.ConnectionClosed:
        state.end_conversation = True
        print("Connection Closed")
        return

async def clarify(websocket):
    await websocket.send(json.dumps({
        'type': 'conversation.item.create',
        'item': {
            'type': 'message',
            'role': 'user',
            'content': [
                {
                    'type': 'input_text',
                    'text': "It seems the conversation has halted. Perhaps you forgot to call the 'request_user_response' tool or the 'end_conversation' tool. Do not reply to this message, simply call the tool."
                }
            ]
        }
    }))
    await request_response(websocket)



async def single_interaction(websocket, text_only=False, timeout=30):
    async with recv_lock:
        try:
            async with asyncio.timeout(timeout): 
                async for message in websocket:
                    status = await process_message(message, websocket, text_only)
                    if status:
                        break
        except asyncio.TimeoutError as e:
                print("WebSocket response timed out", e)
                status = await process_message("ERROR: WebSocket response timed out", websocket, text_only)
                return 


async def conversation_loop(websocket):
    state = State()
    queue = Queue()
    listener_task = asyncio.create_task(message_listener(websocket, queue))
    empty_for = 0
    while not state.end_conversation:
        if not queue.empty():
            message = await queue.get()
            await process_message(message, websocket)
            empty_for = 0
        else:
            await asyncio.sleep(0.1)
            empty_for += 1
            if empty_for > 10:
                print("Clarification requested")
                await clarify(websocket)
                empty_for = 0
    listener_task.cancel()
