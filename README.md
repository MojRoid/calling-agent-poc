# Calling Agent Service

A Python-based phone calling service that integrates Twilio Media Streams with Google's Gemini 2.5 Flash Live API for real-time conversational AI.

## Overview

This service enables:
- Placing phone calls via Twilio
- Real-time audio streaming using Twilio Media Streams
- Integration with Google's Gemini 2.5 Flash model for conversational AI
- Bidirectional audio processing with automatic interruption handling

## Architecture

```
Phone Call ↔ Twilio ↔ Your Server ↔ Google Gemini Live API
                ↕
             WebSocket
                ↕  
         Your ngrok URL
```

### Components
- **FastAPI Server**: Handles HTTP endpoints and WebSocket connections
- **Twilio Integration**: Places calls and manages media streams
- **Gemini Client**: Connects to Google's Gemini API for AI processing
- **Media Stream Handler**: Bridges Twilio and Gemini for real-time audio
- **Audio Converter**: Handles μ-law/PCM audio format conversions

## Prerequisites

- Python 3.9 or higher
- Twilio Account with:
  - Account SID
  - Auth Token
  - Phone Number
- Google Cloud Project with:
  - Vertex AI API enabled
  - Access to `gemini-live-2.5-flash-preview-native-audio` model
  - Proper authentication (gcloud CLI logged in)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd calling-agent-poc
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

If you have an issue with audioop, also run:
```bash
pip install audioop-lts
```

3. Set up Google Cloud authentication:
```bash
# Login to Google Cloud
gcloud auth login
gcloud auth application-default login
```

## Configuration

The service requires a `.env` file with your configuration values. Copy `.env.example` to `.env` and update with your values:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=+1234567890

# Vertex AI Configuration
VERTEX_PROJECT_ID=your-project-id
VERTEX_LOCATION=us-central1

# Server Configuration
SERVER_BASE_URL=https://your-ngrok-url.ngrok-free.app
SERVER_PORT=8080

# Gemini Model Configuration
GEMINI_MODEL=gemini-2.5-flash-preview-native-audio-dialog

# Test Configuration
TEST_PHONE_NUMBER=+1234567890
```

## System Prompt Configuration

The AI assistant's behavior is controlled by the `gemini_system_prompt.txt` file. This file is **required** for the application to start.

Edit `gemini_system_prompt.txt` to customize the assistant's personality and behavior:

```
You are a helpful cooking assistant. You are knowledgeable about:
- Various cuisines from around the world
- Cooking techniques and methods
- Recipe creation and modification

Keep your responses conversational and appropriate for phone conversations.
```

## Running the Service

1. **Start the server**:
   ```bash
   python app.py
   ```
   The server will start on port 8080.

2. **Set up ngrok** (for local development):
   ```bash
   ngrok http 8080 --domain=your-ngrok-url.ngrok-free.app
   ```
   Update `SERVER_BASE_URL` in your `.env` file with your ngrok URL.

3. **Place a test call**:
   
   Using the test script (recommended):
   ```bash
   python make_test_call.py
   ```
   
   Or using curl directly:
   ```bash
   curl -X POST http://localhost:8080/place-call \
     -H "Content-Type: application/json" \
     -d '{
       "to": "+1234567890"
     }'
   ```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Root endpoint |
| `/health` | GET | Health check |
| `/place-call` | POST | Initiate a phone call |
| `/twiml/stream` | POST | Twilio webhook (internal) |
| `/call-status` | POST | Twilio status callback (internal) |
| `/media-stream` | WebSocket | Real-time audio streaming (internal) |

### Place Call Request

```json
{
  "to": "+1234567890"
}
```

Response:
```json
{
  "callSid": "CAxxxxxxxxxx",
  "status": "queued"
}
```

## Live API Features

The Gemini integration includes advanced features:

- **Automatic Interruption Handling**: Users can interrupt the AI naturally
- **Voice Activity Detection (VAD)**: Automatically detects speech start/end
- **Real-time Transcriptions**: Logs what both user and AI say
- **Affective Dialog**: Natural, emotionally appropriate responses
- **Proactive Audio**: More fluid, natural conversation flow

## Call Handling Features

- **Answering Machine Detection**: Automatically detects voicemail and hangs up without leaving a message
- **Declined Call Handling**: Ends the call immediately if declined/busy
- **No Voicemail**: The system will not leave voicemail messages
- **Call Status Tracking**: Monitors call status (answered, busy, failed, no-answer)

## Audio Processing

- **Twilio → Service**: μ-law encoded, 8kHz sample rate
- **Service → Gemini**: PCM, 16kHz sample rate (upsampled)
- **Gemini → Service**: PCM, 24kHz sample rate
- **Service → Twilio**: μ-law encoded, 8kHz (downsampled)

The service automatically records conversations in the `recordings/` directory for debugging purposes.

## Testing

Run all tests:
```bash
python run_tests.py
```

Run individual test suites:
```bash
# Test audio converter
python tests/test_audio_converter.py

# Test Twilio service (mocked)
python tests/test_twilio_service.py

# Test Gemini client (requires authentication)
python tests/test_gemini_client.py

# Test API endpoints (requires running server)
python tests/test_api_endpoints.py
```

## Test Utilities

### Test Script

Use `make_test_call.py` to easily test your calling agent:

```bash
python make_test_call.py
```

This script will:
- Check if your server is running
- Use the `TEST_PHONE_NUMBER` from your `.env` file
- Place a test call with proper error handling
- Provide detailed status information

Make sure to set `TEST_PHONE_NUMBER` in your `.env` file to your phone number.

## Project Structure
```
calling-agent-poc/
├── .env                            # Configuration values (create this)
├── app.py                          # Main FastAPI application
├── config.py                       # Configuration loader
├── models.py                       # Data models
├── gemini_system_prompt.txt        # AI assistant instructions (required)
├── requirements.txt                # Python dependencies
├── run_tests.py                    # Test runner script
├── make_test_call.py              # Utility to place test calls
├── services/
│   ├── twilio_service.py          # Twilio integration
│   ├── gemini_client.py           # Gemini API client
│   ├── media_stream_handler.py    # WebSocket handler
│   └── audio_converter_simple.py  # Audio format converter
└── tests/
    ├── test_twilio_service.py
    ├── test_gemini_client.py
    ├── test_audio_converter.py
    └── test_api_endpoints.py
```

## Troubleshooting

### Missing Configuration
If you see errors about missing configuration values:
- Ensure you've created a `.env` file with all required values
- Check that all values in the `.env` file are correct
- The application will not start without all required configuration

### Authentication Issues
- Ensure you're logged in: `gcloud auth list`
- Run `gcloud auth application-default login` for credentials
- Verify your project has access to the Gemini model

### Model Access
If you see "model not found" errors, your project needs access to the model:
1. Visit [Vertex AI Model Garden](https://console.cloud.google.com/vertex-ai/model-garden)
2. Search for the model
3. Request access for your project

### Connection Issues
- Ensure your ngrok URL is accessible from the internet
- Check that Twilio webhooks can reach your server
- Verify WebSocket connections are not blocked by firewalls

### Audio Issues
- Check the recordings in `recordings/` directory for debugging
- Verify audio is being received from both Twilio and Gemini
- Review logs for audio processing errors 