class PCMPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.current = null;
    this.offset = 0;

    this.port.onmessage = (event) => {
      const { samples } = event.data || {};
      if (!samples) {
        return;
      }
      const float32 = new Float32Array(samples);
      this.queue.push(float32);
    };
  }

  process(_inputs, outputs) {
    const output = outputs[0];
    if (!output || output.length === 0) {
      return true;
    }
    const channelData = output[0];
    channelData.fill(0);

    let writeIndex = 0;
    while (writeIndex < channelData.length) {
      if (!this.current || this.offset >= this.current.length) {
        this.current = this.queue.shift();
        this.offset = 0;
        if (!this.current) {
          break;
        }
      }

      const available = this.current.length - this.offset;
      const remaining = channelData.length - writeIndex;
      const copyLength = Math.min(available, remaining);
      channelData.set(
        this.current.subarray(this.offset, this.offset + copyLength),
        writeIndex
      );

      writeIndex += copyLength;
      this.offset += copyLength;
    }

    // Mirror mono data to the rest of the channels if needed.
    for (let channel = 1; channel < output.length; channel += 1) {
      output[channel].set(channelData);
    }

    return true;
  }
}

registerProcessor("pcm-player-processor", PCMPlayerProcessor);
