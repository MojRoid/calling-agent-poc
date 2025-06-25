"""
Gemini Live API client for real-time audio streaming.
This module provides a standalone client that can be used for testing
and integration with various audio streaming services.
"""

import asyncio
import logging
import ssl
import os
import platform
from typing import Optional, AsyncGenerator, Dict, Any
from google import genai
from google.genai import types
from config import VERTEX_PROJECT_ID, VERTEX_LOCATION, GEMINI_MODEL

logger = logging.getLogger(__name__)

class GeminiLiveClient:
    """
    A client for interacting with Google's Gemini Live API for real-time audio streaming.
    This class handles the connection, audio input/output, and session management.
    """
    
    def __init__(self, model_name: str = None, function_call_handler=None):
        self.model_name = model_name or GEMINI_MODEL
        if not self.model_name:
            raise ValueError("GEMINI_MODEL not set in environment variables")
        self.client = None
        self.session = None
        self._connected = False
        self.function_call_handler = function_call_handler
        self.conversation_state = {
            "quote_mentioned": False,
            "visit_scheduled": False,
            "goodbyes_exchanged": False
        }
        
        # Configure SSL context for macOS certificate issues
        self._setup_ssl_context()
    
    def _setup_ssl_context(self):
        """Setup SSL context to handle certificate verification issues on macOS"""
        if platform.system() != "Darwin":
            return
            
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
            self.client = genai.Client(
                vertexai=True,
                project=VERTEX_PROJECT_ID,
                location=VERTEX_LOCATION
            )
            
            # API docs here https://ai.google.dev/api/live
            config = {
                "response_modalities": ["AUDIO"],
                "input_audio_transcription": {},
                "output_audio_transcription": {},
                "speech_config": {
                    "language_code": "en-US",
                    "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": "Kore"
                            }
                        }
                    },
                "enable_affective_dialog": True,
                "proactivity": {
                    "proactive_audio": False,
                },
                "realtime_input_config": {
                    "automatic_activity_detection": {
                        "disabled": False,
                        "start_of_speech_sensitivity": types.StartSensitivity.START_SENSITIVITY_LOW,
                        "end_of_speech_sensitivity": types.EndSensitivity.END_SENSITIVITY_LOW,
                        "prefix_padding_ms": 20,
                        "silence_duration_ms": 250,
                    }
                },
                "tools": [
                    {
                        "function_declarations": [
                            {
                                "name": "summarize_call_outcome",
                                "description": "Summarize the outcome of the call with the tradesperson",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "call_transcript": {
                                            "type": "string",
                                            "description": "A brief summary of the conversation that took place"
                                        },
                                        "quote_obtained": {
                                            "type": "boolean",
                                            "description": "True if a quote or price estimate was obtained"
                                        },
                                        "quote": {
                                            "type": "string",
                                            "description": "The actual quote amount/range if obtained, null if not"
                                        },
                                        "visit_booked": {
                                            "type": "boolean",
                                            "description": "True if an appointment or visit was scheduled"
                                        },
                                        "visit_booked_date": {
                                            "type": "string",
                                            "description": "The date of the visit if booked (format: YYYY-MM-DD), null if not"
                                        },
                                        "visit_time": {
                                            "type": "string",
                                            "description": "The time of the visit if specified (format: HH:MM), null if not"
                                        },
                                        "trade_sentiment_analysis": {
                                            "type": "string",
                                            "description": "Assessment of the tradesperson's attitude and sentiment during the call"
                                        }
                                    },
                                    "required": ["call_transcript", "quote_obtained", "visit_booked", "trade_sentiment_analysis"]
                                }
                                # Uncomment the following line to make this function non-blocking:
                                # , "behavior": "NON_BLOCKING"
                            }
                        ]
                    }
                ]
            }
            
            if system_instruction:
                config["system_instruction"] = system_instruction
            
            self._session_context = self.client.aio.live.connect(
                model=self.model_name, 
                config=config
            )
            
            self.session = await self._session_context.__aenter__()
            
            self._connected = True
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
            response_count = 0
            
            async for response in self.session.receive():
                response_count += 1
                # Only log every 20 responses to reduce noise
                if response_count % 20 == 0:
                    logger.debug(f"📨 Received response #{response_count} from Gemini")
                
                # Handle tool calls according to Google documentation
                if hasattr(response, 'tool_call') and response.tool_call:
                    logger.info(f"🔧 Tool call received")
                    if hasattr(response.tool_call, 'function_calls'):
                        for fc in response.tool_call.function_calls:
                            logger.info(f"🔧 Function call: {fc.name} with id: {fc.id}")
                            if self.function_call_handler:
                                try:
                                    await self.function_call_handler(fc)
                                except Exception as e:
                                    logger.error(f"Error handling function call: {e}")
                            else:
                                logger.warning("Function call received but no handler provided")
                    continue
                
                if not response.server_content:
                    if response_count % 20 == 0:
                        logger.debug(f"Response #{response_count}: No server_content")
                    continue
                    
                server_content = response.server_content
                if response_count % 20 == 0:
                    logger.debug(f"Response #{response_count}: Has server_content")
                
                # Handle interruptions
                if hasattr(server_content, "interrupted") and server_content.interrupted:
                    logger.info(f"🛑 Response #{response_count}: Gemini response was interrupted by user")
                    # Clear any pending audio when interrupted
                    continue
                
                # Log transcriptions
                if response.server_content.input_transcription:
                    user_text = response.server_content.input_transcription.text
                    logger.info(f"🎤 User said: {user_text}")
                    
                    # Check for goodbye patterns only if text is not None
                    if user_text:
                        goodbye_patterns = ["bye", "goodbye", "thanks", "thank you", "see you"]
                        if any(pattern in user_text.lower() for pattern in goodbye_patterns):
                            self.conversation_state["goodbyes_exchanged"] = True
                        
                if response.server_content.output_transcription:
                    ai_text = response.server_content.output_transcription.text
                    logger.info(f"🤖 Gemini says: {ai_text}")
                    
                    # Only process text if it's not None
                    if ai_text:
                        # Monitor for quote mentions
                        if any(word in ai_text.lower() for word in ["quote", "pound", "£", "cost", "price"]):
                            self.conversation_state["quote_mentioned"] = True
                        
                        # Monitor for visit scheduling
                        if any(word in ai_text.lower() for word in ["scheduled", "appointment", "visit", "saturday", "thursday"]):
                            self.conversation_state["visit_scheduled"] = True
                        
                        # Check if objectives are met and conversation might be ending
                        if (self.conversation_state["quote_mentioned"] and 
                            self.conversation_state["visit_scheduled"] and
                            self.conversation_state["goodbyes_exchanged"]):
                            logger.info("📊 Call objectives appear to be met - function should be called")
                
                # Process model turns silently unless there's speech
                if hasattr(server_content, 'model_turn') and server_content.model_turn:
                    # Process model turn with audio
                    for part_idx, part in enumerate(server_content.model_turn.parts):
                        # Check for audio data
                        if hasattr(part, 'inline_data') and part.inline_data and part.inline_data.data:
                            audio_chunk = part.inline_data.data
                            # Only log if we're debugging specific issues
                            logger.debug(f"🎵 Response #{response_count}, Part #{part_idx}: Found audio chunk: {len(audio_chunk)} bytes")
                            yield audio_chunk
                
                # Log turn completion
                if hasattr(server_content, 'turn_complete') and server_content.turn_complete:
                    logger.info(f"Response #{response_count}: Gemini turn complete")
                    
                # Safety break to prevent infinite loops
                if response_count > 1000:
                    logger.warning("Received too many responses, breaking loop")
                    break
                    
        except Exception as e:
            logger.error(f"Error receiving from Gemini: {e}", exc_info=True)
    
    async def close(self):
        """Close the Gemini session and cleanup resources."""
        if hasattr(self, '_session_context') and self._session_context:
            try:
                # Add timeout to prevent hanging
                await asyncio.wait_for(
                    self._session_context.__aexit__(None, None, None),
                    timeout=5.0  # 5 second timeout
                )
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Error closing Gemini session: {e}")
        
        self._connected = False
        self.session = None 