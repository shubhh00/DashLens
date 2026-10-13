# DashLens: a dashboard warning-light co-driver

A hands-free Android voice and camera assistant built on **Agora Conversational AI**. Point the phone at the instrument cluster and ask "what's this light?". DashLens sees the symbol through the live camera, explains it from **that car's own owner's manual**, asks a follow-up when the answer depends on something it can't see, and, for an urgent lamp, shows the carmaker's verified roadside helpline one tap from the dialler.

🥉 3rd place, Agora Voice AI Hackathon 2026 (AI Mobile Coders).

## What this recipe shows

- **Vision input**: the LLM receives the latest frame of the user's RTC camera stream with every turn (`input_modalities: ["text", "image"]`).
- **HTTP tool calling**: the agent calls two tools on your own server mid-conversation, `lookupManual(make, model)` and `getRoadsideHelpline(make)`.
- **Silent UI tags**: TTS `skip_patterns` keeps `{curly brace}` text out of the voice, so the agent can send UI instructions (source line, stop card, call button) inside its reply.
- **RTM transcripts and agent state** driving a word-by-word caption and status pill.
- **Keyword barge-in**: "wait" or "stop" interrupts the agent; road noise doesn't.
- **Per-turn latency analytics** saved after each call.

## Architecture

```
 Android app (Kotlin, Jetpack Compose)
   mic + rear camera (720p, frames rotated upright)
        │  Agora RTC                 ▲ RTM: transcripts, agent state
        ▼                            │
 Agora Conversational AI ────────────┘
   Deepgram nova-3 (ASR) → gpt-5-mini (text + camera frame) → ElevenLabs / OpenAI TTS
        │  HTTP tool calls
        ▼
 FastAPI server (owns all keys, mints tokens, starts/stops the agent)
   /v1/tools/manual    → manual cache (28 cars) or background manual search
   /v1/tools/helpline  → verified roadside helplines
```

## Prerequisites

