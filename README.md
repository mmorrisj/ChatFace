# ChatFace

A voice chat companion for children, running on a Raspberry Pi 5 with a
touchscreen, camera, and microphone. A child taps the screen, talks, and gets a
spoken reply from a face made of two eyes and a mouth.

> **Status: step 1.** The activation lifecycle and the face are built and
> tested. Speech recognition, the language model, text-to-speech, face
> recognition, and the database are not wired in yet — see [Roadmap](#roadmap).

## Design decisions

**A tap starts every conversation.** No wake word, no motion sensor, no "stand
here for three seconds". A tap has zero false positives, needs no extra
hardware, and is instantly understood by a four-year-old. It also happens to be
the best possible moment to photograph a face: the child is within arm's reach,
facing the screen, and holding still.

**The camera is open for about one second per conversation.** Long enough to
grab frames for identification, then off. The microphone is closed entirely
until a tap. Both properties are derived from the session state in exactly one
place — `session/states.py` — and asserted in `TestPrivacyInvariants`.

**Identification never blocks the conversation.** The microphone opens on the
tap; who the child is resolves asynchronously and the greeting arrives when it
does. A slow or failed face lookup costs a personalised hello, not a working
device.

**The mouth is the frequency visualiser.** During a response it is driven by the
audio being played; while listening it is driven by the microphone, so a child
can see they are being heard. That feedback matters more than it looks —
children's speech is significantly harder for ASR than adult speech, and a mouth
that barely moves teaches a child to speak up without anyone telling them to.

**Audio plays in the browser, not through the Pi's audio device.** This is what
makes the visualiser possible: `AnalyserNode` gives a real FFT of exactly what
is audible, perfectly synced, instead of an amplitude envelope pushed over a
socket and forever slightly out of step.

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn chatface.main:app --host 0.0.0.0 --port 8000
```

Open <http://localhost:8000>. The bar along the bottom drives the state machine
by hand and toggles the mouth on and off; add `?kiosk` to the URL to hide it.

The microphone needs a secure context, which `localhost` counts as. Reaching the
Pi from another machine over plain HTTP will leave the mouth idling rather than
responding to sound.

On the device itself:

```bash
chromium-browser --kiosk --app=http://localhost:8000/?kiosk
```

## Development

```bash
.venv/bin/pytest            # 20 tests, no hardware required
.venv/bin/ruff check .
.venv/bin/ruff format .
.venv/bin/mypy              # strict
```

## Layout

```
src/chatface/
├── config.py            settings, env-driven
├── main.py              FastAPI app: kiosk page + WebSocket
├── session/
│   ├── states.py        SessionState, Event, and the sensor rules
│   └── machine.py       the transition table
├── api/ws.py            one browser connection: events in, state out
└── static/              the face (SVG eyes, canvas mouth)
```

The state machine is synchronous and side-effect free. Timers, sockets, and
hardware live outside and feed events in, which is why the entire conversation
lifecycle is testable with no camera, no microphone, and no clock.

```
IDLE ──tap──> WAKE ──identified / timeout / speech──> LISTENING
                                                       │      ▲
                                        speech ends    ▼      │ playback done
                                                    THINKING ─┴─> SPEAKING
                                                       │            │
                             barge-in (child speaks) ──┴────────────┘

LISTENING ──20s silence──> IDLE        any state ──stop──> IDLE
                                       any state ──disconnect──> OFFLINE
```

## Roadmap

| Step | Scope | State |
|---|---|---|
| 1 | Activation lifecycle, WebSocket transport, face UI | done |
| 2 | Voice loop: VAD → speech recognition → model → Piper TTS | next |
| 3 | Postgres + pgvector, avatar picker, per-child history | |
| 4 | Face recognition (InsightFace → pgvector) pre-selects the avatar | |
| 5 | Parent dashboard: transcripts, time limits, quiet hours | |

### Notes for step 2

- Speech recognition should sit behind a `Protocol` from the start. Children's
  word error rates are materially worse than adults', so expect to start with a
  cloud provider and keep `faster-whisper` as the offline path.
- Piper synthesises in real time on a Pi 5 CPU. Use the *medium* voice tier —
  the highest that stays comfortably real time.
- Split the model's output on sentence boundaries and feed Piper a sentence at a
  time, streaming audio chunks as they are ready. Budget under 1.5s from
  end-of-speech to first audio, or it feels broken to a child.

### Hardware note

The Pi 5 has no 3.5mm audio jack, and the official DSI touch display carries no
audio. Plan for a USB speaker, HDMI audio, or an I2S hat.
