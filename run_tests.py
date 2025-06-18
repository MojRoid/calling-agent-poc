"""
Run all tests for the Calling Agent Service
"""
import subprocess
import sys
import time
import os
import requests

def run_test(test_name, test_command):
    """Run a single test"""
    print(f"\n{'='*60}")
    print(f"Running: {test_name}")
    print('='*60)
    
    try:
        # Set environment to include current directory in Python path
        env = os.environ.copy()
        env['PYTHONPATH'] = os.getcwd()
        
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            env=env
        )
        
        if result.returncode == 0:
            print(result.stdout)
            print(f"SUCCESS: {test_name} PASSED")
            return True
        else:
            print(result.stdout)
            print(result.stderr)
            print(f"FAILED: {test_name} FAILED")
            return False
            
    except Exception as e:
        print(f"ERROR: Error running {test_name}: {e}")
        return False

def main():
    """Run all tests"""
    print("Starting Comprehensive Test Suite")
    print("="*60)
    
    # Define tests using module syntax
    tests = [
        ("Audio Converter Tests", "python -m tests.test_audio_converter"),
        ("Twilio Service Tests", "python -m tests.test_twilio_service"),
        ("Gemini Client Tests", "python -m tests.test_gemini_client"),
    ]
    
    # Run tests
    results = []
    for test_name, test_command in tests:
        passed = run_test(test_name, test_command)
        results.append((test_name, passed))
        time.sleep(1)  # Small delay between tests
    
    # Check if server tests should be run
    print(f"\n{'='*60}")
    print("Server Integration Tests")
    print('='*60)
    
    # Try to start the server for API tests
    server_process = None
    try:
        print("Starting server for API tests...")
        # Set environment for server too
        env = os.environ.copy()
        env['PYTHONPATH'] = os.getcwd()
        
        server_process = subprocess.Popen(
            ["python", "app.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        
        # Wait for server to start by polling health check
        server_ready = False
        max_retries = 15
        for i in range(max_retries):
            try:
                print(f"Waiting for server... (attempt {i+1}/{max_retries})")
                response = requests.get("http://localhost:8080/health", timeout=1)
                if response.status_code == 200:
                    print("✅ Server is up and running!")
                    server_ready = True
                    break
            except requests.ConnectionError:
                time.sleep(1)
            except Exception as e:
                print(f"Health check failed with unexpected error: {e}")
                time.sleep(1)

        if not server_ready:
            print("❌ Server did not start in time. Aborting API tests.")
            results.append(("API Endpoint Tests", False))
        else:
            # Run API tests
            api_test_passed = run_test(
                "API Endpoint Tests",
                "python -m tests.test_api_endpoints"
            )
            results.append(("API Endpoint Tests", api_test_passed))
        
    except Exception as e:
        print(f"ERROR: Error with server tests: {e}")
        results.append(("API Endpoint Tests", False))
    finally:
        if server_process:
            print("\nStopping test server...")
            server_process.terminate()
            time.sleep(2)
    
    # Final summary
    print(f"\n\n{'='*60}")
    print("FINAL TEST SUMMARY")
    print('='*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)
    
    for test_name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\nSUCCESS: ALL TESTS PASSED! The service is ready to use!")
        print("\nTo place a test call:")
        print('curl -X POST http://localhost:8080/place-call \\')
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"to": "+1234567890"}\'')
    else:
        print("\nWARNING: Some tests failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main() 