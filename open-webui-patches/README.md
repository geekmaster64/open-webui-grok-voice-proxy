# Open WebUI talk-mode TTS patch

Talk mode skipped every Ara clip (~0.5s silence). The speaker icon still worked.

Safari-specific: the speaker icon `play()` runs inside a tap. Talk-mode TTS runs later, so Safari will not play a detached `Audio()` object. Unlock `#audioElement` on tap, keep using that element, ignore pause-as-ended, and ignore AudioQueue halt while a talk clip is playing.

`loader.js` is bind-mounted as `/static/loader.js` and injected by nginx as `/hexxus-talk-tts-webaudio-2.js` (`Cache-Control: no-store`) so Safari cannot keep an empty or stale copy.
