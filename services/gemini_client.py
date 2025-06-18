"""
Gemini Live API client for real-time audio streaming.
This module provides a standalone client that can be used for testing
and integration with various audio streaming services.
"""

import asyncio
import logging
import ssl
import os
from typing import Optional, AsyncGenerator, Dict, Any
from google import genai
from google.genai import types
from config import VERTEX_PROJECT_ID, VERTEX_LOCATION

logger = logging.getLogger(__name__)

class GeminiLiveClient:
    """
    A client for interacting with Google's Gemini Live API for real-time audio streaming.
    This class handles the connection, audio input/output, and session management.
    """
    
    def __init__(self, model_name: str = "gemini-live-2.5-flash-preview-native-audio"):
        self.model_name = model_name
        self.client = None
        self.session = None
        self._connected = False
        
        # Configure SSL context for macOS certificate issues
        self._setup_ssl_context()
    
    def _setup_ssl_context(self):
        """Setup SSL context to handle certificate verification issues on macOS"""
        try:
            # Create a default SSL context
            ssl_context = ssl.create_default_context()
            
            # Try to load system certificates
            try:
                ssl_context.load_default_certs()
                logger.debug("Loaded default SSL certificates")
            except Exception as e:
                logger.warning(f"Could not load default certificates: {e}")
            
            # Try to load certificate from certifi if available
            try:
                import certifi
                ssl_context.load_verify_locations(certifi.where())
                logger.debug("Loaded certifi certificates")
            except ImportError:
                logger.warning("certifi not available")
            except Exception as e:
                logger.warning(f"Could not load certifi certificates: {e}")
            
            # Set the SSL context in the environment for websockets
            # This is a workaround for the google-genai library
            os.environ['SSL_CERT_FILE'] = self._get_cert_file()
            os.environ['REQUESTS_CA_BUNDLE'] = self._get_cert_file()
            
            # Development SSL bypass option
            if os.getenv('DISABLE_SSL_VERIFY', '').lower() == 'true':
                logger.warning("⚠️  SSL verification disabled for development - NOT FOR PRODUCTION!")
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                # Also set for websockets
                import websockets
                if hasattr(websockets, 'client'):
                    websockets.client.ssl_context_for_client = lambda *args, **kwargs: ssl_context
            
        except Exception as e:
            logger.error(f"Error setting up SSL context: {e}")
    
    def _get_cert_file(self):
        """Get the certificate file path"""
        try:
            import certifi
            return certifi.where()
        except ImportError:
            # Fallback to system certificates
            return '/etc/ssl/certs/ca-certificates.crt'
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        
    async def connect(self, system_instruction: Optional[str] = None) -> bool:
        """
        Connect to the Gemini Live API.
        
        Args:
            system_instruction: Optional system instruction for the AI
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Initializing Gemini client for project {VERTEX_PROJECT_ID}")
            
            self.client = genai.Client(
                vertexai=True,
                project=VERTEX_PROJECT_ID,
                location=VERTEX_LOCATION,
                # http_options={"api_version": "v1alpha"}
            )
            
            # API docs here https://ai.google.dev/api/live
            config = {
                "response_modalities": ["AUDIO"],
                "enable_affective_dialog": True,
                "proactivity": {
                    "proactive_audio": False,
                },
                "realtime_input_config": {
                    "automatic_activity_detection": {
                        "disabled": False,
                        "start_of_speech_sensitivity": types.StartSensitivity.START_SENSITIVITY_HIGH,
                        "end_of_speech_sensitivity": types.EndSensitivity.END_SENSITIVITY_HIGH,
                        "prefix_padding_ms": 20,
                        "silence_duration_ms": 250,
                    }
                }
            }
            
            if system_instruction:
                config["system_instruction"] = system_instruction
                logger.info(f"Using system instruction: {system_instruction}")
            
            logger.info(f"Connecting to Gemini model: {self.model_name}")
            logger.info(f"Config: affective_dialog=True, proactive_audio=True, VAD=enabled")
            
            self._session_context = self.client.aio.live.connect(
                model=self.model_name, 
                config=config
            )
            
            self.session = await self._session_context.__aenter__()
            
            self._connected = True
            logger.info("✅ Successfully connected to Gemini Live API")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Gemini: {e}")
            self._connected = False
            return False
    
    async def send_audio_chunk(self, audio_data: bytes, sample_rate: int = 8000) -> bool:
        """
        Send an audio chunk to Gemini.
        
        Args:
            audio_data: Raw PCM audio data
            sample_rate: Sample rate of the audio (default 8000 for Twilio)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self._connected or not self.session:
            logger.error("Not connected to Gemini")
            return False
            
        try:
            await self.session.send_realtime_input(
                media={
                    "data": audio_data,
                    "mime_type": f"audio/pcm;rate={sample_rate}"
                }
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to send audio to Gemini: {e}")
            return False
    
    async def receive_audio_responses(self) -> AsyncGenerator[bytes, None]:
        """
        Receive audio responses from Gemini as an async generator.
        
        Yields:
            Audio data bytes from Gemini responses
        """
        if not self._connected or not self.session:
            logger.error("Not connected to Gemini")
            return
            
        try:
            logger.info("Starting to listen for Gemini responses...")
            response_count = 0
            
            async for response in self.session.receive():
                response_count += 1
                logger.debug(f"📨 Received response #{response_count} from Gemini")
                
                if not response.server_content:
                    logger.debug(f"Response #{response_count}: No server_content")
                    continue
                    
                server_content = response.server_content
                logger.debug(f"Response #{response_count}: Has server_content")
                
                # Handle interruptions
                if hasattr(server_content, "interrupted") and server_content.interrupted:
                    logger.info(f"🛑 Response #{response_count}: Gemini response was interrupted by user")
                    # Clear any pending audio when interrupted
                    continue
                
                # Log transcriptions if available
                if hasattr(server_content, 'user_content') and server_content.user_content:
                    if hasattr(server_content.user_content, 'turns') and server_content.user_content.turns:
                        for turn in server_content.user_content.turns:
                            if hasattr(turn, 'parts') and turn.parts:
                                for part in turn.parts:
                                    if hasattr(part, 'text') and part.text:
                                        logger.info(f"🎤 User said: {part.text}")
                
                # Log what we're getting
                if hasattr(server_content, 'model_turn') and server_content.model_turn:
                    logger.info(f"Response #{response_count}: Has model_turn with {len(server_content.model_turn.parts)} parts")
                    
                    # Process model turn with audio and text
                    for part_idx, part in enumerate(server_content.model_turn.parts):
                        logger.debug(f"Response #{response_count}, Part #{part_idx}: Processing part")
                        
                        # Check for text transcription
                        if hasattr(part, 'text') and part.text:
                            logger.info(f"🤖 Gemini says: {part.text}")
                        
                        # Check for audio data
                        if hasattr(part, 'inline_data') and part.inline_data and part.inline_data.data:
                            audio_chunk = part.inline_data.data
                            logger.info(f"🎵 Response #{response_count}, Part #{part_idx}: Found audio chunk: {len(audio_chunk)} bytes")
                            yield audio_chunk
                        else:
                            logger.debug(f"Response #{response_count}, Part #{part_idx}: No inline_data or audio data")
                else:
                    logger.debug(f"Response #{response_count}: No model_turn")
                
                # Log turn completion
                if hasattr(server_content, 'turn_complete') and server_content.turn_complete:
                    logger.info(f"Response #{response_count}: Gemini turn complete")
                    
                # Safety break to prevent infinite loops
                if response_count > 1000:
                    logger.warning("Received too many responses, breaking loop")
                    break
                    
        except Exception as e:
            logger.error(f"Error receiving from Gemini: {e}", exc_info=True)
    
    async def process_audio_file(self, audio_file_path: str, output_file_path: str = "gemini_output.wav") -> bool:
        """
        Process an audio file through Gemini and save the response.

        
        Args:
            audio_file_path: Path to input audio file
            output_file_path: Path to save Gemini's audio response
            
        Returns:
            True if processing successful, False otherwise
        """
        import wave
        import librosa
        import soundfile as sf
        import io
        
        try:
            logger.info(f"Processing audio file: {audio_file_path}")
            
            # Initialize client
            self.client = genai.Client(
                vertexai=True,
                project=VERTEX_PROJECT_ID,
                location=VERTEX_LOCATION,
                http_options={"api_version": "v1alpha"}
            )
            
            config = {
                "response_modalities": ["AUDIO"],
                "system_instruction": "You are a helpful assistant. When someone greets you, respond warmly and ask how their day is going."
            }
            
            # Load and convert audio to 16kHz PCM (like the working test)
            y, sr = librosa.load(audio_file_path, sr=16000)
            buffer = io.BytesIO()
            sf.write(buffer, y, sr, format='RAW', subtype='PCM_16')
            buffer.seek(0)
            audio_bytes = buffer.read()
            
            logger.info(f"Loaded {len(audio_bytes)} bytes of audio data")
            
            total_received = 0
            

            async with self.client.aio.live.connect(model=self.model_name, config=config) as session:
                logger.info("✅ Successfully connected to Gemini session!")
                
                # Create audio queue like the working test
                audio_queue = asyncio.Queue()
                
                # Split audio into chunks and add to queue
                chunk_size = 512
                for i in range(0, len(audio_bytes), chunk_size):
                    chunk = audio_bytes[i:i + chunk_size]
                    await audio_queue.put(chunk)
                
                # Prepare output file
                wf = wave.open(output_file_path, "wb")
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(24000)  # Gemini outputs 24kHz
                
                # Use TaskGroup for concurrent send/receive (like working test)
                async with asyncio.TaskGroup() as tg:
                    
                    async def send_audio():
                        """Send audio chunks to Gemini (like working test)"""
                        chunk_count = 0
                        while True:
                            try:
                                # Use timeout to prevent infinite waiting
                                chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
                                
                                await session.send_realtime_input(
                                    media={
                                        "data": chunk,
                                        "mime_type": "audio/pcm;rate=16000",
                                    }
                                )
                                chunk_count += 1
                                logger.debug(f"Sent chunk {chunk_count}: {len(chunk)} bytes")
                                
                                await asyncio.sleep(0.05)  # Same delay as working test
                                audio_queue.task_done()
                                
                            except asyncio.TimeoutError:
                                logger.info("✅ All audio chunks sent!")
                                break
                    
                    async def receive_audio():
                        """Receive audio responses from Gemini (like working test)"""
                        nonlocal total_received
                        response_count = 0
                        turn_complete_received = False
                        
                        try:
                            async for response in session.receive():
                                response_count += 1
                                logger.debug(f"Response #{response_count} received")
                                
                                server_content = response.server_content
                                
                                # Handle interruptions (like working test)
                                if hasattr(server_content, "interrupted") and server_content.interrupted:
                                    logger.info("Interruption detected - continuing")
                                    continue
                                
                                if server_content and server_content.model_turn:
                                    for part in server_content.model_turn.parts:
                                        if hasattr(part, 'inline_data') and part.inline_data:
                                            audio_chunk = part.inline_data.data
                                            wf.writeframes(audio_chunk)
                                            wf._file.flush()
                                            total_received += len(audio_chunk)
                                            logger.debug(f"Received audio chunk: {len(audio_chunk)} bytes")
                                
                                # Handle turn completion (like working test)
                                if server_content and server_content.turn_complete:
                                    logger.info("✅ Gemini done talking")
                                    turn_complete_received = True
                                
                                # Safety breaks (like working test)
                                if response_count > 100:
                                    logger.info("Many responses received, breaking loop")
                                    break
                                    
                                if turn_complete_received and response_count > 35:
                                    logger.info("Turn complete received and sufficient processing time elapsed")
                                    break
                                    
                        except Exception as e:
                            logger.error(f"Error during audio reception: {e}")
                    
                    # Start both tasks
                    tg.create_task(send_audio())
                    tg.create_task(receive_audio())
                
                # Close output file
                wf.close()
            
            if total_received > 0:
                logger.info(f"✅ SUCCESS! Received {total_received} bytes of audio response")
                logger.info(f"📁 Saved to: {output_file_path}")
                logger.info(f"🎵 Duration: ~{total_received / 48000:.1f} seconds")
                return True
            else:
                logger.warning("No audio response received from Gemini")
                return False
                
        except Exception as e:
            logger.error(f"Error processing audio file: {e}")
            return False
    
    async def close(self):
        """Close the Gemini session and cleanup resources."""
        if hasattr(self, '_session_context') and self._session_context:
            try:
                # Add timeout to prevent hanging
                await asyncio.wait_for(
                    self._session_context.__aexit__(None, None, None),
                    timeout=5.0  # 5 second timeout
                )
                logger.info("Gemini session closed")
            except asyncio.TimeoutError:
                logger.warning("Timeout while closing Gemini session - forcing cleanup")
            except Exception as e:
                logger.error(f"Error closing Gemini session: {e}")
        
        self._connected = False
        self.session = None 