import sounddevice as sd
import json
import yaml
import os
import paho.mqtt.client as mqtt
import asyncio

# --- Import OpenAI TTS Tools ---
from openai import AsyncOpenAI
from openai.helpers import LocalAudioPlayer

from dotenv import load_dotenv

load_dotenv()

# Create an instance of AsyncOpenAI
openai = AsyncOpenAI()

async def tts_speak(text: str) -> None:
    """
    Calls OpenAI's TTS API using a streaming response and plays the audio
    using LocalAudioPlayer.
    """
    instructions = "You are Jupyter, a smart home assistant integrated with our surveillance and event logging system. Simply speak the text provided to you. Do not add any additional information or context."

    sd.default.device = (int(os.getenv("MICROPHONE_DEVICE_ID")), int(os.getenv("SPEAKER_DEVICE_ID")))
    import ipdb; ipdb.set_trace()  # BREAKPOINT
    print("Preparing TTS for:", text)
    async with openai.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice=os.getenv("VOICE", "ash"),
        input=text,
        instructions=instructions,
        response_format="pcm",
    ) as response:
        await LocalAudioPlayer().play(response)

# --- Load event templates from YAML ---
TEMPLATE_FILE = os.getenv("EVENT_TEMPLATES_FILE", "event_templates.yml")
with open(TEMPLATE_FILE, "r") as file:
    event_templates = yaml.safe_load(file)

# --- MQTT Event Callback ---
def on_message(client, userdata, msg):
    try:
        # Parse the incoming JSON payload.
        payload = json.loads(msg.payload.decode('utf-8'))
        print("Received payload:", payload)

        # Determine the event type (expects an "event_type" field).
        event_type = payload.get("event_type")
        if not event_type:
            print("No event_type found in payload.")
            return

        # Lookup the template for the event type.
        if event_type not in event_templates:
            print(f"No template found for event type: {event_type}")
            return

        template = event_templates[event_type]

        try:
            # Fill in the template placeholders with event payload data.
            filled_text = template.format(**payload)
        except KeyError as ke:
            print(f"Missing field in event payload for placeholder: {ke}")
            return

        # Call the asynchronous TTS function using asyncio.run.
        print("Filled text:", filled_text)
        asyncio.run(tts_speak(filled_text))

    except Exception as e:
        print("Error processing MQTT message:", e)

# --- Main MQTT Listener Function ---
def main():
    client = mqtt.Client()
    client.on_message = on_message

    # Connect to the MQTT broker.
    mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    client.connect(mqtt_broker, mqtt_port, 60)

    # Subscribe to the topic specified by the environment or default.
    topic = os.getenv("MQTT_TOPIC", "smart_home/events")
    client.subscribe(topic)

    print(f"Listening for events on topic '{topic}' at {mqtt_broker}:{mqtt_port}...")

    # Run the MQTT network loop.
    client.loop_forever()

if __name__ == "__main__":
    main()
