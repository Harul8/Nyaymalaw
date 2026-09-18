/* The microphone, as the live speech model wants it. Implementation Plan F-C-03.
 *
 * 16-BIT MONO FRAMES, A TENTH OF A SECOND AT A TIME. The audio graph hands this
 * processor 128 samples at a time -- 8 ms, which would be 125 messages a second
 * on the socket -- so they are gathered into ~100 ms frames first.
 *
 * THE RATE IS THE CONTEXT'S. The page opens the audio context at 16 kHz, the
 * rate the model is built for, so nothing is resampled here or on the server.
 *
 * NOTHING IS KEPT. Each frame is posted to the page and the buffer reused; this
 * processor holds at most a tenth of a second of the advocate's voice.
 */
const FRAME_SAMPLES = 1600;

class DictationProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.pending = new Int16Array(FRAME_SAMPLES);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let at = 0; at < channel.length; at += 1) {
      // Clamped before scaling: a sample outside [-1, 1] would wrap round to
      // the opposite sign and arrive as a click.
      const sample = Math.max(-1, Math.min(1, channel[at]));
      this.pending[this.filled] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      this.filled += 1;
      if (this.filled === FRAME_SAMPLES) {
        const frame = this.pending;
        this.pending = new Int16Array(FRAME_SAMPLES);
        this.filled = 0;
        this.port.postMessage(frame.buffer, [frame.buffer]);
      }
    }
    return true;
  }
}

registerProcessor('dictation', DictationProcessor);
