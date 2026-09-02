/* The face: SVG eyes driven by CSS state classes, canvas mouth driven by audio.
 *
 * The mouth *is* the frequency visualiser. During LISTENING it is driven by the
 * microphone, so a child can see that they are being heard; during SPEAKING it
 * is driven by the response audio. Until Piper is wired in, SPEAKING uses a
 * synthetic syllable envelope so the animation can be judged without a backend.
 */

const BINS = 28;

const body = document.body;
const stage = document.getElementById("stage");
const caption = document.getElementById("caption");
const stopButton = document.getElementById("stop");
const stateLabel = document.getElementById("state-label");

/* --- Mouth ---------------------------------------------------------------- */

class Mouth {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.level = new Float32Array(BINS);
    this.resize();
    addEventListener("resize", () => this.resize());
  }

  resize() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const rect = this.canvas.getBoundingClientRect();
    this.w = Math.max(1, rect.width);
    this.h = Math.max(1, rect.height);
    this.canvas.width = this.w * dpr;
    this.canvas.height = this.h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /** Ease toward the new spectrum. Without this it reads as an instrument. */
  update(target) {
    for (let i = 0; i < BINS; i++) {
      this.level[i] += (target[i] - this.level[i]) * 0.28;
    }
  }

  draw(curve, color, alpha) {
    const { ctx, w, h } = this;
    ctx.clearRect(0, 0, w, h);

    const pad = w * 0.06;
    const span = w - pad * 2;
    const maxThickness = h * 0.72;
    const minThickness = h * 0.055;
    const top = [];
    const bottom = [];

    for (let i = 0; i < BINS; i++) {
      const t = i / (BINS - 1);
      const x = pad + t * span;
      // Taper toward the corners so the shape has mouth-like rounded ends
      // instead of a squared-off bar chart.
      const taper = Math.pow(Math.sin(Math.PI * t), 0.65);
      const thickness = minThickness + this.level[i] * maxThickness * taper;
      // A positive curve drops the centre and lifts the corners: a smile.
      const cy = h / 2 + curve * (1 - 4 * (t - 0.5) ** 2) * h * 0.16;
      top.push([x, cy - thickness / 2]);
      bottom.push([x, cy + thickness / 2]);
    }

    ctx.globalAlpha = alpha;
    ctx.fillStyle = color;
    ctx.beginPath();
    traceSmooth(ctx, top, true);
    traceSmooth(ctx, bottom.reverse(), false);
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;
  }
}

/** Draw a polyline as a smooth curve through midpoints. */
function traceSmooth(ctx, points, start) {
  const [x0, y0] = points[0];
  if (start) ctx.moveTo(x0, y0);
  else ctx.lineTo(x0, y0);
  for (let i = 1; i < points.length - 1; i++) {
    const [x, y] = points[i];
    const [nx, ny] = points[i + 1];
    ctx.quadraticCurveTo(x, y, (x + nx) / 2, (y + ny) / 2);
  }
  const last = points[points.length - 1];
  ctx.lineTo(last[0], last[1]);
}

/* --- Audio sources -------------------------------------------------------- */

/** Live microphone level, so LISTENING shows the child they are being heard. */
class MicSource {
  constructor() {
    this.analyser = null;
    this.raw = null;
    this.pending = false;
  }

  /** Must be called from a user gesture. Safe to call repeatedly. */
  async start() {
    if (this.analyser || this.pending) return;
    this.pending = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.6;
      context.createMediaStreamSource(stream).connect(analyser);
      this.analyser = analyser;
      this.raw = new Uint8Array(analyser.frequencyBinCount);
    } catch (err) {
      console.warn("microphone unavailable, mouth will idle", err);
    } finally {
      this.pending = false;
    }
  }

  read(out) {
    if (!this.analyser) return false;
    this.analyser.getByteFrequencyData(this.raw);
    // Speech energy lives below ~4 kHz; spread those bins across the mouth.
    const usable = Math.min(this.raw.length, 180);
    for (let i = 0; i < BINS; i++) {
      const lo = Math.floor((i / BINS) ** 1.35 * usable);
      const hi = Math.max(lo + 1, Math.floor(((i + 1) / BINS) ** 1.35 * usable));
      let sum = 0;
      for (let j = lo; j < hi; j++) sum += this.raw[j];
      out[i] = Math.min(1, sum / (hi - lo) / 190);
    }
    return true;
  }
}

/**
 * Placeholder for response audio until Piper is streaming.
 *
 * Models speech as a ~4.5 Hz syllable train with occasional pauses, which is
 * close enough to real speech to judge the animation by.
 */
class SyntheticSpeech {
  constructor() {
    this.phase = 0;
    this.amp = 0.7;
    this.gap = 0;
    this.shimmer = new Float32Array(BINS).fill(0.5);
  }

