# Calling Agent POC (TypeScript)

An AI-powered phone calling agent that can make automated phone calls using Twilio and Google's Gemini AI. The agent can have natural conversations, handle interruptions, and summarize call outcomes.

## Features

- 🤖 Real-time conversational AI using Google Gemini
- 📞 Automated phone calls via Twilio
- 🎤 Real-time audio streaming and processing
- 🚫 Machine detection to avoid voicemails
- 📝 Automatic call summarization
- 🔊 High-quality audio conversion between formats
- 💾 Call recording for debugging

## Prerequisites

- Node.js 18+ and npm
- Twilio account with phone number
- Google Cloud account with Vertex AI enabled
- ngrok for local development (or public URL for webhooks)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd calling-agent-poc
```

2. Install dependencies:
```bash
npm install
```

3. Create `.env` file with your credentials:
```bash
# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890  # Your Twilio phone number

# Google Vertex AI Configuration
VERTEX_PROJECT_ID=your_gcp_project_id
VERTEX_LOCATION=us-central1  # or your preferred location

# Gemini Model
GEMINI_MODEL=gemini-1.5-flash-002

# Server Configuration
SERVER_BASE_URL=https://your-domain.ngrok-free.app  # Your public URL
SERVER_PORT=8080

# Test Configuration (optional)
TEST_PHONE_NUMBER=+1234567890  # Phone number to test calls
```

4. Create `gemini_system_prompt.txt` with your AI agent's instructions. Example content is already provided in the file.

## Running the Application

### Development Mode

Run with auto-reload on file changes:
```bash
npm run dev
```

### Production Mode

Build and run:
```bash
npm run build
npm start
```

### Setting up ngrok

If running locally, you need ngrok to expose your server:
```bash
ngrok http 8080
```

Update `SERVER_BASE_URL` in `.env` with the ngrok URL.

## Testing

### Make a Test Call

```bash
npm run test:call
```

This will place a call to the phone number configured in `TEST_PHONE_NUMBER`.

### API Endpoints

- `GET /` - Health check
- `GET /health` - Detailed health status
- `POST /place-call` - Initiate a phone call
  ```json
  {
    "to": "+1234567890"
  }
  ```
- `POST /twiml/stream` - Twilio webhook for TwiML
- `POST /call-status` - Twilio status callback
- `WS /media-stream` - WebSocket endpoint for audio streaming

## Architecture

The application consists of:

1. **Express Server** (`src/app.ts`) - Main HTTP server with WebSocket support
2. **Twilio Service** (`src/services/twilioService.ts`) - Handles phone call operations
3. **Gemini Client** (`src/services/geminiClient.ts`) - Manages AI conversation
4. **Media Stream Handler** (`src/services/mediaStreamHandler.ts`) - Bridges audio between Twilio and Gemini
5. **Audio Converter** (`src/services/audioConverter.ts`) - Converts between audio formats

### Call Flow

1. Client calls `/place-call` endpoint
2. Server initiates call via Twilio API
3. Twilio fetches TwiML instructions from `/twiml/stream`
4. When call is answered, Twilio connects to WebSocket at `/media-stream`
5. Audio streams bidirectionally between caller and Gemini AI
6. AI processes speech and responds in real-time
7. Call summary is generated when call ends

## Configuration

### System Prompt

Edit `gemini_system_prompt.txt` to customize the AI agent's behavior, personality, and objectives.

### Audio Settings

- Input: 8kHz μ-law from Twilio
- Processing: 16kHz PCM for Gemini
- Output: 24kHz PCM from Gemini
- Recording: Saved as WAV files in `recordings/` directory

## Development

### Project Structure

```
calling-agent-poc/
├── src/
│   ├── app.ts                 # Main application
│   ├── config.ts              # Configuration loader
│   ├── makeTestCall.ts        # Test call script
│   ├── models/                # TypeScript interfaces
│   ├── services/              # Service modules
│   └── utils/                 # Utility modules
├── dist/                      # Compiled JavaScript
├── logs/                      # Application logs
├── recordings/                # Call recordings
├── package.json               # Dependencies
├── tsconfig.json              # TypeScript config
└── gemini_system_prompt.txt   # AI instructions
```

### Building

```bash
npm run build
```

### Linting

```bash
npm run lint
```

### Formatting

```bash
npm run format
```

## Troubleshooting

1. **WebSocket Connection Issues**
   - Ensure ngrok is running and URL is updated
   - Check firewall settings
   - Verify Twilio webhook configuration

2. **Audio Quality Issues**
   - Check network latency
   - Verify audio conversion settings
   - Monitor CPU usage during calls

3. **Gemini Connection Issues**
   - Verify Google Cloud credentials
   - Check Vertex AI API is enabled
   - Ensure proper authentication setup

## License

MIT

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request 