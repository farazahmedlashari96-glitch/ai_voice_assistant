// Runs on the audio thread: collects microphone samples and posts them (in blocks of
// ~2048 samples) to the page, which turns them into a 16 kHz WAV file.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.parts = [];
    this.count = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      this.parts.push(new Float32Array(channel));
      this.count += channel.length;
      if (this.count >= 2048) {
        const block = new Float32Array(this.count);
        let offset = 0;
        for (const part of this.parts) {
          block.set(part, offset);
          offset += part.length;
        }
        this.port.postMessage(block, [block.buffer]);
        this.parts = [];
        this.count = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCapture);
