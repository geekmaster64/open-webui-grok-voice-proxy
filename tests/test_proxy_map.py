#!/usr/bin/env python3
"""Pure mapping tests — no network, no API key, no third-party packages."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "proxy"))

from mapping import (  # noqa: E402
    DEFAULT_STT_MODEL,
    clamp_speed,
    extra_keyterms_from_prompt,
    map_codec,
    map_voice,
    multipart_body,
    openai_speech_to_xai_tts,
    parse_keyterms,
    stt_form_fields,
)


class MapTests(unittest.TestCase):
    def test_openai_voices_become_ara_by_default_alloy(self):
        self.assertEqual(map_voice("alloy"), "ara")

    def test_ara_passthrough(self):
        self.assertEqual(map_voice("ara"), "ara")
        self.assertEqual(map_voice("Ara"), "Ara")

    def test_empty_voice_default(self):
        self.assertEqual(map_voice(None), "ara")
        self.assertEqual(map_voice(""), "ara")

    def test_codec_map(self):
        self.assertEqual(map_codec("mp3"), "mp3")
        self.assertEqual(map_codec("opus"), "mp3")
        self.assertEqual(map_codec(None), "mp3")

    def test_speed_clamp(self):
        self.assertEqual(clamp_speed(1.0), 1.0)
        self.assertEqual(clamp_speed(0.1), 0.7)
        self.assertEqual(clamp_speed(9), 1.5)
        self.assertIsNone(clamp_speed(None))

    def test_speech_payload(self):
        payload, codec = openai_speech_to_xai_tts(
            {"input": "Hello from Hexxus.", "voice": "alloy", "response_format": "mp3", "speed": 1.0}
        )
        self.assertEqual(codec, "mp3")
        self.assertEqual(payload["text"], "Hello from Hexxus.")
        self.assertEqual(payload["voice_id"], "ara")
        self.assertEqual(payload["language"], "en")
        self.assertEqual(payload["output_format"]["codec"], "mp3")
        self.assertEqual(payload["output_format"]["sample_rate"], 44100)
        self.assertEqual(payload["output_format"]["bit_rate"], 128000)
        self.assertIn("optimize_streaming_latency", payload)
        self.assertTrue(payload["text_normalization"])

    def test_explicit_24000_is_honored(self):
        payload, codec = openai_speech_to_xai_tts(
            {"input": "Hello.", "voice": "ara"},
            sample_rate=24000,
            bit_rate=128000,
        )
        self.assertEqual(codec, "mp3")
        self.assertEqual(payload["output_format"]["sample_rate"], 24000)

    def test_mp3_invalid_rate_falls_back_to_44100(self):
        payload, _ = openai_speech_to_xai_tts(
            {"input": "Hello.", "voice": "ara"},
            sample_rate=12345,
            bit_rate=1,
        )
        self.assertEqual(payload["output_format"]["sample_rate"], 44100)
        self.assertEqual(payload["output_format"]["bit_rate"], 128000)

    def test_wav_omits_bit_rate(self):
        payload, codec = openai_speech_to_xai_tts(
            {"input": "Hello.", "voice": "ara", "response_format": "wav"},
            sample_rate=44100,
        )
        self.assertEqual(codec, "wav")
        self.assertEqual(payload["output_format"], {"codec": "wav", "sample_rate": 44100})

    def test_text_normalization_can_be_disabled(self):
        payload, _ = openai_speech_to_xai_tts(
            {"input": "Call me at 5."},
            text_normalization=False,
        )
        self.assertFalse(payload["text_normalization"])

    def test_stt_fields_pin_model_and_keyterms_before_file(self):
        fields = stt_form_fields(
            language="en",
            keyterms=["Grok", "Ara", "Open WebUI", "Hexxus", "grok"],
        )
        names = [name for name, _ in fields]
        self.assertEqual(fields[0], ("model", DEFAULT_STT_MODEL))
        self.assertEqual(fields[1], ("language", "en"))
        self.assertEqual(fields[2], ("format", "true"))
        self.assertIn(("filler_words", "false"), fields)
        self.assertEqual(names.count("keyterm"), 4)
        self.assertEqual(
            [value for name, value in fields if name == "keyterm"],
            ["Grok", "Ara", "Open WebUI", "Hexxus"],
        )
        body, _ = multipart_body(fields, "clip.webm", "audio/webm", b"WEBM")
        self.assertLess(body.find(b'name="model"'), body.find(b'name="file"'))
        self.assertLess(body.find(b'name="keyterm"'), body.find(b'name="file"'))

    def test_stt_format_omitted_without_language(self):
        fields = stt_form_fields(language=None, keyterms=["Grok"])
        self.assertNotIn("language", dict(fields))
        self.assertNotIn("format", dict(fields))
        self.assertIn(("keyterm", "Grok"), fields)

    def test_parse_keyterms_defaults_and_empty(self):
        self.assertEqual(parse_keyterms(None)[0], "Grok")
        self.assertEqual(parse_keyterms(""), [])
        self.assertEqual(parse_keyterms("Grok, Ara, Grok"), ["Grok", "Ara"])

    def test_whisper_prompt_becomes_keyterms(self):
        self.assertEqual(
            extra_keyterms_from_prompt("Hexxus, grok-4"),
            ["Hexxus", "grok-4"],
        )

    def test_multipart_puts_file_last(self):
        body, header = multipart_body(
            [("language", "en"), ("format", "true")],
            "clip.mp3",
            "audio/mpeg",
            b"ID3FAKE",
        )
        self.assertIn("multipart/form-data; boundary=", header)
        self.assertLess(body.find(b'name="language"'), body.find(b'name="file"'))
        self.assertTrue(body.endswith(b"--\r\n") or b"--xaiProxyFormBoundary--" in body)
        self.assertIn(b"ID3FAKE", body)


if __name__ == "__main__":
    unittest.main()