- Android Studio (JDK 17+) and an Android phone with a camera (API 24+)
- Python 3.10+
- An Agora project with Conversational AI enabled (App ID and App Certificate)
- A public HTTPS tunnel to your server, such as ngrok (Agora's cloud calls the tools over the internet)
- Optional: an ElevenLabs key (otherwise the Agora-managed OpenAI voice is used); Gemini, Tavily and Serper keys only to add cars that aren't cached

## 1. Run the server

```bash
cd server
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env.local         # set AGORA_APP_ID and AGORA_APP_CERTIFICATE
```

Start a tunnel and put its URL in `server/.env.local` as `PUBLIC_BASE_URL`; the tools are only registered when it is set:

```bash
ngrok http 8000
```

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`GET /health` should return `"agora_configured": true`.

## 2. Run the app

Add the tunnel URL to `local.properties` in the project root, then run the `app` configuration on your phone from Android Studio:

```properties
DASHLENS_SERVER_URL=https://your-tunnel.ngrok-free.app
```

Grant microphone and camera access, tap the mic, say your car ("This is my Tata Tiago") and point the camera at a lamp.

## 3. How it works

### The agent: vision LLM plus tools

The server builds one agent per call ([agora_client.py](../../server/app/agora_client.py)). The LLM gets image input, and each tool is an HTTP endpoint on the server that Agora calls synchronously:

```python
tools = [{
    "type": "function",
    "function": {
        "name": "lookupManual",
        "description": "Look up the warning lamp meanings from a car's owner manual. "
                       "Call this as soon as you know the car's make and model.",
        "parameters": {
            "type": "object",
            "properties": {"make": {"type": "string"}, "model": {"type": "string"}},
            "required": ["make", "model"],
        },
    },
    "execution": {"mode": "sync"},
    "server": {
        "method": "GET",
        "url": PUBLIC_BASE_URL + "/v1/tools/manual?make={{args.make}}&model={{args.model}}&sid=" + tool_sid,
        "timeout_ms": 60000,
    },
}]

agent = (
    Agent(client=client, advanced_features={"enable_rtm": True, "enable_tools": True}, ...)
    .with_stt(DeepgramSTT(model="nova-3", language="en"))
    .with_llm(OpenAI(model="gpt-5-mini", tools=tools,
                     input_modalities=["text", "image"],   # the latest camera frame comes with each turn
                     params={"reasoning_effort": "minimal", "verbosity": "low"}))
    .with_tts(ElevenLabsTTS(..., skip_patterns=[5]))        # 5 = never speak {curly braces}
)
```

`sid` is a per-call id. The server uses it to read the call's history and refuse a lookup for a car model nobody actually said (the LLM occasionally invents one).

### The tool endpoint: manual data plus a screen tag

`/v1/tools/manual` ([routes.py](../../server/app/routes.py)) answers from the cache in about 13 ms. For an unknown car it replies "being fetched" at once and starts the manual pipeline in the background, so the driver never waits in silence. Every result carries the verified helpline and a ready-made screen tag:

```json
{
  "source": "manual",
  "car": "Tata Tiago",
  "lamps": ["High Coolant Temperature (red). Steady: Engine coolant temperature is very high. Stop engine and allow it to cool.", "..."],
  "roadside_spoken": "one eight hundred, two zero nine, eight two eight two",
  "screen_tag": "{car:Tata Tiago|manual|Tata Motors cars customer care and roadside assistance|18002098282}"
}
```

The prompt tells the agent to begin its reply with `screen_tag`. TTS skips it, and the app parses it ([AgentTags.kt](../../app/src/main/java/com/dashlens/app/ui/AgentTags.kt)) into the "Tata Tiago · owner's manual" source line and the call button. When the reply says to pull over, the app shows a red stop card with that helpline.

### The manual pipeline

[manual_pipeline.py](../../server/app/manual/manual_pipeline.py) turns a 450–700 page owner's manual into structured lamp data once per car:

1. **Find**: carmaker feeds first (Maruti/Nexa), then Tavily and Serper search, with candidates scored (official and Indian editions first, brochures and other markets out).
2. **Verify**: a real manual has 50+ pages and a warning-lamp section.
3. **Extract**: keep only the ~26 most lamp-dense pages.
4. **Structure**: Gemini returns `{lamp, colour, steady, flashing}` per lamp, with model fallback, and the raw lamp pages as a last resort.
5. **Cache**: `server/cache/<make>_<model>.json`.

### Upright camera frames

The UI is locked to portrait, but drivers hold the phone sideways to fit a wide cluster. A pre-encoder `IVideoFrameObserver` ([UprightFrameRotator.kt](../../app/src/main/java/com/dashlens/app/rtc/UprightFrameRotator.kt)) rotates each I420 frame by the device angle so the model always sees the dashboard upright, while the on-screen preview is untouched.

### Prompting for a safety assistant

The system prompt reasons like a mechanic in the passenger seat rather than listing rules:

- Speed above zero means the engine is running; a rev counter at 0, or the oil and battery lamps together, means it is off (the start-up self-check, not a fault).
- A red brake lamp on a stationary car is usually the handbrake: ask the driver to release it and watch the lamp.
- Only oil pressure, temperature, charging, brake-fault and steering lamps on a moving car get "pull over safely".
- If a symbol is unclear, ask for a closer look instead of guessing; never hedge with "if X then stop, otherwise...".

## Try it

1. "This is my Tata Tiago, what's this red light?" with a red temperature lamp at speed: the agent says pull over, and the stop card appears with the Tata helpline.
2. "This is my BMW M3, what's this amber light?" with the check engine lamp: keep driving and get it checked, from BMW's manual.
3. "What's Mahindra's roadside number?": the number is read in short groups and a call button appears.
4. Say "wait" while it is talking: it stops.

## Troubleshooting

- **The agent never looks anything up**: `PUBLIC_BASE_URL` is missing or the tunnel is down; the tools are only registered when it is set.
- **No stop card or call button**: check that the reply starts with a `{car:...}` or `{help:...}` tag in the server's saved transcript (`server/transcripts/`).
- **No voice**: the ElevenLabs quota may be used up; the server falls back to Agora's OpenAI voice automatically when fewer than 1,000 characters remain.
- **Wrong lamp**: hold the phone closer so the lamp is clearly visible; small or blurred icons are the main source of errors.

## Credits

Built by Shubh Singh on top of Agora's [agent-quickstart-android](https://github.com/AgoraIO-Conversational-AI/agent-quickstart-android). More detail, measured results and limitations are in the [README](../../README.md).
