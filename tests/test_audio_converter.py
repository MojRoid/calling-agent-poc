"""
Test Audio Converter functionality
"""
import numpy as np
from services.audio_converter_simple import SimpleAudioConverter

def test_mulaw_to_pcm_conversion():
    """Test mulaw to PCM conversion"""
    converter = SimpleAudioConverter()
    
    print("Testing mulaw to PCM conversion...")
    
    # Create test mulaw data
    mulaw_data = bytes([0xFF, 0x7F, 0xEF, 0x6F, 0xE7, 0x67])
    
    # Convert to PCM
    pcm_data = converter.mulaw_to_pcm(mulaw_data)
    
    # Verify conversion
    assert len(pcm_data) == len(mulaw_data) * 2  # PCM is 16-bit
    assert isinstance(pcm_data, bytes)
    
    print(f"SUCCESS: Converted {len(mulaw_data)} mulaw bytes to {len(pcm_data)} PCM bytes")

def test_pcm_to_mulaw_conversion():
    """Test PCM to mulaw conversion"""
    converter = SimpleAudioConverter()
    
    print("Testing PCM to mulaw conversion...")
    
    # Create test PCM data (16-bit samples)
    pcm_samples = np.array([0, 1000, -1000, 5000, -5000, 10000], dtype=np.int16)
    pcm_data = pcm_samples.tobytes()
    
    # Convert to mulaw
    mulaw_data = converter.pcm_to_mulaw(pcm_data)
    
    # Verify conversion
    assert len(mulaw_data) == len(pcm_samples)
    assert isinstance(mulaw_data, bytes)
    
    print(f"SUCCESS: Converted {len(pcm_data)} PCM bytes to {len(mulaw_data)} mulaw bytes")

def test_round_trip_conversion():
    """Test round-trip conversion (PCM -> mulaw -> PCM)"""
    converter = SimpleAudioConverter()
    
    print("Testing round-trip conversion...")
    
    # Create test PCM data
    original_samples = np.array([0, 500, -500, 2000, -2000, 8000, -8000], dtype=np.int16)
    original_data = original_samples.tobytes()
    
    # Convert PCM -> mulaw -> PCM
    mulaw_data = converter.pcm_to_mulaw(original_data)
    recovered_data = converter.mulaw_to_pcm(mulaw_data)
    
    # Convert back to numpy for comparison
    recovered_samples = np.frombuffer(recovered_data, dtype=np.int16)
    
    # mulaw is lossy, so we check if values are close
    max_error = np.max(np.abs(original_samples - recovered_samples))
    avg_error = np.mean(np.abs(original_samples - recovered_samples))
    
    print(f"Stats: Max error: {max_error}, Avg error: {avg_error:.2f}")
    
    # mulaw typically has some quantization error
    assert max_error < 5000  # Reasonable error threshold for mulaw
    print("SUCCESS: Round-trip conversion successful with acceptable error")

def test_audio_resampling():
    """Test audio resampling"""
    converter = SimpleAudioConverter()
    
    print("Testing audio resampling...")
    
    # Create test audio at 8kHz
    duration = 0.1  # 100ms
    sample_rate = 8000
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # Generate a 440Hz sine wave
    frequency = 440
    audio_samples = (np.sin(2 * np.pi * frequency * t) * 5000).astype(np.int16)
    audio_data = audio_samples.tobytes()
    
    # Resample from 8kHz to 16kHz
    resampled_data = converter.resample_audio(audio_data, 8000, 16000)
    
    # Verify
    resampled_samples = np.frombuffer(resampled_data, dtype=np.int16)
    expected_length = len(audio_samples) * 2  # Doubling sample rate
    
    print(f"Stats: Original: {len(audio_samples)} samples, Resampled: {len(resampled_samples)} samples")
    assert abs(len(resampled_samples) - expected_length) < 10  # Allow small difference
    
    print("SUCCESS: Audio resampling successful")

if __name__ == "__main__":
    # Run tests manually
    test_mulaw_to_pcm_conversion()
    test_pcm_to_mulaw_conversion() 
    test_round_trip_conversion()
    test_audio_resampling()
    print("All audio converter tests passed!") 
