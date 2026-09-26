import { describe, expect, it } from "vitest";
import { chunksToWavBlob, downsample, encodeWavBytes, mergeChunks } from "./wav.js";

const text = (bytes, start, end) => String.fromCharCode(...bytes.slice(start, end));

describe("WAV encoding", () => {
  it("writes a valid 16-bit mono PCM header", () => {
    const bytes = encodeWavBytes(new Float32Array([0, 0.5, -0.5, 1]), 16000);
    const view = new DataView(bytes.buffer);
    expect(text(bytes, 0, 4)).toBe("RIFF");
    expect(text(bytes, 8, 12)).toBe("WAVE");
    expect(text(bytes, 12, 16)).toBe("fmt ");
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(text(bytes, 36, 40)).toBe("data");
    expect(view.getUint32(40, true)).toBe(8);
    expect(view.getUint32(4, true)).toBe(bytes.length - 8);
    expect(bytes.length).toBe(44 + 8);
  });

  it("converts and clips samples to signed 16-bit", () => {
    const bytes = encodeWavBytes(new Float32Array([0, 1, -1, 2, -2]), 16000);
    const view = new DataView(bytes.buffer);
    const values = [0, 1, 2, 3, 4].map((i) => view.getInt16(44 + i * 2, true));
    expect(values).toEqual([0, 32767, -32768, 32767, -32768]);
  });
});

describe("resampling", () => {
  it("48 kHz -> 16 kHz keeps a constant signal constant", () => {
    const out = downsample(new Float32Array(4800).fill(0.5), 48000, 16000);
    expect(out.length).toBe(1600);
    expect(out.every((v) => Math.abs(v - 0.5) < 1e-6)).toBe(true);
  });

  it("44.1 kHz -> 16 kHz gives one second of samples", () => {
    expect(downsample(new Float32Array(44100), 44100, 16000).length).toBe(16000);
  });

  it("does not upsample", () => {
    const input = new Float32Array(100);
    expect(downsample(input, 8000, 16000)).toBe(input);
  });
});

describe("chunksToWavBlob", () => {
  it("merges chunks into one WAV blob", () => {
    expect(mergeChunks([new Float32Array(3), new Float32Array(5)]).length).toBe(8);
    const blob = chunksToWavBlob([new Float32Array(24000), new Float32Array(24000)], 48000);
    expect(blob.type).toBe("audio/wav");
    expect(blob.size).toBe(44 + 16000 * 2); // one second at 16 kHz
  });
});
