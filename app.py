import logging
import os
import sys
from datetime import datetime
from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import SERVER_PORT, DEFAULT_SYSTEM_INSTRUCTIONS
from models import PlaceCallRequest, PlaceCallResponse
from services.twilio_service import TwilioService
from services.media_stream_handler import MediaStreamHandler
from services.gemini_connection_pool import connection_pool

# Enhanced logging setup
def setup_logging():
    """Setup comprehensive logging for debugging"""
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/calling_agent_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Set specific loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("websockets").setLevel(logging.DEBUG)
    logging.getLogger("twilio").setLevel(logging.DEBUG)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured. Log file: {log_file}")
    return logger

# Setup logging
logger = setup_logging()

# Check if system prompt is loaded
if DEFAULT_SYSTEM_INSTRUCTIONS is None:
    logger.error("FATAL: System prompt not loaded. Cannot start application.")
    logger.error("Please ensure 'gemini_system_prompt.txt' exists and contains valid instructions.")
    sys.exit(1)

app = FastAPI(
    title="Calling Agent Service",
    description="AI-powered phone calling agent with real-time audio streaming",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
twilio_service = TwilioService()

@app.on_event("startup")
async def startup_event():
    """Application startup"""
    logger.info("Starting Calling Agent Service...")
    logger.info(f"System prompt loaded: {len(DEFAULT_SYSTEM_INSTRUCTIONS)} characters")
    
    # Start the Gemini connection pool
    try:
        await connection_pool.start()
        logger.info("✅ Gemini connection pool initialized")
    except Exception as e:
        logger.error(f"Failed to start connection pool: {e}")
        # Continue anyway - connections will be created on demand
    
    logger.info("Services initialized successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown"""
    logger.info("Shutting down Calling Agent Service...")
    
    # Stop the connection pool
    try:
        await connection_pool.stop()
        logger.info("✅ Gemini connection pool stopped")
    except Exception as e:
        logger.error(f"Error stopping connection pool: {e}")
    
    logger.info("Shutdown complete")

@app.get("/")
async def root():
    """Root endpoint"""
    logger.info("Root endpoint accessed")
    return {"message": "Calling Agent Service is running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.info("Health check requested")
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "twilio": "initialized"
        }
    }

@app.post("/place-call")
async def place_call(request: PlaceCallRequest):
    """Place a phone call."""
    logger.info(f"Call request received: {request}")
    
    try:
        call = twilio_service.place_call(to=request.to)
        
        logger.info(f"Call placed successfully. SID: {call.sid}, Status: {call.status}")
        
        return PlaceCallResponse(
            callSid=call.sid,
            status=call.status
        )
        
    except Exception as e:
        logger.error(f"Failed to place call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to place call: {str(e)}")

@app.post("/twiml/stream")
async def generate_twiml(request: Request):
    """
    Generate TwiML for call handling.
    Checks if answered by human or machine.
    """
    logger.info("TwiML request received")
    
    # Check if call was answered by machine
    try:
        form_data = await request.form()
        answered_by = form_data.get("AnsweredBy")
        logger.info(f"Call answered by: {answered_by}")
    except:
        answered_by = None
    
    try:
        twiml = twilio_service.generate_stream_twiml(answered_by=answered_by)
        logger.info("TwiML generated successfully")
        logger.debug(f"TwiML content: {twiml}")
        
        return Response(content=twiml, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Failed to generate TwiML: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate TwiML: {str(e)}")

@app.post("/call-status")
async def handle_call_status(request: Request):
    """
    Handle call status callbacks from Twilio.
    Tracks call progress through various states.
    """
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")
        
        logger.info(f"Call status update - SID: {call_sid}, Status: {call_status}")
        
        # Track different call states
        if call_status == "initiated":
            logger.info(f"📞 Call {call_sid} initiated - preparing to dial")
        elif call_status == "ringing":
            logger.info(f"🔔 Call {call_sid} is ringing - waiting for answer")
            logger.info(f"💡 Pre-warmed connections available: {connection_pool.available_connections.qsize()}")
            # Could trigger additional pre-warming here if needed
        elif call_status == "answered":
            logger.info(f"✅ Call {call_sid} answered - WebSocket will connect soon")
        elif call_status in ["busy", "no-answer", "failed"]:
            logger.info(f"❌ Call {call_sid} was {call_status}")
            
        return Response(content="", status_code=200)
        
    except Exception as e:
        logger.error(f"Error handling call status: {e}", exc_info=True)
        return Response(content="", status_code=200)  # Return 200 to avoid Twilio retries

@app.websocket("/media-stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for media streaming"""
    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info(f"=== New WebSocket connection attempt from {client_ip} ===")
    logger.info(f"WebSocket headers: {websocket.headers}")
    
    try:
        # Accept the WebSocket connection
        await websocket.accept()
        logger.info(f"✅ WebSocket connection accepted from {client_ip}")
        
        # The handler will manage the entire lifecycle of the stream
        media_handler = MediaStreamHandler(websocket)
        await media_handler.handle_stream()
        
    except Exception as e:
        logger.error(f"❌ Error in WebSocket endpoint: {e}", exc_info=True)
    finally:
        logger.info(f"=== WebSocket connection with {client_ip} has been closed ===")

if __name__ == "__main__":
    logger.info("Starting Calling Agent Server...")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=SERVER_PORT,
        log_level="info",
        reload=False  # Disable reload to prevent crashes during testing
    ) 