# Use an official Python runtime as a parent image
FROM python:3.11.11-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Install system dependencies, including audio libraries for microphone/speaker access
RUN apt-get update && apt-get install -y \
    build-essential \
    # libgl1-mesa-glx \
    libgl1 \
    libglib2.0-0 \
    portaudio19-dev \
    libasound2-dev \
    ffmpeg \
    pulseaudio \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install Python dependencies
COPY requirements.txt .


# Set default environment variables
ENV MICROPHONE_DEVICE_ID=-1
ENV SPEAKER_DEVICE_ID=-1
ENV SUMMARY_TIMEFRAME=daily
ENV EVENT_TEMPLATES_FILE=event_templates.yml
ENV VOICE=ash
ENV MQTT_BROKER=172.17.0.1
ENV MQTT_PORT=1883
ENV MQTT_TOPIC=smart_home/events
ENV DB_PORT=5432
RUN pip install uv
RUN uv pip install --system -r requirements.txt 

# Copy the rest of the application code
COPY . .

# Expose ports as needed (e.g., web demo on 8000 and PostgreSQL on 5432 if required)
EXPOSE 8001
EXPOSE 5432

# Run the main application script when the container launches.
CMD ["uvicorn", "web_demo:app", "--host", "0.0.0.0", "--port", "8001"]
# CMD ["python", "test_audio.py"]
# CMD ["python", "create_database.py"]
# CMD ["/bin/bash"]
