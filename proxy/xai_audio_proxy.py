#!/usr/bin/env python3
"""OpenAI-compatible audio gateway in front of xAI TTS/STT.

Open WebUI talks OpenAI:
  POST /v1/audio/speech
  POST /v1/audio/transcriptions

xAI native endpoints are different:
  POST https://api.x.ai/v1/tts    JSON {text, voice_id, language, ...} → audio bytes
  POST https://api.x.ai/v1/stt    multipart file → {text, language, duration, words}

Listens on 127.0.0.1:8787. Inference stays on api.x.ai.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

from mapping import (
    CODEC_CONTENT_TYPE,
    DEFAULT_STT_MODEL,
    extra_keyterms_from_prompt,
    multipart_body,
    openai_speech_to_xai_tts,
    parse_keyterms,
    stt_form_fields,
)

load_dotenv(Path(__file__).resolve().parent / ".env")

log = logging.getLogger("xai-audio-proxy")

LISTEN_HOST = os.environ.get("PROXY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "8787"))
XAI_BASE_URL = os.environ.get("XAI_BASE_URL", "https://api.x.ai").rstrip("/")
XAI_API_KEY = os.environ.get("XAI_API_KEY", "").strip()
DEFAULT_VOICE = os.environ.get("TTS_DEFAULT_VOICE", "ara")
DEFAULT_LANGUAGE = os.environ.get("TTS_DEFAULT_LANGUAGE", "en")
OPTIMIZE_STREAMING_LATENCY = int(os.environ.get("TTS_OPTIMIZE_STREAMING_LATENCY", "1"))
TTS_SAMPLE_RATE = int(os.environ.get("TTS_SAMPLE_RATE", "44100"))
TTS_BIT_RATE = int(os.environ.get("TTS_BIT_RATE", "128000"))
TTS_TEXT_NORMALIZATION = os.environ.get("TTS_TEXT_NORMALIZATION", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
STT_MODEL = os.environ.get("STT_MODEL", DEFAULT_STT_MODEL).strip() or DEFAULT_STT_MODEL
STT_KEYTERMS = parse_keyterms(os.environ.get("STT_KEYTERMS"))

http_client: httpx.AsyncClient | None = None


def _require_key() -> str | JSONResponse:
    if not XAI_API_KEY:
        return JSONResponse(
            {"error": {"message": "XAI_API_KEY is not set", "type": "auth_error"}},
            status_code=500,
        )
    return XAI_API_KEY


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


@asynccontextmanager
async def lifespan(_app: Starlette):
    global http_client
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=180.0, write=60.0, pool=10.0),
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        http2=True,
        follow_redirects=True,
    )
    log.info(
        "xAI audio proxy listening on %s:%s → %s (voice=%s)",
        LISTEN_HOST,
        LISTEN_PORT,
        XAI_BASE_URL,
        DEFAULT_VOICE,
    )
    try:
        yield
    finally:
        await http_client.aclose()
        http_client = None


async def health(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "upstream": XAI_BASE_URL,
            "default_voice": DEFAULT_VOICE,
            "has_api_key": bool(XAI_API_KEY),
            "text_normalization": TTS_TEXT_NORMALIZATION,
            "stt_model": STT_MODEL,
            "stt_keyterms": STT_KEYTERMS,
        }
    )


async def list_models(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "object": "list",
            "data": [
                {"id": "tts-1", "object": "model", "owned_by": "xai"},
                {"id": "tts-1-hd", "object": "model", "owned_by": "xai"},
                {"id": "whisper-1", "object": "model", "owned_by": "xai"},
                {"id": "grok-tts", "object": "model", "owned_by": "xai"},
                {"id": "grok-stt", "object": "model", "owned_by": "xai"},
            ],
        }
    )


async def speech(request: Request) -> Response:
    key = _require_key()
    if isinstance(key, JSONResponse):
        return key
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": {"message": "request body must be JSON", "type": "invalid_request_error"}},
            status_code=400,
        )
    if not isinstance(body, dict):
        return JSONResponse(
            {"error": {"message": "request body must be a JSON object", "type": "invalid_request_error"}},
            status_code=400,
        )
    text = body.get("input") or body.get("text") or ""
    if not text:
        return JSONResponse(
            {"error": {"message": "missing input text", "type": "invalid_request_error"}},
            status_code=400,
        )
    payload, codec = openai_speech_to_xai_tts(
        body,
        default_voice=DEFAULT_VOICE,
        default_language=DEFAULT_LANGUAGE,
        optimize_streaming_latency=OPTIMIZE_STREAMING_LATENCY,
        sample_rate=TTS_SAMPLE_RATE,
        bit_rate=TTS_BIT_RATE,
        text_normalization=TTS_TEXT_NORMALIZATION,
    )
    assert http_client is not None
    url = f"{XAI_BASE_URL}/v1/tts"
    try:
        req = http_client.build_request(
            "POST",
            url,
            headers={**_auth_headers(key), "Content-Type": "application/json"},
            json=payload,
        )
        upstream = await http_client.send(req, stream=True)
    except httpx.RequestError as exc:
        log.exception("TTS upstream error")
        return JSONResponse(
            {"error": {"message": f"xAI TTS request failed: {exc}", "type": "upstream_error"}},
            status_code=502,
        )

    if upstream.status_code >= 400:
        err_body = await upstream.aread()
        await upstream.aclose()
        log.warning("TTS upstream %s: %s", upstream.status_code, err_body[:500])
        try:
            parsed = json.loads(err_body)
        except json.JSONDecodeError:
            parsed = {"error": {"message": err_body.decode("utf-8", "replace"), "type": "upstream_error"}}
        return JSONResponse(parsed, status_code=upstream.status_code)

    async def stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                if chunk:
                    yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        stream(),
        media_type=CODEC_CONTENT_TYPE.get(codec, "application/octet-stream"),
        headers={"Cache-Control": "no-store"},
    )


def _form_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)





async def transcriptions(request: Request) -> Response:
    key = _require_key()
    if isinstance(key, JSONResponse):
        return key
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        return JSONResponse(
            {"error": {"message": "missing file", "type": "invalid_request_error"}},
            status_code=400,
        )
    filename = getattr(upload, "filename", None) or "audio.webm"
    content_type = getattr(upload, "content_type", None) or "application/octet-stream"
    data = await upload.read()  # type: ignore[union-attr]
    if not data:
        return JSONResponse(
            {"error": {"message": "empty audio file", "type": "invalid_request_error"}},
            status_code=400,
        )

    response_format = (_form_str(form.get("response_format")) or "json").lower()
    language = _form_str(form.get("language"))
    prompt = _form_str(form.get("prompt"))

    # xAI wants option fields before file.
    fields = stt_form_fields(
        language=language,
        model=STT_MODEL,
        keyterms=STT_KEYTERMS + extra_keyterms_from_prompt(prompt),
        filler_words=False,
    )

    assert http_client is not None
    url = f"{XAI_BASE_URL}/v1/stt"
    body, content_type_header = multipart_body(fields, filename, content_type, data)
    try:
        req = http_client.build_request(
            "POST",
            url,
            headers={**_auth_headers(key), "Content-Type": content_type_header},
            content=body,
        )
        upstream = await http_client.send(req)
    except httpx.RequestError as exc:
        log.exception("STT upstream error")
        return JSONResponse(
            {"error": {"message": f"xAI STT request failed: {exc}", "type": "upstream_error"}},
            status_code=502,
        )

    if upstream.status_code >= 400:
        log.warning("STT upstream %s: %s", upstream.status_code, upstream.content[:500])
        try:
            parsed = upstream.json()
        except json.JSONDecodeError:
            parsed = {"error": {"message": upstream.text, "type": "upstream_error"}}
        return JSONResponse(parsed, status_code=upstream.status_code)

    try:
        result = upstream.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": {"message": "xAI STT returned non-JSON", "type": "upstream_error"}},
            status_code=502,
        )

    text = result.get("text", "")
    if response_format == "text":
        return PlainTextResponse(text)
    if response_format == "verbose_json":
        words = []
        for word in result.get("words") or []:
            words.append(
                {
                    "word": word.get("word") or word.get("text") or "",
                    "start": word.get("start", 0),
                    "end": word.get("end", 0),
                }
            )
        return JSONResponse(
            {
                "task": "transcribe",
                "language": result.get("language") or language or "en",
                "duration": result.get("duration"),
                "text": text,
                "words": words,
            }
        )
    return JSONResponse({"text": text})


async def not_implemented(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "message": f"{request.method} {request.url.path} is not implemented on this gateway",
                "type": "invalid_request_error",
            }
        },
        status_code=404,
    )


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/v1/models", list_models, methods=["GET"]),
    Route("/v1/audio/speech", speech, methods=["POST"]),
    Route("/v1/audio/transcriptions", transcriptions, methods=["POST"]),
    Route("/{path:path}", not_implemented, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
]

app = Starlette(debug=False, routes=routes, lifespan=lifespan)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not XAI_API_KEY:
        log.warning("XAI_API_KEY is empty — /health will work, speech/transcriptions will 500")
    uvicorn.run(
        app,
        host=LISTEN_HOST,
        port=LISTEN_PORT,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
