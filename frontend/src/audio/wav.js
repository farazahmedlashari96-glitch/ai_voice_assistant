// Phase 2 - audio processing: turn raw microphone samples into a WAV file
// (16 kHz, mono, 16-bit PCM - the format the project brief recommends).
export const TARGET_RATE = 16000;

export function mergeChunks(chunks) {
  const total = chunks.reduce((n, chunk) => n + chunk.length, 0);
  const merged = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

/** Reduce the sample rate by averaging (a simple anti-aliasing low-pass). */
export function downsample(samples, inputRate, outputRate = TARGET_RATE) {
  if (outputRate >= inputRate) return samples;
  const ratio = inputRate / outputRate;
  const length = Math.floor(samples.length / ratio);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(samples.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += samples[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

/** Mono 16-bit PCM WAV file as bytes. */
export function encodeWavBytes(samples, sampleRate) {
  const dataBytes = samples.length * 2;
  const bytes = new Uint8Array(44 + dataBytes);
  const view = new DataView(bytes.buffer);
  const text = (offset, value) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };

  text(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  view.setUint32(40, dataBytes, true);

  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return bytes;
}

export function chunksToWavBlob(chunks, inputRate, targetRate = TARGET_RATE) {
  const samples = downsample(mergeChunks(chunks), inputRate, targetRate);
  const rate = Math.min(inputRate, targetRate);
  return new Blob([encodeWavBytes(samples, rate)], { type: "audio/wav" });
}
