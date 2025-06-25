import asyncio
import base64
import json
import logging
import wave
import os
from datetime import datetime
from typing import Optional
from fastapi import WebSocket
import websockets
import numpy as np
from scipy import signal

from services.gemini_client import GeminiLiveClient
from services.audio_converter_simple import SimpleAudioConverter
from models import TwilioMessage, CallSummary
from config import DEFAULT_SYSTEM_INSTRUCTIONS
from google.genai import types

logger = logging.getLogger(__name__)

class MediaStreamHandler:
    """
    Handles the WebSocket connection, bridging audio between Twilio and Gemini.
    Includes audio recording functionality for testing - records both input and output.
    """
    
    def __init__(self, websocket: WebSocket):
        """Initialize the handler with a WebSocket connection."""
        self.websocket = websocket
        self.gemini_client = None
        self.audio_converter = SimpleAudioConverter()
        self.stream_sid = None
        self.call_sid = None
        self.recording_enabled = True
        self.input_audio_file = None
        self.input_recording_file_path = None
        self.output_audio_file = None
        self.output_recording_file_path = None
        self.gemini_audio_chunks_received = 0
        self.total_gemini_audio_bytes = 0
        self.is_gemini_speaking = False
        self.call_summary = None

    async def handle_function_call(self, function_call):
        """Handle function calls from Gemini."""
        try:
            function_name = function_call.name
            args = function_call.args if hasattr(function_call, 'args') else {}
            
            logger.info(f"📞 Handling function call: {function_name}")
            logger.info(f"📋 Function arguments: {args}")
            
            if function_name == "summarize_call_outcome":
                # Extract and validate the call summary data
                call_summary_data = {
                    "call_transcript": args.get("call_transcript", ""),
                    "quote_obtained": args.get("quote_obtained", False),
                    "quote": args.get("quote"),
                    "visit_booked": args.get("visit_booked", False),
                    "visit_booked_date": args.get("visit_booked_date"),
                    "visit_time": args.get("visit_time"),
                    "trade_sentiment_analysis": args.get("trade_sentiment_analysis", "neutral")
                }
                
                # Create CallSummary object
                self.call_summary = CallSummary(**call_summary_data)
                
                logger.info("✅ Call summary captured:")
                logger.info(f"   📝 Transcript: {self.call_summary.call_transcript}")
                logger.info(f"   💰 Quote obtained: {self.call_summary.quote_obtained}")
                if self.call_summary.quote:
                    logger.info(f"   💷 Quote: {self.call_summary.quote}")
                logger.info(f"   📅 Visit booked: {self.call_summary.visit_booked}")
                if self.call_summary.visit_booked_date:
                    logger.info(f"   📆 Visit date: {self.call_summary.visit_booked_date}")
                if self.call_summary.visit_time:
                    logger.info(f"   ⏰ Visit time: {self.call_summary.visit_time}")
                logger.info(f"   😊 Sentiment: {self.call_summary.trade_sentiment_analysis}")
                
                # Send function response back to Gemini using the correct format
                if hasattr(self.gemini_client, 'session') and self.gemini_client.session:
                    # Create a FunctionResponse object according to Google's documentation
                    function_response = types.FunctionResponse(
                        id=function_call.id if hasattr(function_call, 'id') else None,
                        name=function_name,
                        response={
                            "status": "success", 
                            "message": "Call summary recorded successfully"
                            # For non-blocking functions, you can add scheduling:
                            # "scheduling": "INTERRUPT"  # or "WHEN_IDLE" or "SILENT"
                        }
                    )
                    
                    try:
                        # Use send_tool_response method as per documentation
                        await self.gemini_client.session.send_tool_response(
                            function_responses=[function_response]
                        )
                        logger.info("📤 Function response sent to Gemini using send_tool_response")
                    except Exception as e:
                        logger.error(f"Error sending function response to Gemini: {e}")
            else:
                logger.warning(f"Unknown function call: {function_name}")
                
        except Exception as e:
            logger.error(f"Error handling function call: {e}", exc_info=True)

    async def handle_stream(self):
        """
        Handles the entire lifecycle of the media stream.
        Connects to Gemini and starts two concurrent tasks for bidirectional streaming.
        """
        logger.info("📞 Starting media stream handler")
        
        try:
            # First, Twilio sends a 'connected' event
            logger.debug("Waiting for 'connected' message from Twilio...")
            connected_data = await self.websocket.receive_text()
            logger.debug(f"Received data: {connected_data[:200]}...")
            
            connected_message = json.loads(connected_data)
            if connected_message.get("event") != "connected":
                logger.error(f"Expected 'connected' event, but received '{connected_message.get('event')}'")
                return
            
            logger.debug(f"Connected event received - Protocol: {connected_message.get('protocol')}, Version: {connected_message.get('version')}")
            
            # Then Twilio sends the 'start' event with stream details
            logger.debug("Waiting for 'start' message from Twilio...")
            start_data = await self.websocket.receive_text()
            logger.debug(f"Received start data: {start_data[:200]}...")
            
            start_message = TwilioMessage.parse_raw(start_data)
            logger.debug(f"Parsed start message - Event: {start_message.event}")
            
            if start_message.event == "start":
                logger.info(f"📞 Call started - SID: {start_message.start.callSid}")
                self.call_sid = start_message.start.callSid  # Store for connection pool
            else:
                logger.error(f"Expected 'start' event, but received '{start_message.event}'")
                return

            self.stream_sid = start_message.start.streamSid
            
            # Initialize audio recording if enabled
            if self.recording_enabled:
                await self.setup_audio_recording()
            
            # Establish connection to Gemini using the new client
            if not await self.connect_to_gemini(start_message):
                logger.error("Failed to establish Gemini connection. Closing stream.")
                return
            gemini_receiver_task = asyncio.create_task(self.receive_from_gemini())

            # The lifetime of the call is primarily dictated by the Twilio WebSocket connection.
            # We await the Twilio receiver task. It will only complete when the user hangs up
            # or Twilio sends a 'stop' message.
            await self.receive_from_twilio()
            
            # Trigger call summary before closing
            logger.info("📞 Call ending - triggering summary")
            await self.trigger_call_summary()

            # Once the call is ending, we can safely cancel the Gemini listener task.
            if not gemini_receiver_task.done():
                gemini_receiver_task.cancel()
                try:
                    await gemini_receiver_task
                except asyncio.CancelledError:
                    pass
                
        except Exception as e:
            logger.error(f"Error in handle_stream: {e}", exc_info=True)
        finally:
            await self.cleanup()
            logger.info("📞 Call ended")

    async def setup_audio_recording(self):
        """Set up audio recording to files for testing purposes - both input and output."""
        try:
            # Create recordings directory if it doesn't exist
            recordings_dir = "recordings"
            os.makedirs(recordings_dir, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Setup input recording (from Twilio)
            self.input_recording_file_path = os.path.join(recordings_dir, f"twilio_input_{timestamp}.wav")
            self.input_audio_file = wave.open(self.input_recording_file_path, 'wb')
            self.input_audio_file.setnchannels(1)  # Mono
            self.input_audio_file.setsampwidth(2)  # 16-bit
            self.input_audio_file.setframerate(8000)  # 8kHz
            
            # Setup output recording (from Gemini)
            self.output_recording_file_path = os.path.join(recordings_dir, f"gemini_output_{timestamp}.wav")
            self.output_audio_file = wave.open(self.output_recording_file_path, 'wb')
            self.output_audio_file.setnchannels(1)  # Mono
            self.output_audio_file.setsampwidth(2)  # 16-bit
            self.output_audio_file.setframerate(24000)  # 24kHz (Gemini outputs at 24kHz)
            
            logger.debug(f"📼 Recording enabled: {timestamp}")
            
        except Exception as e:
            logger.error(f"Failed to setup audio recording: {e}")
            self.recording_enabled = False

    async def connect_to_gemini(self, start_message: TwilioMessage) -> bool:
        """Creates and connects to a new Gemini client."""
        try:
            logger.info("Creating new Gemini client...")
            
            # Create a new GeminiLiveClient with function call handler
            start_time = datetime.now()
            self.gemini_client = GeminiLiveClient(function_call_handler=self.handle_function_call)
            
            # Connect with system instructions
            success = await self.gemini_client.connect(system_instruction=DEFAULT_SYSTEM_INSTRUCTIONS)
            
            if success:
                return True
            else:
                logger.error("❌ Failed to connect to Gemini")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to connect to Gemini: {type(e).__name__}: {e}", exc_info=True)
            return False

    async def receive_from_twilio(self):
        """Receives audio from Twilio, upsamples it, and sends it to Gemini."""
        audio_chunks_received = 0
        total_audio_bytes = 0
        
        while True:
            try:
                data = await self.websocket.receive_text()
                message = TwilioMessage.parse_raw(data)

                if message.event == "media":
                    # Check if user is speaking while Gemini is speaking (interruption)
                    if self.is_gemini_speaking:
                        # The interruption is handled automatically by Gemini's VAD
                        self.is_gemini_speaking = False
                    
                    # Decode the mulaw audio from Twilio
                    audio_mulaw = base64.b64decode(message.media.payload)
                    audio_chunks_received += 1
                    total_audio_bytes += len(audio_mulaw)
                    
                    # Convert mulaw to PCM
                    audio_pcm = self.audio_converter.mulaw_to_pcm(audio_mulaw)
                    
                    # Record the original audio for comparison
                    if self.recording_enabled and self.input_audio_file:
                        try:
                            self.input_audio_file.writeframes(audio_pcm)
                        except Exception as e:
                            logger.error(f"Error writing input audio to file: {e}")
                    
                    # Simple upsampling from 8kHz to 16kHz
                    upsampled_audio = self.audio_converter.resample_audio(audio_pcm, from_rate=8000, to_rate=16000)
                    
                    # Forward the upsampled audio to Gemini
                    success = await self.gemini_client.send_audio_chunk(upsampled_audio, sample_rate=16000)
                    if not success:
                        logger.warning("Failed to send audio chunk to Gemini")
                    
                elif message.event == "stop":
                    logger.info("Received 'stop' from Twilio. Closing stream.")
                    break
                    
            except websockets.exceptions.ConnectionClosedOK:
                logger.info("Twilio WebSocket connection closed gracefully.")
                break
            except websockets.exceptions.ConnectionClosedError as e:
                logger.warning(f"Twilio WebSocket connection closed with error: {e}")
                break
            except json.JSONDecodeError as e:
                logger.warning(f"Ignoring non-JSON message from Twilio: {e}")
                continue
            except Exception as e:
                logger.error(f"An unexpected error occurred while receiving from Twilio: {e}", exc_info=True)
                continue
                
        logger.debug(f"Twilio listener stopped. Received {audio_chunks_received} audio chunks ({total_audio_bytes} bytes total)")

    async def receive_from_gemini(self):
        """Receives audio from Gemini and sends it back to Twilio."""
        try:
            while True:
                # The async for loop will run as long as the Gemini session is active
                # This outer while loop ensures we immediately start listening again for the next turn
                async for audio_chunk in self.gemini_client.receive_audio_responses():
                    # Mark that Gemini is speaking
                    self.is_gemini_speaking = True
                    
                    logger.debug(f"Received audio from Gemini: {len(audio_chunk)} bytes")
                    
                    # Record output audio from Gemini if enabled
                    if self.recording_enabled and self.output_audio_file:
                        try:
                            self.output_audio_file.writeframes(audio_chunk)
                            self.gemini_audio_chunks_received += 1
                            self.total_gemini_audio_bytes += len(audio_chunk)
                            # Don't log recording progress - it's too noisy
                        except Exception as e:
                            logger.error(f"Error writing output audio to file: {e}")
                    
                    # Convert Gemini's 24kHz audio to 8kHz for Twilio
                    downsampled_audio = self.audio_converter.resample_audio(
                        audio_chunk, from_rate=24000, to_rate=8000
                    )
                    
                    # Convert PCM to mulaw for Twilio
                    mulaw_audio = self.audio_converter.pcm_to_mulaw(downsampled_audio)
                    
                    # Send audio back to Twilio
                    media_message = {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {
                            "payload": base64.b64encode(mulaw_audio).decode('utf-8')
                        }
                    }
                    
                    await self.websocket.send_json(media_message)
                    # Don't log every audio packet sent - too noisy
                
                # Gemini finished speaking
                self.is_gemini_speaking = False
                
                # Small sleep to prevent high-CPU loop
                await asyncio.sleep(0.05)
                
        except asyncio.CancelledError:
            self.is_gemini_speaking = False
        except Exception as e:
            logger.error(f"Error in Gemini receiver: {e}", exc_info=True)
            self.is_gemini_speaking = False

    async def cleanup(self):
        """Cleans up resources."""
        # Log final call summary if available
        if self.call_summary:
            logger.info("=== FINAL CALL SUMMARY ===")
            logger.info(f"Transcript: {self.call_summary.call_transcript}")
            logger.info(f"Quote obtained: {self.call_summary.quote_obtained}")
            if self.call_summary.quote:
                logger.info(f"Quote: {self.call_summary.quote}")
            logger.info(f"Visit booked: {self.call_summary.visit_booked}")
            if self.call_summary.visit_booked_date:
                logger.info(f"Visit date: {self.call_summary.visit_booked_date}")
            if self.call_summary.visit_time:
                logger.info(f"Visit time: {self.call_summary.visit_time}")
            logger.info(f"Trade sentiment: {self.call_summary.trade_sentiment_analysis}")
            logger.info("=========================")
        
        # Close input audio recording file
        if self.recording_enabled and self.input_audio_file:
            try:
                self.input_audio_file.close()
                if self.input_recording_file_path and os.path.exists(self.input_recording_file_path):
                    file_size = os.path.getsize(self.input_recording_file_path)
                    duration_seconds = file_size / (8000 * 2)  # 8kHz, 16-bit
                    logger.debug(f"📼 Input recording: {duration_seconds:.1f}s - {self.input_recording_file_path}")
                    
                    if file_size < 1000:  # Less than 1KB
                        logger.warning("⚠️ Very little input audio data received - check microphone/call setup")
            except Exception as e:
                logger.error(f"Error closing input audio recording file: {e}")
        
        # Close output audio recording file
        if self.recording_enabled and self.output_audio_file:
            try:
                self.output_audio_file.close()
                if self.output_recording_file_path and os.path.exists(self.output_recording_file_path):
                    file_size = os.path.getsize(self.output_recording_file_path)
                    duration_seconds = file_size / (24000 * 2)  # 24kHz, 16-bit
                    logger.debug(f"📼 Output recording: {duration_seconds:.1f}s - {self.output_recording_file_path}")
                    
                    if file_size < 1000:  # Less than 1KB
                        logger.warning("⚠️ No output audio data received from Gemini - check Gemini response")
            except Exception as e:
                logger.error(f"Error closing output audio recording file: {e}")
        
        # Close Gemini connection
        if self.gemini_client:
            try:
                await self.gemini_client.close()
            except Exception as e:
                logger.error(f"Error closing Gemini connection: {e}")
                
        # Close WebSocket
        try:
            await asyncio.wait_for(self.websocket.close(code=1000), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

    async def trigger_call_summary(self):
        """Explicitly trigger the call summary function before ending the call."""
        if not self.gemini_client or not self.gemini_client.session:
            return
            
        try:
            # Send a text message to trigger the function call
            await self.gemini_client.session.send_client_content(
                turns={
                    "parts": [{
                        "text": "The call is ending. Please summarize the call outcome now using the summarize_call_outcome function."
                    }]
                }
            )
            logger.info("📤 Sent trigger message for call summary")
            
            # Wait for the function call and response
            timeout = 5.0
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                if self.call_summary is not None:
                    logger.info("✅ Call summary received")
                    break
                await asyncio.sleep(0.1)
            else:
                logger.warning("⚠️ Timeout waiting for call summary")
            
        except Exception as e:
            logger.error(f"Error triggering call summary: {e}") 