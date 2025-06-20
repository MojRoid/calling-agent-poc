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
from models import TwilioMessage
from config import DEFAULT_SYSTEM_INSTRUCTIONS

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

    async def handle_stream(self):
        """
        Handles the entire lifecycle of the media stream.
        Connects to Gemini and starts two concurrent tasks for bidirectional streaming.
        """
        logger.info("=== Starting media stream handler ===")
        logger.info(f"WebSocket client: {self.websocket.client}")
        
        try:
            # First, Twilio sends a 'connected' event
            logger.info("Waiting for 'connected' message from Twilio...")
            connected_data = await self.websocket.receive_text()
            logger.info(f"Received data: {connected_data[:200]}...")
            
            connected_message = json.loads(connected_data)
            if connected_message.get("event") != "connected":
                logger.error(f"Expected 'connected' event, but received '{connected_message.get('event')}'")
                return
            
            logger.info(f"Connected event received - Protocol: {connected_message.get('protocol')}, Version: {connected_message.get('version')}")
            
            # Then Twilio sends the 'start' event with stream details
            logger.info("Waiting for 'start' message from Twilio...")
            start_data = await self.websocket.receive_text()
            logger.info(f"Received start data: {start_data[:200]}...")
            
            start_message = TwilioMessage.parse_raw(start_data)
            logger.info(f"Parsed start message - Event: {start_message.event}")
            
            if start_message.event == "start":
                logger.info(f"Stream SID: {start_message.start.streamSid}")
                logger.info(f"Account SID: {start_message.start.accountSid}")
                logger.info(f"Call SID: {start_message.start.callSid}")
                logger.info(f"Custom Parameters: {start_message.start.customParameters}")
                self.call_sid = start_message.start.callSid  # Store for connection pool
            else:
                logger.error(f"Expected 'start' event, but received '{start_message.event}'")
                return

            self.stream_sid = start_message.start.streamSid
            
            # Initialize audio recording if enabled
            if self.recording_enabled:
                await self.setup_audio_recording()
            
            # Establish connection to Gemini using the new client
            logger.info("Attempting to connect to Gemini...")
            if not await self.connect_to_gemini(start_message):
                logger.error("Failed to establish Gemini connection. Closing stream.")
                return

            # Start concurrent tasks for bidirectional streaming
            logger.info("Starting bidirectional streaming tasks...")
            gemini_receiver_task = asyncio.create_task(self.receive_from_gemini())

            # The lifetime of the call is primarily dictated by the Twilio WebSocket connection.
            # We await the Twilio receiver task. It will only complete when the user hangs up
            # or Twilio sends a 'stop' message.
            await self.receive_from_twilio()

            logger.info("Twilio listener has stopped. The call is ending.")

            # Once the call is ending, we can safely cancel the Gemini listener task.
            if not gemini_receiver_task.done():
                logger.info("Cancelling Gemini listener task...")
                gemini_receiver_task.cancel()
                try:
                    await gemini_receiver_task
                except asyncio.CancelledError:
                    logger.info("Gemini listener task successfully cancelled.")
                
        except Exception as e:
            logger.error(f"Error in handle_stream: {e}", exc_info=True)
        finally:
            await self.cleanup()
            logger.info("=== Media stream handler completed ===")

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
            
            logger.info(f"📼 Audio recording enabled:")
            logger.info(f"   📥 Input (Twilio): {self.input_recording_file_path}")
            logger.info(f"   📤 Output (Gemini): {self.output_recording_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to setup audio recording: {e}")
            self.recording_enabled = False

    async def connect_to_gemini(self, start_message: TwilioMessage) -> bool:
        """Creates and connects to a new Gemini client."""
        try:
            logger.info("Creating new Gemini client...")
            
            # Create a new GeminiLiveClient
            start_time = datetime.now()
            self.gemini_client = GeminiLiveClient()
            
            # Connect with system instructions
            success = await self.gemini_client.connect(system_instruction=DEFAULT_SYSTEM_INSTRUCTIONS)
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if success:
                logger.info(f"✅ Successfully connected to Gemini in {elapsed:.2f}s")
                return True
            else:
                logger.error("❌ Failed to connect to Gemini")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to connect to Gemini: {type(e).__name__}: {e}", exc_info=True)
            return False

    async def receive_from_twilio(self):
        """Receives audio from Twilio, upsamples it, and sends it to Gemini."""
        logger.info("Listening for audio from Twilio...")
        audio_chunks_received = 0
        total_audio_bytes = 0
        
        while True:
            try:
                data = await self.websocket.receive_text()
                message = TwilioMessage.parse_raw(data)

                if message.event == "media":
                    # Check if user is speaking while Gemini is speaking (interruption)
                    if self.is_gemini_speaking:
                        logger.info("🛑 User interrupted Gemini - sending interruption signal")
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
                            if audio_chunks_received % 50 == 0:
                                logger.info(f"📼 Recorded {audio_chunks_received} input audio chunks ({total_audio_bytes} bytes total)")
                        except Exception as e:
                            logger.error(f"Error writing input audio to file: {e}")
                    
                    # Simple upsampling from 8kHz to 16kHz
                    upsampled_audio = self.audio_converter.resample_audio(audio_pcm, from_rate=8000, to_rate=16000)
                    
                    # Forward the upsampled audio to Gemini
                    success = await self.gemini_client.send_audio_chunk(upsampled_audio, sample_rate=16000)
                    if not success:
                        logger.warning("Failed to send audio chunk to Gemini")
                    else:
                        logger.debug(f"Forwarding {len(upsampled_audio)} bytes of 16kHz audio to Gemini.")
                    
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
                
        logger.info(f"Twilio listener stopped. Received {audio_chunks_received} audio chunks ({total_audio_bytes} bytes total)")

    async def receive_from_gemini(self):
        """Receives audio from Gemini and sends it back to Twilio."""
        logger.info("Listening for audio from Gemini...")
        
        try:
            while True:
                # The async for loop will run as long as the Gemini session is active
                # This outer while loop ensures we immediately start listening again for the next turn
                async for audio_chunk in self.gemini_client.receive_audio_responses():
                    # Mark that Gemini is speaking
                    self.is_gemini_speaking = True
                    
                    logger.info(f"Received audio from Gemini: {len(audio_chunk)} bytes, processing...")
                    
                    # Record output audio from Gemini if enabled
                    if self.recording_enabled and self.output_audio_file:
                        try:
                            self.output_audio_file.writeframes(audio_chunk)
                            self.gemini_audio_chunks_received += 1
                            self.total_gemini_audio_bytes += len(audio_chunk)
                            logger.info(f"📼 Recorded Gemini output chunk #{self.gemini_audio_chunks_received}: {len(audio_chunk)} bytes (total: {self.total_gemini_audio_bytes} bytes)")
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
                    logger.debug(f"Sent {len(mulaw_audio)} bytes back to Twilio.")
                    logger.info(f"Sent {len(mulaw_audio)} bytes of audio back to Twilio")
                
                # Gemini finished speaking
                self.is_gemini_speaking = False
                logger.info("Gemini response stream finished a turn. Looping to listen for the next one.")
                
                # Small sleep to prevent high-CPU loop
                await asyncio.sleep(0.05)
                
        except asyncio.CancelledError:
            logger.info("Gemini listener task cancelled as the call is ending.")
            self.is_gemini_speaking = False
        except Exception as e:
            logger.error(f"Error in Gemini receiver: {e}", exc_info=True)
            self.is_gemini_speaking = False
        finally:
            logger.info("Gemini listener has stopped.")

    async def cleanup(self):
        """Cleans up resources."""
        logger.info("Cleaning up resources...")
        
        # Close input audio recording file
        if self.recording_enabled and self.input_audio_file:
            try:
                self.input_audio_file.close()
                if self.input_recording_file_path and os.path.exists(self.input_recording_file_path):
                    file_size = os.path.getsize(self.input_recording_file_path)
                    duration_seconds = file_size / (8000 * 2)  # 8kHz, 16-bit
                    logger.info(f"📼 Input audio recording saved: {self.input_recording_file_path}")
                    logger.info(f"📊 Input recording stats: {file_size} bytes, ~{duration_seconds:.1f} seconds")
                    
                    if file_size > 1000:  # At least 1KB
                        logger.info("✅ Input audio was successfully received from Twilio!")
                    else:
                        logger.warning("⚠️ Very little input audio data received - check microphone/call setup")
                else:
                    logger.warning("⚠️ No input audio recording file found")
            except Exception as e:
                logger.error(f"Error closing input audio recording file: {e}")
        
        # Close output audio recording file
        if self.recording_enabled and self.output_audio_file:
            try:
                self.output_audio_file.close()
                if self.output_recording_file_path and os.path.exists(self.output_recording_file_path):
                    file_size = os.path.getsize(self.output_recording_file_path)
                    duration_seconds = file_size / (24000 * 2)  # 24kHz, 16-bit
                    logger.info(f"📼 Output audio recording saved: {self.output_recording_file_path}")
                    logger.info(f"📊 Output recording stats: {file_size} bytes, ~{duration_seconds:.1f} seconds")
                    
                    if file_size > 1000:  # At least 1KB
                        logger.info("✅ Output audio was successfully received from Gemini!")
                    else:
                        logger.warning("⚠️ No output audio data received from Gemini - check Gemini response")
                else:
                    logger.warning("⚠️ No output audio recording file found")
            except Exception as e:
                logger.error(f"Error closing output audio recording file: {e}")
        
        # Close Gemini connection
        if self.gemini_client:
            try:
                await self.gemini_client.close()
                logger.info("Gemini connection closed.")
            except Exception as e:
                logger.error(f"Error closing Gemini connection: {e}")
                
        # Close WebSocket
        try:
            await asyncio.wait_for(self.websocket.close(code=1000), timeout=5.0)
            logger.info("WebSocket connection closed.")
        except asyncio.TimeoutError:
            logger.warning("Timeout while closing WebSocket - connection may already be closed")
        except Exception:
            pass 