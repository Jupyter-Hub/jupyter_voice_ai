# Jupyter Smart Home Assistant

This project is a multi-functional smart home assistant that integrates event logging, MQTT-based event listening, and voice interactions using OpenAI APIs. It includes an interactive web demo interface and a separate MQTT listener for events. The code is modular and highly configurable via editable files and environment variables.

---

## Editable Files

### `prompt.txt`
- **Role:**  
  This file contains the system prompt and schema description that guides the language model on how to interpret and answer user queries. It describes the database schema (without exposing sensitive fields) and instructs the assistant to use a dedicated tool (`retrieve_media_paths`) to retrieve media paths.
- **Modification:**  
  You can modify the prompt to change:
  - The explanation of the event schema.
  - The formatting guidelines (e.g., how dates/times are spoken).
  - Additional instructions for handling events or sensitive information.
- **Significance:**  
  Changes here influence the LLM’s behavior, ensuring responses are relevant, privacy-conscious, and follow the correct format when querying the underlying events.

### `.env`
- **Role:**  
  This file centralizes all runtime configuration for the application, including model settings, audio device IDs, database connection information, MQTT configuration, and TTS settings.
- **Editable Components:**  
  -**OPENAI_API_KEY:** Your OpenAI API key for accessing the LLM and TTS services.
  - **MODEL & VOICE:** Set the OpenAI model and voice used for LLM interactions.
  - **MICROPHONE_DEVICE_ID & SPEAKER_DEVICE_ID:** Device indices for audio input and output. Adjust these if yout want to use different audio devices.
  - **SUMMARY_TIMEFRAME:** Controls whether the summary is computed on a daily, weekly, or monthly basis.
  - **EVENT_TEMPLATES_FILE:** Specifies the name/path of the YAML file that contains the event templates.
  - **Database Settings:** `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` — configure your PostgreSQL connection.
  - **MQTT Settings:** `MQTT_BROKER`, `MQTT_PORT`, `MQTT_TOPIC` — set the connection details for receiving smart home events.
  - **TTS Settings:** `TTS_MODEL` – identifies the TTS model used to synthesize speech.
- **Significance:**  
  The `.env` file is crucial for dynamic configuration. It allows you to adjust the system's behavior (audio devices, time frames, external connections) without changing the source code.

### `event_templates.yml`
- **Role:**  
  This YAML file defines a set of string templates used to generate spoken messages for various event types. Each template uses placeholders (e.g., `{name}`, `{action}`, etc.) that are filled with data from incoming MQTT event payloads.
- **Editable Components:**  
  - Templates for individual event types (e.g., `dummy_event`, `parcel_arrival`).  
  - You can add, remove, or modify templates to suit the events that your smart home system generates.
- **Significance:**  
  This file links the event data to the audible notifications. By editing the templates, you control the narrative that is spoken when an event is received.

---

## Main Functionalities

### Entry Point: `web_demo.py`
- **Overview:**  
  This file serves as the primary entry point for the web demo interface. It sets up a FastAPI application which:
  - Hosts a static HTML page for user interaction.
  - Allows users to submit text and audio queries to the LLM.
  - Retrieves and displays responses along with any associated media details.
- **Core Features & Operations:**  
  - Handling HTTP endpoints for text queries (`/ask`), audio queries (`/record_and_ask`), summaries (`/summary`), and media paths (`/media_paths`).
  - Interacting with a websocket connection to receive real-time responses.
  - Automatically updating the UI with response text and media details from the database.

### MQTT Listener: `mqtt_listener.py`
- **Overview:**  
  This standalone script subscribes to an MQTT topic (configured via `.env`) and listens for smart home event messages.
- **Core Features & Operations:**  
  - Parsing incoming MQTT JSON payloads.
  - Looking up the corresponding string template from `event_templates.yml` based on the event’s `event_type`.
  - Filling in the placeholders in the template with event data.
  - Generating a spoken message using the OpenAI TTS API (via asynchronous calls) and playing the audio.
- **Significance:**  
  It allows the assistant to provide immediate audible notifications for events detected in the smart home system.

---

## Connecting Files

- **`prompt.txt`:** Guides the language model behavior across the entire application; its instructions affect the responses generated both in the web demo. 
- **`.env`:** Dynamically configures the system (database, MQTT, TTS, audio devices, and summary interval) that all other modules read during runtime.
- **`event_templates.yml`:** Provides a mapping between event types and the message templates used in `mqtt_listener.py` to generate spoken notifications.
- The modular design ensures that changes to any of these files—whether updating event formatting in the prompt or modifying the TTS settings in the `.env` file—are immediately reflected in the overall functionality of the application.

---

## Docker Deployment

To deploy the application in a Docker container, ensure you have Docker and Docker Compose installed. Then run the following command from your project directory:

```bash
docker-compose up --build
```

This command will:

Build the Docker image based on the provided Dockerfile.

Start the container with all required environment variables (loaded from `.env`), volume mounts (including audio devices and configuration files), and network settings.

Expose the web demo on the port specified in the `.env` file (default is port `8000`).

## Summary

This project integrates multiple functionalities:

- A FastAPI-based web demo (`web_demo.py`) for LLM interactions and media display.
- An MQTT listener (`mqtt_listener.py`) to process and audibly present event notifications based on YAML templates.
- Configuration through editable files (`prompt.txt`, `.env`, `event_templates.yml`), making the system customizable.
