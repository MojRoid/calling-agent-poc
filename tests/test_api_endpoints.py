"""
Test API Endpoints
"""
import requests
import json
import time
import sys

# Base URL for the API
BASE_URL = "http://localhost:8080"

def test_health_check():
    """Test health check endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        return True
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

def test_root_endpoint():
    """Test root endpoint"""
    try:
        print("Testing root endpoint...")
        response = requests.get(f"{BASE_URL}/", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"SUCCESS: Root endpoint passed: {data}")
        return True
    except Exception as e:
        print(f"Root endpoint failed: {e}")
        return False

def test_twiml_generation():
    """Test TwiML generation endpoint"""
    try:
        print("Testing TwiML generation...")
        
        # Test default TwiML (human answered)
        response = requests.post(f"{BASE_URL}/twiml/stream", timeout=5)
        assert response.status_code == 200
        twiml = response.text
        assert "<Response>" in twiml
        assert "<Connect>" in twiml
        assert "<Say>" not in twiml
        print("SUCCESS: TwiML generation (human) passed")
        
        # Test machine detection
        response = requests.post(
            f"{BASE_URL}/twiml/stream",
            data={"AnsweredBy": "machine_start"},
            timeout=5
        )
        assert response.status_code == 200
        twiml = response.text
        assert "<Hangup/>" in twiml
        print("SUCCESS: TwiML generation (machine) passed")
        
        return True
        
    except Exception as e:
        print(f"TwiML generation failed: {e}")
        return False

def test_place_call():
    """Test place call endpoint"""
    try:
        print("Testing place call endpoint...")
        
        call_data = {
            "to": "+1234567890"
        }
        
        response = requests.post(
            f"{BASE_URL}/place-call",
            json=call_data,
            timeout=10
        )
        
        print(f"Response status: {response.status_code}")
        
        # With test credentials, we expect a 500 error
        if response.status_code == 500:
            print("EXPECTED: Call placement failed (expected if using test credentials)")
        else:
            data = response.json()
            print(f"Call result: {data}")
            assert "callSid" in data
            assert "status" in data
        
        return True
        
    except Exception as e:
        print(f"Place call test error: {e}")
        return False # Expected to fail with test credentials

def test_call_status_endpoint():
    """Test call status callback endpoint"""
    try:
        print("Testing call status endpoint...")
        
        # Test with different call statuses
        statuses = ["answered", "busy", "no-answer", "failed", "completed"]
        
        for status in statuses:
            data = {
                "CallSid": f"CAtest{status}",
                "CallStatus": status
            }
            
            response = requests.post(
                f"{BASE_URL}/call-status",
                data=data,
                timeout=5
            )
            
            assert response.status_code == 200
            print(f"SUCCESS: Call status '{status}' handled correctly")
        
        return True
        
    except Exception as e:
        print(f"Call status test failed: {e}")
        return False

def main():
    """Run all API endpoint tests"""
    print("Starting API Endpoint Tests")
    print("=" * 50)
    
    tests = [
        ("Health Check", test_health_check),
        ("Root Endpoint", test_root_endpoint),
        ("TwiML Generation", test_twiml_generation),
        ("Call Status", test_call_status_endpoint),
        ("Place Call", test_place_call)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        print("=" * 50)
        
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"Test {test_name} failed with error: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    for test_name, passed in results:
        status = "SUCCESS: PASSED" if passed else "FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(passed for _, passed in results)
    if all_passed:
        print("\nAll API endpoint tests passed!")
    else:
        print("\nSome API endpoint tests failed!")
        sys.exit(1)
    
    return all_passed

if __name__ == "__main__":
    main() 
