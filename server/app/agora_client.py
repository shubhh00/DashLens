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


DEFAULT_SYSTEM_PROMPT = """You are a hands-free car dashboard assistant talking to a driver. Sound like a calm co-driver.
BREVITY: at most two short spoken sentences, about 35 words, even when many lamps are lit. Give the verdict and the one thing to do; the driver can ask for more. Plain speech only: no lists, no markdown, no symbols.

CAR AND MANUAL
- As soon as you know the car's make and model, call lookupManual before explaining any lamp. A brand or a year alone is not enough: ask which model.
- If the display shows the car's name or model picture, you may guess the car, but confirm it out loud first.
- Source "manual": answer only from its lamps. Source "none": confirm the model name in case it was misheard, then give brief general guidance and say it is general.

CAMERA (the latest frame of the driver's camera comes with each message)
- If the display shows a written warning message (for example "Instrument cluster malfunction, contact Service" or "Drivetrain malfunction, drive moderately"), read it out first: it is the car telling you exactly what is wrong.
- When the driver asks about lights or says look, check the rev counter and gear. If revs read zero or the gear shows P, the engine is off: say the red lamps are the normal self-check that clears once the engine starts, and name only the ones that still matter while parked, such as an unfastened seat belt or the parking brake. Never tell a parked driver to pull over. Suggest starting the engine and showing you again.
- With the engine running, name the lamps you actually see by shape and colour, most urgent first. Only mention lamps you can see. If the frame is blurry or far away, ask them to hold the phone steady and closer.
- Icons are small; identify them by shape before naming them. Commonly confused: seat belt = seated person with a diagonal belt across the chest; airbag = seated person with a large circle in front. Oil pressure = dripping oil can; battery = box with plus and minus; coolant = thermometer in waves; engine check = engine outline; tyre pressure = horseshoe with an exclamation mark; brake = circle with an exclamation mark or P in brackets; stability control = car with wavy skid lines.
- Green or blue icons (headlamps, turn signals, cruise, auto hold) are indicators, not faults; do not treat them as warnings.
- If you are not sure which lamp a shape is, say what shape you see and ask the driver to confirm instead of guessing.

WHEN IT IS UNCLEAR
- If more than one lamp could match a description, ask one short question about the symbol's shape instead of guessing; if any possible match means stop now, say that first.
- If a lamp means something different flashing and steady and you do not know which, ask.
- If the reported colour does not match the manual's lamp, say so and ask them to check again.

URGENT
- Rank what you see: a red brake, ABS, steering, oil pressure or overheating lamp while the car is moving (speedometer above zero or gear in D) outranks everything else. Give one clear verdict: either pull over now, or safe to continue and get it checked; never both in the same answer.
- If a lamp means stop now with the engine running, lead with: pull over safely and switch off the engine, then offer the roadside assistance number from lookupManual (roadside_number, with roadside_label saying whose line it is). Also give it whenever the driver asks for help, a tow or a helpline. Read it slowly in digit groups, for example one eight hundred, one oh two, four six four five. Never invent a number; if roadside_number is null, say you do not have a verified number for this brand.

Remember: two short sentences at most."""

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
                    "name": "getProjectGuidance",
                    "description": "Look up this Android quickstart's setup or troubleshooting instructions. Use for questions about configuring or debugging this project.",
                    "parameters": {
                        "type": "object",
                        "properties": {"topic": {"type": "string", "enum": ["setup", "troubleshooting"]}},
                        "required": ["topic"],
                        "additionalProperties": False,
                    },
                },
                "execution": {"mode": "sync"},
                "server": {
                    "method": "GET",
                    "url": self.settings.public_base_url.rstrip("/") + "/v1/tools/guidance?topic={{args.topic}}",
                    "timeout_ms": 5000,
                },
            })



    def _build_agent(self, system_prompt: str | None = None) -> Agent:
        tools = []
        if self.settings.public_base_url:
            tools.append({
                "type": "function",
                "function": {
                    "name": "getProjectGuidance",
                    "description": "Look up this Android quickstart's setup or troubleshooting instructions. Use for questions about configuring or debugging this project.",
                    "parameters": {
                        "type": "object",
                        "properties": {"topic": {"type": "string", "enum": ["setup", "troubleshooting"]}},
                        "required": ["topic"],
                        "additionalProperties": False,
                    },
                },
                "execution": {"mode": "sync"},
                "server": {
                    "method": "GET",
                    "url": self.settings.public_base_url.rstrip("/") + "/v1/tools/guidance?topic={{args.topic}}",
                    "timeout_ms": 5000,
                },
            })
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
                    max_tokens=160,  # safety net: spoken replies should be ~35 words
                    temperature=0.7,
                    top_p=0.95,
                    tools=tools or None,
                    # The app publishes its rear camera over RTC; Agora forwards the latest frame to the LLM.
                    input_modalities=["text", "image"],
                )
            )
            .with_tts(self._build_tts())
        )

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
            )
        if self.settings.tts_vendor == "openai":
            return OpenAITTS(model="tts-1", voice=self.settings.tts_voice_id, speed=self.settings.tts_speed)
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
        await self._save_transcript(agent_id, session)  # history is only served while the agent runs
        try:
            await session.stop()
        except Exception as exc:  # the idle timeout stops it anyway
            print(f"[agent] stop failed for {agent_id}: {exc}", flush=True)

    async def _save_transcript(self, agent_id: str, session: Any) -> None:
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
        except Exception as exc:  # never block leaving a call on this
            print(f"[transcript] could not save {agent_id}: {exc}", flush=True)

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