  read(out, dt) {
    if (this.gap > 0) {
      this.gap -= dt;
      out.fill(0);
      return true;
    }
    this.phase += dt * (4.0 + Math.random() * 1.2);
    if (this.phase >= 1) {
      this.phase = 0;
      this.amp = 0.35 + Math.random() * 0.65;
      if (Math.random() < 0.16) this.gap = 0.16 + Math.random() * 0.28;
    }
    const envelope = Math.sin(Math.PI * this.phase) ** 0.7 * this.amp;
    for (let i = 0; i < BINS; i++) {
      const t = i / (BINS - 1);
      // Energy concentrated toward the low-mid, like a voice.
      const formant = Math.exp(-((t - 0.32) ** 2) / 0.09);
      this.shimmer[i] += (Math.random() - 0.5) * 0.35;
      this.shimmer[i] = Math.min(1, Math.max(0.25, this.shimmer[i]));
      out[i] = envelope * formant * this.shimmer[i];
    }
    return true;
  }
}

/* --- Face controller ------------------------------------------------------ */

const mouth = new Mouth(document.getElementById("mouth"));
const mic = new MicSource();
const speech = new SyntheticSpeech();
const target = new Float32Array(BINS);

let state = "idle";
let clock = performance.now();

const CAPTIONS = { idle: "tap to talk", offline: "reconnecting…" };

function render(now) {
  const dt = Math.min(0.05, (now - clock) / 1000);
  clock = now;

  if (state === "speaking") {
    speech.read(target, dt);
  } else if ((state === "listening" || state === "wake") && mic.read(target)) {
    // Driven by the live microphone.
  } else {
    // Idle breathing so the mouth never looks dead or vanishes.
    const breath = 0.045 + Math.sin(now / 900) * 0.03;
    for (let i = 0; i < BINS; i++) target[i] = breath;
  }

  mouth.update(target);
  const style = getComputedStyle(body);
  mouth.draw(
    parseFloat(style.getPropertyValue("--mouth-curve")) || 0,
    style.getPropertyValue("--ink").trim() || "#4fd8ff",
    parseFloat(style.getPropertyValue("--eye-glow")) || 0.5,
  );
  requestAnimationFrame(render);
}
requestAnimationFrame(render);

/* A face that never blinks is dead. Cheapest aliveness available. */
function scheduleBlink() {
  setTimeout(() => {
    blink();
    if (Math.random() < 0.2) setTimeout(blink, 210);
    scheduleBlink();
  }, 2200 + Math.random() * 4200);
}
function blink() {
  if (state === "offline") return;
  body.classList.add("blink");
  setTimeout(() => body.classList.remove("blink"), 110);
}
scheduleBlink();

/** Flick the eyes toward where the child touched, then settle. */
function glanceAt(x, y) {
  const dx = Math.max(-18, Math.min(18, (x / innerWidth - 0.5) * 46));
  const dy = Math.max(-12, Math.min(12, (y / innerHeight - 0.5) * 26));
  body.style.setProperty("--eye-dx", `${dx}px`);
  body.style.setProperty("--eye-dy", `${dy}px`);
  setTimeout(() => {
    body.style.removeProperty("--eye-dx");
    body.style.removeProperty("--eye-dy");
  }, 750);
}

function applyState(next, devices) {
  state = next;
  body.dataset.state = next;
  stateLabel.textContent = next;
  stopButton.hidden = next === "idle" || next === "offline";
  caption.textContent = CAPTIONS[next] ?? "";
  caption.classList.toggle("show", Boolean(CAPTIONS[next]));
  for (const pip of document.querySelectorAll(".pip")) {
    const key = pip.dataset.pip === "mic" ? "mic_open" : "camera_open";
    pip.classList.toggle("on", Boolean(devices?.[key]));
  }
}

/* --- Transport ------------------------------------------------------------ */

let socket = null;
let backoff = 500;

function connect() {
  socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  socket.addEventListener("open", () => {
    backoff = 500;
  });
  socket.addEventListener("message", (message) => {
    const payload = JSON.parse(message.data);
    applyState(payload.state, payload);
  });
  socket.addEventListener("close", () => {
    applyState("offline", null);
    setTimeout(connect, backoff);
    backoff = Math.min(8000, backoff * 2);
  });
}
connect();

function send(event) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ event }));
}

/* --- Input ---------------------------------------------------------------- */

stage.addEventListener("pointerdown", (event) => {
  glanceAt(event.clientX, event.clientY);
  // Browsers only grant the microphone from a user gesture, so ask on the tap
  // that starts the conversation.
  mic.start();
  if (state === "idle") send("tap");
});

stopButton.addEventListener("click", (event) => {
  event.stopPropagation();
  send("stop");
});

for (const button of document.querySelectorAll("#dev button")) {
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    mic.start();
    send(button.dataset.event);
  });
}

document.getElementById("toggle-mouth").addEventListener("change", (event) => {
  body.classList.toggle("no-mouth", !event.target.checked);
});

if (new URLSearchParams(location.search).has("kiosk")) body.classList.add("kiosk");
