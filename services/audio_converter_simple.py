import numpy as np
import logging
import audioop
from scipy import signal

logger = logging.getLogger(__name__)

class SimpleAudioConverter:
    """
    Simplified audio converter using Python's built-in audioop for cleaner MULAW decoding.
    Removes all audio enhancements to focus on clean, direct conversion.
    """
    
    def __init__(self):
        """Initialize simple audio converter"""
        pass
        
    def mulaw_to_pcm(self, mulaw_data: bytes) -> bytes:
        """
        Convert μ-law encoded audio to 16-bit PCM using Python's audioop
        
        Args:
            mulaw_data: μ-law encoded audio bytes
            
        Returns:
            PCM encoded audio bytes (16-bit, 8kHz)
        """
        try:
            if not mulaw_data:
                return b''
            
            # Use audioop's built-in mulaw to linear conversion
            # audioop.ulaw2lin converts μ-law to linear PCM
            # The second parameter (2) indicates we want 16-bit output
            pcm_data = audioop.ulaw2lin(mulaw_data, 2)
            
            return pcm_data
            
        except Exception as e:
            logger.error(f"Error converting μ-law to PCM with audioop: {e}")
            # Fallback to manual conversion if audioop fails
            return self.mulaw_to_pcm_fallback(mulaw_data)
    
    def mulaw_to_pcm_fallback(self, mulaw_data: bytes) -> bytes:
        """
        Fallback μ-law to PCM conversion if audioop fails
        """
        try:
            if not mulaw_data:
                return b''
                
            # Simple μ-law to linear conversion
            mulaw_array = np.frombuffer(mulaw_data, dtype=np.uint8)
            pcm_array = np.zeros(len(mulaw_array), dtype=np.int16)
            
            # μ-law decoding table
            exp_lut = [0, 132, 396, 924, 1980, 4092, 8316, 16764]
            
            for i, mulaw_val in enumerate(mulaw_array):
                # ITU-T G.711 standard
                mulaw_val = ~mulaw_val
                sign = (mulaw_val & 0x80)
                exponent = (mulaw_val >> 4) & 0x07
                mantissa = mulaw_val & 0x0F
                
                sample = exp_lut[exponent] + (mantissa << (exponent + 3))
                
                if sign != 0:
                    sample = -sample
                    
                pcm_array[i] = sample
            
            return pcm_array.tobytes()
            
        except Exception as e:
            logger.error(f"Error in fallback μ-law to PCM conversion: {e}")
            return b''
    
    def pcm_to_mulaw(self, pcm_data: bytes) -> bytes:
        """
        Convert 16-bit PCM audio to μ-law encoding using audioop
        """
        try:
            if not pcm_data:
                return b''
            
            # Use audioop's built-in linear to mulaw conversion
            # audioop.lin2ulaw converts linear PCM to μ-law
            # The second parameter (2) indicates the input is 16-bit
            mulaw_data = audioop.lin2ulaw(pcm_data, 2)
            
            return mulaw_data
            
        except Exception as e:
            logger.error(f"Error converting PCM to μ-law with audioop: {e}")
            return b''
    
    def resample_audio(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """
        Simple resampling without any enhancements
        """
        try:
            if not audio_data or from_rate == to_rate:
                return audio_data
            
            # Use audioop's ratecv for resampling
            # Parameters: input_data, width_in_bytes, channels, input_rate, output_rate, state
            # Returns: (converted_data, state)
            converted_data, _ = audioop.ratecv(
                audio_data,
                2,  # 16-bit samples = 2 bytes
                1,  # mono
                from_rate,
                to_rate,
                None
            )
            
            return converted_data
            
        except Exception as e:
            logger.warning(f"audioop resampling failed, using scipy: {e}")
            
            # Fallback to scipy resampling if audioop fails
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            num_samples = int(len(audio_array) * to_rate / from_rate)
            resampled = signal.resample(audio_array, num_samples)
            
            # Convert back to int16 and clamp
            resampled = np.clip(resampled, -32768, 32767)
            resampled = np.round(resampled).astype(np.int16)
            
            return resampled.tobytes() 