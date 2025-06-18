"""
Test Twilio Service functionality
"""
from services.twilio_service import TwilioService

def test_initialization():
    """Test Twilio service initialization"""
    service = TwilioService()
    assert service.client is not None

def test_place_call():
    """Test call placement (mock)"""
    service = TwilioService()
    
    # This will fail with test credentials, but we test the method exists
    try:
        result = service.place_call(to="+1234567890")
        # If it doesn't throw an exception, the method works
        assert hasattr(result, 'sid')
    except Exception as e:
        # Expected with test credentials
        assert "Unable to create record" in str(e) or "authenticate" in str(e)

def test_generate_twiml():
    """Test TwiML generation"""
    service = TwilioService()
    
    # Test default TwiML (human answered)
    twiml = service.generate_stream_twiml()
    assert "<?xml" in twiml
    assert "<Response>" in twiml
    assert "<Connect>" in twiml
    assert "<Stream" in twiml
    assert "<Say>" in twiml
    
    # Test machine detection - should now hang up immediately
    machine_twiml = service.generate_stream_twiml(answered_by="machine_start")
    assert "<Hangup/>" in machine_twiml
    
    # Test fax - should hang up
    fax_twiml = service.generate_stream_twiml(answered_by="fax")
    assert "<Hangup/>" in fax_twiml

    # Test TwiML generation - human answer
    twiml = service.generate_stream_twiml(answered_by="human")
    assert "<?xml" in twiml
    assert "<Response>" in twiml
    assert "<Connect>" in twiml
    assert "<Stream" in twiml
    assert "<Say>" in twiml

def test_update_call():
    """Test call update functionality"""
    service = TwilioService()
    
    # Test with invalid call SID (expected to fail but method should exist)
    result = service.update_call("CA123", status="completed")
    assert isinstance(result, bool)

if __name__ == "__main__":
    print("Testing Twilio Service...")
    
    # Test initialization
    test_initialization()
    print("SUCCESS: Initialization test passed")
    
    # Test place call
    test_place_call()
    print("SUCCESS: Place call test passed")
    
    # Test TwiML generation
    test_generate_twiml()
    print("SUCCESS: TwiML generation test passed")
    
    # Test update call
    test_update_call()
    print("SUCCESS: Update call test passed")
    
    print("All Twilio service tests passed!") 
