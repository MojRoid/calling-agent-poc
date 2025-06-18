#!/usr/bin/env python3
"""
Script to place a test call to verify the calling agent works
"""
import requests
import json
import time
import sys
from config import TEST_PHONE_NUMBER

BASE_URL = "http://localhost:8080"

def check_server_health():
    """Check if the server is running"""
    try:
        # Try root endpoint first
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print("✓ Server is healthy and running")
            print(f"  Server response: {response.json()}")
            
            # Also try health endpoint if available
            try:
                health_response = requests.get(f"{BASE_URL}/health", timeout=5)
                if health_response.status_code == 200:
                    print(f"  Health check: {health_response.json()}")
            except:
                pass  # Health endpoint might not be available
            
            return True
        else:
            print(f"✗ Server health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Cannot connect to server: {e}")
        return False

def place_test_call():
    """Place a test call."""
    if not TEST_PHONE_NUMBER:
        print("✗ No test phone number configured in .env file")
        print("  Please set TEST_PHONE_NUMBER in your .env file")
        return False
        
    print(f"\n📞 Placing test call to {TEST_PHONE_NUMBER}...")
    
    call_data = {
        "to": TEST_PHONE_NUMBER
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/place-call",
            json=call_data,
            timeout=30
        )
        
        print(f"📊 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✓ Call placed successfully!")
            print(f"  Call SID: {result['callSid']}")
            print(f"  Status: {result['status']}")
            return True
        else:
            print(f"✗ Call failed with status {response.status_code}")
            print(f"  Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Error placing call: {e}")
        return False

def main():
    """Main function"""
    print("🚀 Starting Test Call Process")
    print("=" * 50)
    
    if not check_server_health():
        print("\n❌ Server is not ready. Please start the server first.")
        sys.exit(1)

    # Place the test call
    success = place_test_call()
    
    if success:
        print("\n" + "=" * 50)
        print("✅ TEST CALL INITIATED SUCCESSFULLY")
        print("=" * 50)
        print("📱 Your phone should be ringing now!")
    else:
        print("\n❌ Test call failed. Check the server logs for details.")
        sys.exit(1)

if __name__ == "__main__":
    main() 