"""
Test Gemini Client functionality
"""
import asyncio
import os
from services.gemini_client import GeminiLiveClient

async def test_gemini_connection():
    """Test connecting to Gemini Live API"""
    client = GeminiLiveClient()
    
    print("Testing Gemini connection...")
    connected = await client.connect()
    
    if connected:
        print("SUCCESS: Successfully connected to Gemini")
        await client.close()
        return True
    else:
        print("FAILED: Failed to connect to Gemini")
        print("   Make sure you have:")
        print("   1. Run 'gcloud auth application-default login'")
        print("   2. Have access to the Gemini model")
        return False

async def test_audio_streaming():
    """Test sending audio to Gemini and receiving response"""
    client = GeminiLiveClient()
    
    print("\nTesting audio streaming...")
    
    # Connect to Gemini
    if not await client.connect():
        print("FAILED: Failed to connect for audio test")
        return False
    
    try:
        # Create a simple test audio (silence)
        # 1 second of silence at 16kHz, 16-bit PCM
        sample_rate = 16000
        duration = 0.5
        num_samples = int(sample_rate * duration)
        silence = b'\x00\x00' * num_samples
        
        print(f"Sending {len(silence)} bytes of test audio...")
        sent = await client.send_audio_chunk(silence, sample_rate=sample_rate)
        
        if sent:
            print("SUCCESS: Audio sent successfully")
        else:
            print("FAILED: Failed to send audio")
            return False
        
        # Try to receive some responses
        print("Waiting for responses (3 second timeout)...")
        response_count = 0
        
        try:
            async with asyncio.timeout(3):
                async for audio_chunk in client.receive_audio_responses():
                    response_count += 1
                    print(f"Received audio chunk #{response_count}: {len(audio_chunk)} bytes")
                    
                    if response_count >= 2:
                        break
                        
        except asyncio.TimeoutError:
            print("Timeout reached (this is normal for silence input)")
        
        print(f"SUCCESS: Total audio chunks received: {response_count}")
        
        return True
        
    finally:
        await client.close()

async def test_custom_instructions():
    """Test connecting with custom system instructions"""
    client = GeminiLiveClient()
    
    print("\nTesting custom instructions...")
    
    custom_instructions = "You are a helpful assistant who responds briefly."
    connected = await client.connect(system_instruction=custom_instructions)
    
    if connected:
        print("SUCCESS: Connected with custom instructions")
        await client.close()
        return True
    else:
        print("FAILED: Failed to connect with custom instructions")
        return False

async def main():
    """Run all Gemini client tests"""
    print("Starting Gemini Client Tests\n")
    
    # Check if we have proper auth
    if not os.path.exists(os.path.expanduser("~/.config/gcloud/application_default_credentials.json")):
        print("WARNING: Google Cloud credentials not found!")
        print("   Run: gcloud auth application-default login")
        print("   Tests will likely fail without authentication.\n")
    
    tests = [
        ("Connection Test", test_gemini_connection),
        ("Custom Instructions Test", test_custom_instructions),
        ("Audio Streaming Test", test_audio_streaming)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running: {test_name}")
        print('='*50)
        
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"FAILED: Test failed with error: {type(e).__name__}: {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n\n{'='*50}")
    print("TEST SUMMARY")
    print('='*50)
    
    for test_name, passed in results:
        status = "SUCCESS: PASSED" if passed else "FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(passed for _, passed in results)
    if all_passed:
        print("\nSUCCESS: All Gemini client tests passed!")
    else:
        print("\nWARNING: Some tests failed!")
        print("\nCommon issues:")
        print("- Missing Google Cloud authentication")
        print("- No access to the Gemini model")
        print("- Network connectivity issues")

if __name__ == "__main__":
    asyncio.run(main()) 
