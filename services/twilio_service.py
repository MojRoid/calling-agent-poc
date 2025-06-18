import logging
from typing import Optional, Dict
from twilio.rest import Client
from twilio.rest.api.v2010.account.call import CallInstance
import urllib.parse
import html

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    SERVER_BASE_URL
)

logger = logging.getLogger(__name__)

class TwilioService:
    """Service for handling Twilio operations"""
    
    def __init__(self):
        """Initialize Twilio client"""
        self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("Twilio service initialized")
    
    def place_call(self, to: str) -> CallInstance:
        """
        Place a phone call with machine detection to avoid voicemail.
        """
        logger.info(f"Placing call to: {to}")
        
        twiml_url = f"{SERVER_BASE_URL}/twiml/stream"
        status_callback_url = f"{SERVER_BASE_URL}/call-status"
        
        logger.critical(f"Telling Twilio to fetch TwiML from the static URL: {twiml_url}")
        logger.critical("Ensure your ngrok tunnel is active with the command: ngrok http 8080 --domain=striking-iguana-amazingly.ngrok-free.app")
        
        logger.info(f"Creating call with TwiML URL: {twiml_url}")
        logger.info(f"Status callback URL: {status_callback_url}")
        logger.info(f"From: {TWILIO_PHONE_NUMBER}, To: {to}")
        
        call = self.client.calls.create(
            to=to,
            from_=TWILIO_PHONE_NUMBER,
            url=twiml_url,
            method="POST",
            status_callback=status_callback_url,
            status_callback_event=["initiated", "ringing", "answered", "completed", "failed", "busy", "no-answer"],
            status_callback_method="POST",
            machine_detection="Enable",  # Options: Enable, DetectMessageEnd, or Disable
            machine_detection_timeout=3000,  # 3 seconds timeout
            # With 'Enable' mode, AnsweredBy can be: human, machine_start, machine_end_beep, machine_end_silence, machine_end_other, fax, unknown
        )
        
        logger.info(f"Call initiated with SID: {call.sid}")
        logger.info(f"Call status: {call.status}")
        logger.info("Machine detection enabled - will end call if answering machine detected")
        return call
    
    def generate_stream_twiml(self, answered_by: Optional[str] = None) -> str:
        """
        Generate TwiML based on who answered (human or machine).
        If machine answered, just hang up.
        """
        # Hang up immediately for fax or answering machine
        if answered_by in ["fax", "machine_start", "machine_end_beep", "machine_end_silence", "machine_end_other"]:
            logger.info(f"Call answered by {answered_by} - hanging up immediately (no voicemail)")
            return '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup/>
</Response>'''
        
        # Normal flow for human-answered calls
        ws_url = SERVER_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
        ws_endpoint = f"{ws_url}/media-stream"
        
        logger.info(f"Generating TwiML with WebSocket URL: {ws_endpoint}")
        logger.info(f"Call answered by: {answered_by if answered_by else 'unknown (treating as human)'}")
        
        # Connect directly to WebSocket without any Say messages
        # Gemini will handle the initial greeting with recording disclaimer
        twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting you now, one moment please..</Say>
    <Connect>
        <Stream url="''' + ws_endpoint + '''">
        </Stream>
    </Connect>
</Response>'''
        
        logger.debug(f"Generated TwiML: {twiml}")
        logger.info("TwiML generation complete")
        return twiml
    
    def update_call(self, call_sid: str, status: str = "completed") -> bool:
        """
        Update a call to end it immediately.
        """
        try:
            logger.info(f"Updating call {call_sid} to status: {status}")
            call = self.client.calls(call_sid).update(status=status)
            logger.info(f"Call {call_sid} updated successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to update call {call_sid}: {e}")
            return False 