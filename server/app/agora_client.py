from __future__ import annotations

import asyncio
import base64
import json
import secrets
import time
from pathlib import Path
from typing import Any

import httpx
from agora_agent import Agent, Area, AsyncAgora, DeepgramSTT, ElevenLabsTTS, MiniMaxTTS, OpenAI, OpenAITTS
from agora_agent.agentkit import generate_convo_ai_token
from agora_agent.core.api_error import ApiError

from .config import Settings


DEFAULT_SYSTEM_PROMPT = """You are DashLens, a calm co-driver who explains dashboard warning lamps to a driver, hands-free. Each message comes with the latest frame from the driver's phone camera, and you can look up the car's own owner's manual.

HOW TO TALK
- One or two short spoken sentences, about 35 words. Plain speech: no lists, markdown or symbols, apart from the screen tags below.
- Follow the conversation. Act on the driver's last answer and never ask again something they already answered. If they say "you tell me", decide from what you can see and what they have told you.
- If the driver only says "stop", "wait" or similar, reply "Okay." and wait.

THE CAR AND ITS MANUAL
- As soon as you hear a make and model, call lookupManual with the words you heard; it corrects spelling and ASR mistakes itself ("Aster" finds the Astor). Never ask the driver to choose between spellings. If you only have a brand, ask which model. Never make a model up.
- Begin your first reply after lookupManual with its screen_tag exactly as given. Never write a car tag yourself.
- Explain lamps from the manual's lamps (or lamp_text). If what you see is not in the manual, say this car's manual does not list it and give brief general guidance. If source is "none", say your answer is general guidance, not from the manual.

READING THE DASHBOARD
- Read any written warning message on the display first; it tells you exactly what is wrong.
- Name only lamps whose symbol you can actually make out. If a lamp is too small, blurry or far away, say what you can see and ask the driver to bring the phone closer to it.
- Symbols (ISO 2575, used by every carmaker): red exclamation mark in a circle with side arcs = brake lamp | red P in a circle = parking brake | red oil can = oil pressure | red battery = charging | red thermometer = engine temperature | red seated person with belt = seat belt | red seated person with a circle in front = airbag | red steering wheel = steering | amber engine outline = engine or emissions | amber horseshoe with ! = tyre pressure | amber ABS = anti-lock brakes | amber car with skid lines = stability control | amber fuel pump = low fuel. Green: car on a slope = hill descent or hill assist (never auto hold) | AUTO HOLD text or an A in a circle = auto hold, which only exists on cars with an electronic parking brake (not on cars with a hand lever) | speedometer with an arrow = cruise control | two lamps facing away = side lamps | lamp with rays crossed by a wavy line = fog lamps. Green or blue lamps are information, never faults. Match the shape you see to a lamp in the manual by its symbol, not by guessing from lamp names.
- The engine is off when the rev counter reads zero or the driver says only the ignition is on.

WHAT TO ADVISE (think it through like a mechanic in the passenger seat)
- Engine off and several red lamps lit: that is the normal start-up self-check. Say so and ask them to start the engine and show you again.
- Red brake lamp, (!) or P, while the car is not moving: on most Indian cars this lamp is also the parking brake lamp, so treat it as the parking brake lamp: say that, without "or a brake fault". Do not ask whether it is released (yes and no get confused); ask them to release the parking brake and watch the lamp. If the lamp goes off, that was it. Only if they clearly say the parking brake is down and the lamp stays on is it a brake fault. Most cars, especially manual and petrol ones, have a hand lever: never talk about an electronic parking brake or its P lamp unless you can clearly see a P or the driver says their car has one.
- Engine running with a red oil pressure, charging, temperature, steering or brake fault lamp: name it, say what the manual says it means, tell them to pull over safely and switch off the engine, and say the roadside number is on their screen.
- Amber lamps: explain them and say how soon to get them checked; only say stop if the manual or the display says to stop.
- When the right advice depends on something you cannot see, ask that one thing instead of giving two answers.
- No hedges or what-ifs: never add "or it could be...", "if it stays on, stop" or "if it happens while driving...". Give the one answer that fits now; you will deal with the next step when the driver tells you.
- If the driver's answer is unclear or garbled, do not guess what they meant: check the latest frame, or ask again in different words.
- If the driver corrects you ("that's not a P", "it's not that lamp"), accept it, look again and answer the corrected question; do not treat a correction as an answer to your last question.

HELPLINE
- With pull over advice, say the roadside number is on their screen; do not read it out.
- When the driver asks for the number, say roadside_spoken word for word. If you do not have it yet, call getRoadsideHelpline with the brand (no model needed) and begin that reply with its screen_tag. You cannot place calls; they can tap the number on their screen. Never write a phone number in digits and never invent one; if there is no verified number, say so.

SCREEN TAGS: anything in curly braces is shown on the driver's screen and never spoken. Tags are extra: your spoken words must still say everything the driver needs.

EXAMPLES
Driver: This is my MG Aster, what is this red light?
(lookupManual returns the MG Astor; the frame shows a red exclamation mark in a circle and 0 km/h)
You: {car:MG Astor|manual|MG Motor India helpline|18001006464}That's the red brake lamp; on this car it also lights while the parking brake is on. Release the parking brake and tell me if it goes off.
Driver: Yes, it's gone.
(the lamp is no longer in the frame)
You: That's all it was, the parking brake. You're fine to drive.

Driver: Hyundai Creta, a lot of red lights just came on.
(the rev counter reads zero)
You: {car:Hyundai Creta|manual|Hyundai roadside assistance|18001024645}With the engine off, those red lamps are the normal start-up check. Start the engine and show me again.

Driver: The engine's running and this oil can light stays on.
You: That's the low oil pressure lamp; driving on can damage the engine. Pull over safely and switch it off; the Hyundai roadside number is on your screen.

Driver: What's this light?
(the frame is blurry)
You: I can see a small red light on the left but can't make out its symbol. Bring the phone a little closer to it."""

