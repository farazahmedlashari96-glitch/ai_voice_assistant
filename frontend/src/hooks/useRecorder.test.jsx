import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useRecorder } from "./useRecorder.js";

// Fake browser audio: the "worklet node" lets the test push microphone blocks by hand.
let node;
let stopTrack;

class FakeNode {
  constructor() {
    this.port = { onmessage: null };
    node = this;
  }
  connect() {}
  disconnect() {}
}

class FakeContext {
  constructor() {
    this.sampleRate = 16000;
    this.destination = {};
    this.audioWorklet = { addModule: vi.fn(() => Promise.resolve()) };
  }
  createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
  createGain() { return { gain: { value: 1 }, connect() {}, disconnect() {} }; }
  resume() { return Promise.resolve(); }
  close() { return Promise.resolve(); }
}

const block = (amplitude, samples = 2048) => new Float32Array(samples).fill(amplitude); // 0.128 s at 16 kHz

function setup(options = {}) {
  const onRecorded = vi.fn();
  const onError = vi.fn();
  const hook = renderHook(() => useRecorder({ onRecorded, onError, ...options }));
  return { ...hook, onRecorded, onError };
}

const push = (amplitude, times = 1) => {
  for (let i = 0; i < times; i++) act(() => node.port.onmessage({ data: block(amplitude) }));
};

beforeEach(() => {
  stopTrack = vi.fn();
  window.AudioContext = FakeContext;
  window.AudioWorkletNode = FakeNode;
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(() => Promise.resolve({ getTracks: () => [{ stop: stopTrack }] })) },
  });
});

afterEach(() => {
  delete window.AudioContext;
  delete window.AudioWorkletNode;
});

describe("useRecorder", () => {
  it("records speech and stops by itself after a pause, producing a 16 kHz WAV", async () => {
    const { result, onRecorded, onError } = setup();
    await act(() => result.current.start());

    push(0.005, 4); // background noise (calibration)
    push(0.2, 5); // speech
    expect(onRecorded).not.toHaveBeenCalled();
    push(0.005, 11); // 11 blocks = 1.41 s of quiet (limit is 1.4 s)

    expect(onError).not.toHaveBeenCalled();
    expect(onRecorded).toHaveBeenCalledTimes(1);
    const wav = onRecorded.mock.calls[0][0];
    expect(wav.type).toBe("audio/wav");
    expect(wav.size).toBe(44 + (4 + 5 + 11) * 2048 * 2);
    expect(stopTrack).toHaveBeenCalled(); // microphone released
  });

  it("reports 'no input' when nobody speaks", async () => {
    const { result, onRecorded, onError } = setup();
    await act(() => result.current.start());
    push(0.005, 63); // just over 8 s of silence

    expect(onRecorded).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ code: "no_input" }));
  });

  it("sends what was recorded when the user finishes manually", async () => {
    const { result, onRecorded } = setup();
    await act(() => result.current.start());
    push(0.005, 4);
    push(0.2, 3);
    act(() => result.current.stop());
    expect(onRecorded).toHaveBeenCalledTimes(1);
  });

  it("throws the recording away on cancel", async () => {
    const { result, onRecorded, onError } = setup();
    await act(() => result.current.start());
    push(0.2, 3);
    act(() => result.current.cancel());
    expect(onRecorded).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalled();
  });

  it("explains a blocked microphone", async () => {
    navigator.mediaDevices.getUserMedia = vi.fn(() => Promise.reject({ name: "NotAllowedError" }));
    const { result, onError } = setup();
    await act(() => result.current.start());
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ code: "mic_error", message: expect.stringMatching(/blocked/i) }));
  });

  it("can start again after finishing", async () => {
    const { result, onRecorded } = setup();
    await act(() => result.current.start());
    push(0.005, 4);
    push(0.2, 2);
    act(() => result.current.stop());
    await act(() => result.current.start());
    push(0.005, 4);
    push(0.2, 2);
    act(() => result.current.stop());
    expect(onRecorded).toHaveBeenCalledTimes(2);
  });
});
