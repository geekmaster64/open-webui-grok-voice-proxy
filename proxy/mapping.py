"""OpenAI audio request → xAI TTS payload. No third-party imports."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_VOICE = "ara"
DEFAULT_LANGUAGE = "en"
DEFAULT_STT_MODEL = "grok-voice-transcribe-2.0"
DEFAULT_STT_KEYTERMS = ("Grok", "Ara", "Open WebUI", "Hexxus")
MAX_STT_KEYTERMS = 100
MAX_STT_KEYTERM_CHARS = 50

# xAI defaults to 24 kHz MP3 (MPEG-2 Layer III). Safari/CarPlay talk mode
# cannot play that: each clip shows as ~0.5s of silence, then the UI waits
# for the user. The chat speaker icon still works because it uses a normal
# <audio> element. 44.1 kHz is MPEG-1 Layer III, which iOS plays correctly.
DEFAULT_MP3_SAMPLE_RATE = 44100
DEFAULT_MP3_BIT_RATE = 128000
VALID_SAMPLE_RATES = {8000, 16000, 22050, 24000, 44100, 48000}
VALID_MP3_BIT_RATES = {32000, 64000, 96000, 128000, 192000}

OPENAI_VOICE_MAP = {
    "alloy": "ara",
    "ash": "ara",
    "ballad": "eve",
    "coral": "eve",
    "echo": "leo",
    "fable": "sal",
    "nova": "eve",
    "onyx": "rex",
    "sage": "ara",
    "shimmer": "eve",
    "verse": "leo",
}

OPENAI_TO_XAI_CODEC = {
    "mp3": "mp3",
    "wav": "wav",
    "pcm": "pcm",
    "mulaw": "mulaw",
    "ulaw": "mulaw",
    "alaw": "alaw",
    "opus": "mp3",
    "aac": "mp3",
    "flac": "wav",
}

CODEC_CONTENT_TYPE = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
    "mulaw": "audio/basic",
    "alaw": "audio/alaw",
}

XAI_VOICE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,63}$")


def map_voice(voice: str | None, default: str = DEFAULT_VOICE) -> str:
    if not voice:
        return default
    key = voice.strip()
    mapped = OPENAI_VOICE_MAP.get(key.lower())
    if mapped:
        return mapped
    if XAI_VOICE_RE.match(key):
        return key
    return default


def map_codec(response_format: str | None) -> str:
    if not response_format:
        return "mp3"
    return OPENAI_TO_XAI_CODEC.get(response_format.lower(), "mp3")


def clamp_speed(speed: Any) -> float | None:
    if speed is None or speed == "":
        return None
    try:
        value = float(speed)
    except (TypeError, ValueError):
        return None
    return max(0.7, min(1.5, value))


def _int_choice(value: Any, allowed: set[int], default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed in allowed else default


def output_format_for(
    codec: str,
    *,
    sample_rate: int | None = None,
    bit_rate: int | None = None,
) -> dict[str, Any]:
    fmt: dict[str, Any] = {"codec": codec}
    if codec == "mp3":
        fmt["sample_rate"] = _int_choice(sample_rate, VALID_SAMPLE_RATES, DEFAULT_MP3_SAMPLE_RATE)
        fmt["bit_rate"] = _int_choice(bit_rate, VALID_MP3_BIT_RATES, DEFAULT_MP3_BIT_RATE)
    elif sample_rate is not None:
        fmt["sample_rate"] = _int_choice(sample_rate, VALID_SAMPLE_RATES, DEFAULT_MP3_SAMPLE_RATE)
    return fmt


def openai_speech_to_xai_tts(
    body: dict[str, Any],
    *,
    default_voice: str = DEFAULT_VOICE,
    default_language: str = DEFAULT_LANGUAGE,
    optimize_streaming_latency: int = 1,
    sample_rate: int | None = None,
    bit_rate: int | None = None,
    text_normalization: bool = True,
) -> tuple[dict[str, Any], str]:
    text = body.get("input") or body.get("text") or ""
    if not isinstance(text, str):
        text = str(text)
    codec = map_codec(body.get("response_format") or body.get("format"))
    language = body.get("language") or default_language
    payload: dict[str, Any] = {
        "text": text,
        "voice_id": map_voice(body.get("voice"), default_voice),
        "language": language,
        "output_format": output_format_for(codec, sample_rate=sample_rate, bit_rate=bit_rate),
        "optimize_streaming_latency": optimize_streaming_latency,
        "text_normalization": bool(text_normalization),
    }
    speed = clamp_speed(body.get("speed"))
    if speed is not None:
        payload["speed"] = speed
    return payload, codec


def parse_keyterms(value: str | None, defaults: tuple[str, ...] = DEFAULT_STT_KEYTERMS) -> list[str]:
    """Split a comma/newline env list. Empty string means no keyterms."""
    if value is None:
        return normalize_keyterms(defaults)
    return normalize_keyterms(re.split(r"[,;\n]+", value))


def extra_keyterms_from_prompt(prompt: str | None) -> list[str]:
    """Map OpenAI Whisper `prompt` onto xAI `keyterm` fields."""
    if not prompt:
        return []
    return normalize_keyterms(re.split(r"[,;\n]+", prompt))


def normalize_keyterms(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    if values is None:
        return out
    if isinstance(values, str):
        values = [values]
    for raw in values:
        term = str(raw).strip()
        if not term:
            continue
        term = term[:MAX_STT_KEYTERM_CHARS]
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
        if len(out) >= MAX_STT_KEYTERMS:
            break
    return out


def stt_form_fields(
    *,
    language: str | None = None,
    model: str = DEFAULT_STT_MODEL,
    keyterms: list[str] | None = None,
    filler_words: bool = False,
) -> list[tuple[str, str]]:
    """Option fields for POST /v1/stt. Caller appends `file` last."""
    fields: list[tuple[str, str]] = [("model", (model or DEFAULT_STT_MODEL).strip() or DEFAULT_STT_MODEL)]
    if language:
        fields.append(("language", language))
        fields.append(("format", "true"))
    fields.append(("filler_words", "true" if filler_words else "false"))
    for term in normalize_keyterms(keyterms):
        fields.append(("keyterm", term))
    return fields


def multipart_body(
    fields: list[tuple[str, str]],
    filename: str,
    content_type: str,
    data: bytes,
) -> tuple[bytes, str]:
    """Build multipart/form-data bytes. xAI requires `file` last."""
    boundary = "----xaiProxyFormBoundary"
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "") or "audio"
    chunks: list[bytes] = []
    for name, value in fields:
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                f"\r\n{value}\r\n"
            ).encode("utf-8")
        )
    chunks.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
            f"Content-Type: {content_type}\r\n"
            f"\r\n"
        ).encode("utf-8")
    )
    chunks.append(data)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
