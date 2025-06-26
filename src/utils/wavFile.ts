/**
 * Simple WAV file encoder utility
 */

export function encodeWav(samples: Buffer, sampleRate: number, bitDepth: number = 16): Buffer {
  const dataLength = samples.length;
  const headerLength = 44;
  const fileLength = dataLength + headerLength;
  
  const buffer = Buffer.alloc(fileLength);
  
  // RIFF header
  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(fileLength - 8, 4);
  buffer.write('WAVE', 8);
  
  // fmt chunk
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16); // fmt chunk size
  buffer.writeUInt16LE(1, 20); // PCM format
  buffer.writeUInt16LE(1, 22); // Mono
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * bitDepth / 8, 28); // Byte rate
  buffer.writeUInt16LE(bitDepth / 8, 32); // Block align
  buffer.writeUInt16LE(bitDepth, 34); // Bits per sample
  
  // data chunk
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataLength, 40);
  
  // Copy audio data
  samples.copy(buffer, 44);
  
  return buffer;
} 