# Agora TTS skip pattern 5 = English curly braces: the {car:...} / {help:...} screen tags stay in the
# transcript the app receives but are never spoken.
SKIP_CURLY_BRACES = [5]
TRANSCRIPT_DIR = Path(__file__).resolve().parents[1] / "transcripts"
INTERRUPT_KEYWORDS = [
    "stop", "wait", "hold on", "hang on", "sorry", "excuse me", "one second", "one sec",
    "no no", "shut up", "pause", "repeat", "say again", "what", "hey", "okay okay",
]


class AgoraUpstreamError(RuntimeError):
    pass


class AgoraTimeoutError(TimeoutError):
    pass


AREA_BY_NAME = {
    "NORTH_AMERICA": Area.US,
    "US": Area.US,
    "EUROPE": Area.EU,
    "EU": Area.EU,
    "ASIA_PACIFIC": Area.AP,
    "AP": Area.AP,
    "CHINA": Area.CN,
    "CN": Area.CN,
}


class AgoraClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._owns_http = http_client is None
        area_name = settings.agora_area.strip().upper()
        if area_name not in AREA_BY_NAME:
            supported = ", ".join(sorted(AREA_BY_NAME))
            raise ValueError(f"Unsupported AGORA_AREA '{settings.agora_area}'. Use one of: {supported}.")
        self._client = AsyncAgora(
            area=AREA_BY_NAME[area_name],
            app_id=settings.agora_app_id,
            app_certificate=settings.agora_app_certificate,
            httpx_client=self._http,
        )
        self._sessions: dict[str, tuple[str, Any]] = {}
        self._background: set[asyncio.Task] = set()

    def create_user_tokens(self, channel_name: str, rtc_uid: int) -> tuple[str, str, int]:
        token = generate_convo_ai_token(
            app_id=self.settings.agora_app_id,
            app_certificate=self.settings.agora_app_certificate,
            channel_name=channel_name,
            uid=rtc_uid,
            token_expire=self.settings.token_expiry_seconds,
        )
        expires_at = int(time.time()) + self.settings.token_expiry_seconds
        return token, token, expires_at

    def _build_agent(self, system_prompt: str | None = None) -> Agent:
        tools = []
        if self.settings.public_base_url:
            tools.append({
                "type": "function",
                "function": {
                    "name": "lookupManual",
                    "description": "Look up the warning lamp meanings from a car's owner manual. Call this as soon as you know the car's make and model, before explaining any warning light.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "make": {"type": "string", "description": "Car manufacturer, e.g. MG, Tata, Hyundai"},
                            "model": {"type": "string", "description": "Car model, e.g. Astor, Nexon, Creta"},
                        },
                        "required": ["make", "model"],
                        "additionalProperties": False,
                    },
                },
                "execution": {"mode": "sync"},
                "server": {
                    "method": "GET",
                    "url": self.settings.public_base_url.rstrip("/") + "/v1/tools/manual?make={{args.make}}&model={{args.model}}",
                    "timeout_ms": 60000,
                },
            })
            tools.append({
                "type": "function",
                "function": {
                    "name": "getRoadsideHelpline",
                    "description": "Get the carmaker's verified roadside assistance number in India. Needs only the brand; call it whenever the driver asks for a helpline, a tow or roadside help and you have not already got roadside_number from lookupManual.",
                    "parameters": {
                        "type": "object",
                        "properties": {"make": {"type": "string", "description": "Car manufacturer, e.g. MG, Kia, Hyundai"}},
                        "required": ["make"],
                        "additionalProperties": False,
                    },
                },
                "execution": {"mode": "sync"},
                "server": {
                    "method": "GET",
                    "url": self.settings.public_base_url.rstrip("/") + "/v1/tools/helpline?make={{args.make}}",
                    "timeout_ms": 10000,
                },
            })

        return (
            Agent(
                client=self._client,
                turn_detection={
                    "config": {
                        "speech_threshold": 0.5,
                        "start_of_speech": {
                            "mode": "vad",
                            "vad_config": {
                                # 160 ms let car/background noise cut the agent off mid-word.
                                "interrupt_duration_ms": 450,
                                "prefix_padding_ms": 800,
                            },
                        },
                        "end_of_speech": {
                            "mode": "vad",
                            "vad_config": {"silence_duration_ms": 640},
                        },
                    },
                },
                # Keyword barge-in: with start_of_speech, wordless noise (radio, road, a laptop) cut the
                # agent off mid-word. Real speech still interrupts via the app, which calls /interrupt
                # when ASR returns actual words while the agent is talking.
                interruption={
                    "enable": True,
                    "mode": "keywords",
                    "keywords_config": {"trigger_keywords": INTERRUPT_KEYWORDS},
                },
                filler_words={
                    # Disabled: with a generated filler, Agora never resumed the turn after a
                    # lookupManual result (filler held "speaking" until the user spoke again).
                    "enable": False,
                    "trigger": {
                        "mode": "fixed_time",
                        "fixed_time_config": {"response_wait_ms": 1500},
                    },
                    "content": {
                        "mode": "generated",
                        "static_config": {
                            "phrases": [
                                "Let me think that through.",
                                "One moment, please.",
                                "Give me a moment.",
                                "I'm working on that.",
                            ],
                            "selection_rule": "shuffle",
                        },
                        "generated_config": {
                            "prompt": "Briefly acknowledge that you are processing the request. Do not answer it or claim to have performed any action.",
                            "fallback_strategy": "static",
                        },
                    },
                },
                advanced_features={"enable_rtm": True, "enable_tools": bool(tools)},
                parameters={
                    "audio_scenario": "chorus",
                    "data_channel": "rtm",
                    "enable_error_message": True,
                    "enable_metrics": True,
                },
            )
            .with_stt(DeepgramSTT(model=self.settings.asr_model, language="en"))
            .with_llm(
                OpenAI(
                    model=self.settings.llm_model,
                    system_messages=[
                        {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT}
                    ],
                    greeting_message="Hi, I am your dashboard assistant. Which car are you driving, and what light are you seeing?",
                    failure_message="Please wait a moment.",
                    max_history=15,
                    **self._sampling_options(),
                    tools=tools or None,
                    # The app publishes its rear camera over RTC; Agora forwards the latest frame to the LLM.
                    input_modalities=["text", "image"],
                )
            )
            .with_tts(self._build_tts())
        )

    def _sampling_options(self) -> dict[str, Any]:
        """gpt-5 models are reasoning models: they reject temperature/top_p and count reasoning
        against max_completion_tokens, so give them minimal reasoning and room for a short reply."""
        if self.settings.llm_model.startswith("gpt-5"):
            return {"params": {"reasoning_effort": "minimal", "verbosity": "low", "max_completion_tokens": 400}}
        return {"max_tokens": 160, "temperature": 0.7, "top_p": 0.95}  # ~35 spoken words

    def _build_tts(self):
        # OpenAI tts-1 (Agora-managed) reads whole sentences fluently; MiniMax character voices
        # sounded slow and stop-and-go on long replies.
        if self.settings.tts_vendor == "elevenlabs":
            if not self.settings.elevenlabs_api_key:
                raise ValueError("TTS_VENDOR=elevenlabs needs ELEVENLABS_API_KEY in server/.env.local.")
            # Flash v2.5 is ElevenLabs' low-latency model; no speed control via Agora, so pick the voice for pace.
            return ElevenLabsTTS(
                key=self.settings.elevenlabs_api_key,
                model_id=self.settings.elevenlabs_model,
                voice_id=self.settings.tts_voice_id,
                base_url="wss://api.elevenlabs.io/v1",
                stability=0.5,
                similarity_boost=0.75,
                skip_patterns=SKIP_CURLY_BRACES,
            )
        if self.settings.tts_vendor == "openai":
            return OpenAITTS(model="tts-1", voice=self.settings.tts_voice_id, speed=self.settings.tts_speed, skip_patterns=SKIP_CURLY_BRACES)
        return MiniMaxTTS(
            model=self.settings.tts_model,
            voice_id=self.settings.tts_voice_id,
            speed=self.settings.tts_speed,
        )

    async def join_agent(
        self,
        channel_name: str,
        requester_rtc_uid: int,
        agent_profile: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        session = self._build_agent(system_prompt).create_async_session(
            channel=channel_name,
            agent_uid=str(self.settings.agent_uid),
            remote_uids=[str(requester_rtc_uid)],
            name=f"android-server-agent-{int(time.time())}-{secrets.randbelow(9000) + 1000}",
            idle_timeout=30,
            preset=agent_profile,
            expires_in=self.settings.token_expiry_seconds,
            debug=False,
        )
        try:
            agent_id = await session.start()
        except httpx.TimeoutException as exc:
            raise AgoraTimeoutError("Agora request timed out.") from exc
        except (ApiError, httpx.HTTPError, RuntimeError, ValueError) as exc:
            raise AgoraUpstreamError(f"Agora Conversational AI start failed: {exc}") from exc
        if not agent_id:
            raise AgoraUpstreamError("Agora response did not include agent_id.")
        self._sessions[agent_id] = (channel_name, session)
        return {
            "agent_id": agent_id,
            "create_ts": int(time.time()),
            "status": "started",
        }

    async def interrupt_agent(self, agent_id: str, channel_name: str) -> None:
        session = self._require_session(agent_id, channel_name)
        try:
            await session.interrupt()
        except httpx.TimeoutException as exc:
            raise AgoraTimeoutError("Agora interrupt request timed out.") from exc
        except (ApiError, httpx.HTTPError, RuntimeError) as exc:
            raise AgoraUpstreamError(f"Agora agent interrupt failed: {exc}") from exc

    async def speak(self, agent_id: str, channel_name: str, text: str, priority: str, interruptable: bool) -> None:
        session = self._require_session(agent_id, channel_name)
        try:
            await session.say(text, priority=priority, interruptable=interruptable)
        except httpx.TimeoutException as exc:
            raise AgoraTimeoutError("Agora speech request timed out.") from exc
        except (ApiError, httpx.HTTPError, RuntimeError, ValueError) as exc:
            raise AgoraUpstreamError(f"Agora speech request failed: {exc}") from exc

    async def think(self, agent_id: str, channel_name: str, text: str, on_listening_action: str, on_thinking_action: str, on_speaking_action: str, interruptable: bool) -> None:
        session = self._require_session(agent_id, channel_name)
        try:
            await session.think(
                text,
                on_listening_action=on_listening_action,
                on_thinking_action=on_thinking_action,
                on_speaking_action=on_speaking_action,
                interruptable=interruptable,
            )
        except httpx.TimeoutException as exc:
            raise AgoraTimeoutError("Agora instruction request timed out.") from exc
        except (ApiError, httpx.HTTPError, RuntimeError, ValueError) as exc:
            raise AgoraUpstreamError(f"Agora instruction request failed: {exc}") from exc

    async def leave_agent(self, agent_id: str, channel_name: str) -> None:
        """Returns at once; saving the transcript and stopping the agent (2-3 s of Agora calls)
        run in the background so the app's stop button feels instant."""
        session = self._require_session(agent_id, channel_name)
        self._sessions.pop(agent_id, None)
        task = asyncio.create_task(self._save_and_stop(agent_id, session))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _save_and_stop(self, agent_id: str, session: Any) -> None:
        out_dir = await self._save_transcript(agent_id, session)  # history is only served while the agent runs
        try:
            await session.stop()
        except Exception as exc:  # the idle timeout stops it anyway
            print(f"[agent] stop failed for {agent_id}: {exc}", flush=True)
        if out_dir is not None:
            await self._save_turn_metrics(agent_id, session, out_dir)

    @staticmethod
    async def _save_turn_metrics(agent_id: str, session: Any, out_dir: Path) -> None:
        """Per-turn latency (ASR, LLM, TTS, end to end) is only served once the agent has stopped."""
        for _ in range(5):
            await asyncio.sleep(3)
            try:
                result = await session.get_turns()
                data = result.dict() if hasattr(result, "dict") else result
                (out_dir / "turns.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
                return
            except Exception as exc:
                error = exc
        print(f"[transcript] no turn metrics for {agent_id}: {str(error)[:200]}", flush=True)

    async def _save_transcript(self, agent_id: str, session: Any) -> Path | None:
        """Keep each call's history (and the camera frames the LLM saw) in server/transcripts/,
        because Agora only serves history while the agent is running."""
        try:
            data = await self._history_of(session)
            out_dir = TRANSCRIPT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{agent_id[:8]}"
            out_dir.mkdir(parents=True, exist_ok=True)
            frame = 0
            for entry in (data.get("history") or {}).get("contents") or []:
                if not isinstance(entry.get("content"), list):
                    continue
                for part in entry["content"]:
                    image = part.get("image_url") if isinstance(part, dict) else None
                    url = image.get("url") if isinstance(image, dict) else image
                    if isinstance(url, str) and url.startswith("data:image"):
                        frame += 1
                        (out_dir / f"frame{frame}.jpg").write_bytes(base64.b64decode(url.split(",", 1)[1]))
                        part["image_url"] = f"frame{frame}.jpg"
            (out_dir / "history.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
            return out_dir
        except Exception as exc:  # never block leaving a call on this
            print(f"[transcript] could not save {agent_id}: {exc}", flush=True)
            return None

    async def debug_history(self, agent_id: str) -> dict[str, Any]:
        """Conversation history and turn analytics for a session this server started (debugging)."""
        if agent_id not in self._sessions:
            raise AgoraUpstreamError("Unknown agent_id; only sessions started by this server process are available.")
        return await self._history_of(self._sessions[agent_id][1])

    @staticmethod
    async def _history_of(session: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, call in (("info", session.get_info), ("history", session.get_history), ("turns", session.get_turns)):
            try:
                result = await call()
                out[name] = result.dict() if hasattr(result, "dict") else result
            except Exception as exc:  # report every part, even if one fails
                out[name] = {"error": str(exc)[:500]}
        return out

    def _require_session(self, agent_id: str, channel_name: str) -> Any:
        active = self._sessions.get(agent_id)
        if active is None or active[0] != channel_name:
            raise AgoraUpstreamError("The Agora agent session is not active in this server process.")
        return active[1]

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()
