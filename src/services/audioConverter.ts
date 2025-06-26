import { createLogger } from '../utils/logger';

const logger = createLogger('audioConverter');

export class SimpleAudioConverter {
  /**
   * Convert μ-law encoded audio to 16-bit PCM
   * @param mulawData μ-law encoded audio bytes
   * @returns PCM encoded audio bytes (16-bit)
   */
  mulawToPcm(mulawData: Buffer): Buffer {
    try {
      if (!mulawData || mulawData.length === 0) {
        return Buffer.alloc(0);
      }

      const pcmData = Buffer.alloc(mulawData.length * 2);
      
      // μ-law decoding table
      const expLut = [0, 132, 396, 924, 1980, 4092, 8316, 16764];
      
      for (let i = 0; i < mulawData.length; i++) {
        let mulawVal = mulawData[i];
        
        // ITU-T G.711 standard
        mulawVal = ~mulawVal;
        const sign = (mulawVal & 0x80);
        const exponent = (mulawVal >> 4) & 0x07;
        const mantissa = mulawVal & 0x0F;
        
        let sample = expLut[exponent] + (mantissa << (exponent + 3));
        
        if (sign !== 0) {
          sample = -sample;
        }
        
        // Write as little-endian 16-bit PCM
        pcmData.writeInt16LE(sample, i * 2);
      }
      
      return pcmData;
    } catch (error) {
      logger.error(`Error converting μ-law to PCM: ${error}`);
      return Buffer.alloc(0);
    }
  }

  /**
   * Convert 16-bit PCM audio to μ-law encoding
   * @param pcmData PCM audio data
   * @returns μ-law encoded audio
   */
  pcmToMulaw(pcmData: Buffer): Buffer {
    try {
      if (!pcmData || pcmData.length === 0) {
        return Buffer.alloc(0);
      }

      const numSamples = pcmData.length / 2;
      const mulawData = Buffer.alloc(numSamples);
      
      const MULAW_MAX = 0x1FFF;
      const MULAW_BIAS = 0x84;
      
      for (let i = 0; i < numSamples; i++) {
        let sample = pcmData.readInt16LE(i * 2);
        
        // Get sign
        const sign = (sample >> 8) & 0x80;
        
        // Get magnitude
        if (sign) {
          sample = -sample;
        }
        
        // Clip
        if (sample > MULAW_MAX) {
          sample = MULAW_MAX;
        }
        
        // Add bias
        sample = sample + MULAW_BIAS;
        
        // Find exponent
        let exponent = 7;
        for (let j = 0; j < 8; j++) {
          if (sample & (0x4000 >> j)) {
            exponent = 7 - j;
            break;
          }
        }
        
        // Extract mantissa
        const mantissa = (sample >> (exponent + 3)) & 0x0F;
        
        // Encode
        const mulawByte = ~(sign | (exponent << 4) | mantissa);
        mulawData[i] = mulawByte & 0xFF;
      }
      
      return mulawData;
    } catch (error) {
      logger.error(`Error converting PCM to μ-law: ${error}`);
      return Buffer.alloc(0);
    }
  }

  /**
   * Simple audio resampling
   * @param audioData Audio data to resample
   * @param fromRate Source sample rate
   * @param toRate Target sample rate
   * @returns Resampled audio data
   */
  resampleAudio(audioData: Buffer, fromRate: number, toRate: number): Buffer {
    try {
      if (!audioData || audioData.length === 0 || fromRate === toRate) {
        return audioData;
      }

      const numSamples = audioData.length / 2;
      const ratio = toRate / fromRate;
      const newNumSamples = Math.floor(numSamples * ratio);
      const resampledData = Buffer.alloc(newNumSamples * 2);

      // Simple linear interpolation resampling
      for (let i = 0; i < newNumSamples; i++) {
        const sourceIndex = i / ratio;
        const sourceIndexInt = Math.floor(sourceIndex);
        const fraction = sourceIndex - sourceIndexInt;

        if (sourceIndexInt >= numSamples - 1) {
          // Use last sample
          const sample = audioData.readInt16LE((numSamples - 1) * 2);
          resampledData.writeInt16LE(sample, i * 2);
        } else {
          // Linear interpolation between two samples
          const sample1 = audioData.readInt16LE(sourceIndexInt * 2);
          const sample2 = audioData.readInt16LE((sourceIndexInt + 1) * 2);
          const interpolated = Math.round(sample1 * (1 - fraction) + sample2 * fraction);
          resampledData.writeInt16LE(interpolated, i * 2);
        }
      }

      return resampledData;
    } catch (error) {
      logger.error(`Error resampling audio: ${error}`);
      return audioData;
    }
  }
} 