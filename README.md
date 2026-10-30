# Open WebUI Grok Voice Proxy

OpenAI-compatible **TTS and STT proxy** so [Open WebUI](https://github.com/open-webui/open-webui) Talk mode can use **xAI Grok voices** (Ara, Eve, Leo, Rex, Sal).

Open WebUI speaks OpenAI audio:

- `POST /v1/audio/speech`
- `POST /v1/audio/transcriptions`

xAI’s native endpoints are different:

- `POST https://api.x.ai/v1/tts`
- `POST https://api.x.ai/v1/stt`

This proxy sits on `127.0.0.1:8787` and translates between them. Chat completions still go straight to `https://api.x.ai/v1`.

## Why this exists

- Open WebUI Talk mode expects OpenAI TTS/STT, not xAI’s native JSON.
- xAI’s default MP3 is **24 kHz MPEG-2**, which Safari / CarPlay Talk mode plays as ~0.5s of silence. The chat **speaker icon** still works. This proxy requests **44.1 kHz MPEG-1** MP3 instead.
- After Open WebUI 0.11, Talk mode on Safari also treats `pause` as end-of-clip and shares `#audioElement` with the global audio queue. `open-webui-patches/loader.js` plays Talk-mode clips through Web Audio after the mic is on.

## Quick start

```bash
python3 -m venv /opt/xai-proxy/venv
/opt/xai-proxy/venv/bin/pip install -r proxy/requirements.txt
cp proxy/.env.example /opt/xai-proxy/.env   # add XAI_API_KEY
chmod 600 /opt/xai-proxy/.env
# install proxy/xai_audio_proxy.py, mapping.py, systemd/xai-audio-proxy.service
sudo systemctl enable --now xai-audio-proxy
curl -sS http://127.0.0.1:8787/health
```

In Open WebUI **Admin → Settings → Audio**:

| Setting | Value |
| --- | --- |
| Speech-to-Text engine | OpenAI |
| STT API Base URL | `http://127.0.0.1:8787/v1` |
| Text-to-Speech engine | OpenAI |
| TTS API Base URL | `http://127.0.0.1:8787/v1` |
| TTS Voice | `ara` |
| TTS Model | `tts-1` |
| Split on | punctuation |

Point the Open WebUI container at host loopback (this repo uses `network_mode: host` + `HOST=127.0.0.1`) so `http://127.0.0.1:8787/v1` works from inside Docker.

## xAI options this proxy sets

| Setting | Default | Why |
| --- | --- | --- |
| TTS `output_format` | MP3 44.1 kHz / 128 kbps | Safari / CarPlay Talk mode. xAI’s 24 kHz default is MPEG-2. |
| TTS `text_normalization` | `true` | Speak numbers, dates, and abbreviations in spoken form. |
| TTS `optimize_streaming_latency` | `1` | Lower time-to-first-audio for Talk mode. |
| STT `model` | `grok-voice-transcribe-2.0` | Pin the current transcription model. |
| STT `keyterm` | `Grok`, `Ara`, `Open WebUI`, `Hexxus` | Bias short Talk-mode clips toward those names. Open WebUI’s Whisper `prompt` is appended. |
| STT `format` | `true` when `language` is set | Inverse text normalization. xAI requires `language` for this. |
| STT `filler_words` | `false` | Drop uh/um from the transcript. |

Override with `TTS_TEXT_NORMALIZATION`, `STT_MODEL`, and `STT_KEYTERMS` in `/opt/xai-proxy/.env`.

## Voice map

OpenAI voice names are mapped to Grok voices: alloy/ash/sage → **ara**, nova/shimmer/coral → **eve**, echo/verse → **leo**, onyx → **rex**, fable → **sal**. Names like `ara` pass through.

## Safari / CarPlay Talk mode

If the speaker icon plays Ara but Talk mode is silent or repeats the previous reply on Safari:

1. Serve `open-webui-patches/loader.js` as `/hexxus-talk-tts-webaudio-2.js` (see `nginx/open-webui.conf`).
2. Inject it in the Open WebUI HTML `<head>`.
3. Bind-mount the same file over `/app/backend/open_webui/static/loader.js` if you want it inside the container too.

Close the Safari tab fully after installing (a refresh is not enough).

## Layout

| Path | What |
| --- | --- |
| `proxy/` | OpenAI → xAI audio gateway |
| `open-webui-patches/` | Safari Talk-mode playback fix |
| `compose/` | Open WebUI `main-slim`, host networking |
| `nginx/` | TLS + WebSocket reverse proxy |
| `systemd/` | `xai-audio-proxy.service` |
| `ansible/` `terraform/` | Optional VM / OS install |

Do not commit `proxy/.env`. Copy `.env.example` and put the xAI key only on the server.
