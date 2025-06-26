import express from 'express';
import * as http from 'http';
import * as WebSocket from 'ws';
import cors from 'cors';
import multer from 'multer';
import { createLogger } from './utils/logger';
import { SERVER_PORT, DEFAULT_SYSTEM_INSTRUCTIONS } from './config';
import { PlaceCallRequest, PlaceCallResponse } from './models';
import { TwilioService } from './services/twilioService';
import { MediaStreamHandler } from './services/mediaStreamHandler';

const appLogger = createLogger('app');

// Check if system prompt is loaded
if (!DEFAULT_SYSTEM_INSTRUCTIONS) {
  appLogger.error('FATAL: System prompt not loaded. Cannot start application.');
  appLogger.error("Please ensure 'gemini_system_prompt.txt' exists and contains valid instructions.");
  process.exit(1);
}

// Initialize services
const twilioService = new TwilioService();

// Create Express app
const app = express();

// Create HTTP server
const server = http.createServer(app);

// Create WebSocket server
const wss = new WebSocket.Server({ 
  server,
  path: '/media-stream'
});

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Configure multer for form data
const upload = multer();

// Root endpoint
app.get('/', (_req, res) => {
  appLogger.info('Root endpoint accessed');
  res.json({ message: 'Calling Agent Service is running' });
});

// Health check endpoint
app.get('/health', (_req, res) => {
  appLogger.info('Health check requested');
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    services: {
      twilio: 'initialized'
    }
  });
});

// Place call endpoint
app.post('/place-call', async (req, res) => {
  const request: PlaceCallRequest = req.body;
  appLogger.info(`Call request received: ${JSON.stringify(request)}`);
  
  try {
    const call = await twilioService.placeCall(request.to);
    
    appLogger.info(`Call placed successfully. SID: ${call.sid}, Status: ${call.status}`);
    
    const response: PlaceCallResponse = {
      callSid: call.sid,
      status: call.status
    };
    
    res.json(response);
  } catch (error) {
    appLogger.error(`Failed to place call: ${error}`, { stack: error });
    res.status(500).json({ error: `Failed to place call: ${error}` });
  }
});

// TwiML stream endpoint
app.post('/twiml/stream', upload.none(), async (req, res) => {
  appLogger.info('TwiML request received');
  
  // Check if call was answered by machine
  const answeredBy = req.body.AnsweredBy;
  appLogger.info(`Call answered by: ${answeredBy}`);
  
  try {
    const twiml = twilioService.generateStreamTwiml(answeredBy);
    appLogger.info('TwiML generated successfully');
    appLogger.debug(`TwiML content: ${twiml}`);
    
    res.type('application/xml');
    res.send(twiml);
  } catch (error) {
    appLogger.error(`Failed to generate TwiML: ${error}`, { stack: error });
    res.status(500).json({ error: `Failed to generate TwiML: ${error}` });
  }
});

// Call status endpoint
app.post('/call-status', upload.none(), async (req, res) => {
  try {
    const callSid = req.body.CallSid;
    const callStatus = req.body.CallStatus;
    
    appLogger.info(`Call status update - SID: ${callSid}, Status: ${callStatus}`);
    
    // Track different call states
    if (callStatus === 'initiated') {
      appLogger.info(`📞 Call ${callSid} initiated - preparing to dial`);
    } else if (callStatus === 'ringing') {
      appLogger.info(`🔔 Call ${callSid} is ringing - waiting for answer`);
    } else if (callStatus === 'answered') {
      appLogger.info(`✅ Call ${callSid} answered - WebSocket will connect soon`);
    } else if (['busy', 'no-answer', 'failed'].includes(callStatus)) {
      appLogger.info(`❌ Call ${callSid} was ${callStatus}`);
    }
    
    res.status(200).send('');
  } catch (error) {
    appLogger.error(`Error handling call status: ${error}`, { stack: error });
    res.status(200).send(''); // Return 200 to avoid Twilio retries
  }
});

// WebSocket handler
wss.on('connection', (ws: WebSocket, req) => {
  const clientIp = req.socket.remoteAddress || 'unknown';
  
  appLogger.info(`📞 New call from ${clientIp}`);
  
  // The handler will manage the entire lifecycle of the stream
  const mediaHandler = new MediaStreamHandler(ws);
  
  // Handle stream asynchronously
  mediaHandler.handleStream().catch(error => {
    appLogger.error(`❌ Error in WebSocket handler: ${error}`, { stack: error });
  });
});

// Error handling middleware
app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  appLogger.error(`Unhandled error: ${err.message}`, { stack: err.stack });
  res.status(500).json({ error: 'Internal server error' });
});

// Start server
function startServer() {
  server.listen(SERVER_PORT, '0.0.0.0', () => {
    appLogger.info('Starting Calling Agent Service...');
    appLogger.info(`System prompt loaded: ${DEFAULT_SYSTEM_INSTRUCTIONS?.length || 0} characters`);
    appLogger.info('Services initialized successfully');
    appLogger.info(`Server listening on http://0.0.0.0:${SERVER_PORT}`);
  });
}

// Handle shutdown gracefully
process.on('SIGTERM', () => {
  appLogger.info('SIGTERM received, shutting down gracefully...');
  server.close(() => {
    appLogger.info('Server closed');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  appLogger.info('SIGINT received, shutting down gracefully...');
  server.close(() => {
    appLogger.info('Server closed');
    process.exit(0);
  });
});

// Start the server
if (require.main === module) {
  startServer();
}

export { app, server }; 