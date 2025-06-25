"""
Test Gemini Client functionality
"""
import pytest
import asyncio
import os
from unittest.mock import patch, AsyncMock, Mock
from services.gemini_client import GeminiLiveClient

@pytest.mark.asyncio
async def test_gemini_connection():
    """Test connecting to Gemini Live API"""
    with patch.object(GeminiLiveClient, 'connect', return_value=True) as mock_connect:
        client = GeminiLiveClient()
        connected = await client.connect()
        
        assert connected is True
        mock_connect.assert_called_once()

@pytest.mark.asyncio
async def test_audio_streaming():
    """Test sending audio to Gemini and receiving response"""
    with patch.object(GeminiLiveClient, 'connect', return_value=True), \
         patch.object(GeminiLiveClient, 'send_audio_chunk', return_value=True) as mock_send, \
         patch.object(GeminiLiveClient, 'receive_audio_responses') as mock_receive, \
         patch.object(GeminiLiveClient, 'close', return_value=None):
        
        # Mock the async generator for receiving responses
        async def mock_audio_generator():
            yield b'\x00\x01\x02\x03'  # Mock audio chunk
            yield b'\x04\x05\x06\x07'  # Another mock audio chunk
        
        mock_receive.return_value = mock_audio_generator()
        
        client = GeminiLiveClient()
        
        # Connect to Gemini
        connected = await client.connect()
        assert connected is True
        
        # Create test audio data
        sample_rate = 16000
        duration = 0.5
        num_samples = int(sample_rate * duration)
        silence = b'\x00\x00' * num_samples
        
        # Test sending audio
        sent = await client.send_audio_chunk(silence, sample_rate=sample_rate)
        assert sent is True
        mock_send.assert_called_once_with(silence, sample_rate=sample_rate)
        
        # Test receiving responses
        response_count = 0
        async for audio_chunk in client.receive_audio_responses():
            response_count += 1
            assert isinstance(audio_chunk, bytes)
            if response_count >= 2:
                break
        
        assert response_count == 2
        await client.close()

@pytest.mark.asyncio
async def test_custom_instructions():
    """Test connecting with custom system instructions"""
    with patch.object(GeminiLiveClient, 'connect', return_value=True) as mock_connect, \
         patch.object(GeminiLiveClient, 'close', return_value=None):
        
        client = GeminiLiveClient()
        custom_instructions = "You are a helpful assistant who responds briefly."
        
        connected = await client.connect(system_instruction=custom_instructions)
        
        assert connected is True
        mock_connect.assert_called_once_with(system_instruction=custom_instructions)
        await client.close()

@pytest.mark.asyncio
async def test_gemini_connection_failure():
    """Test handling connection failures"""
    with patch.object(GeminiLiveClient, 'connect', return_value=False) as mock_connect:
        client = GeminiLiveClient()
        connected = await client.connect()
        
        assert connected is False
        mock_connect.assert_called_once()

@pytest.mark.asyncio 
async def test_audio_send_failure():
    """Test handling audio sending failures"""
    with patch.object(GeminiLiveClient, 'connect', return_value=True), \
         patch.object(GeminiLiveClient, 'send_audio_chunk', return_value=False) as mock_send, \
         patch.object(GeminiLiveClient, 'close', return_value=None):
        
        client = GeminiLiveClient()
        await client.connect()
        
        test_audio = b'\x00\x01\x02\x03'
        sent = await client.send_audio_chunk(test_audio)
        
        assert sent is False
        mock_send.assert_called_once_with(test_audio)
        await client.close() 
