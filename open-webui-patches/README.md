# Open WebUI talk-mode TTS patch

Talk mode skipped every Ara clip (~0.5s silence). The speaker icon still worked.

Safari-specific: the speaker icon `play()` runs inside a tap. Talk-mode TTS runs later, so Safari will not play a detached `Audio()` object. Unlock `#audioElement` on tap, keep using that element, ignore pause-as-ended, and ignore AudioQueue halt while a talk clip is playing.

`loader.js` is bind-mounted as `/static/loader.js` and injected by nginx as `/hexxus-talk-tts-webaudio-2.js` (`Cache-Control: no-store`) so Safari cannot keep an empty or stale copy.

Voice mode skips an unclosed code block, so that text is not read aloud. The speaker button already skips a finished block. Anything written after the block is spoken when the reply finishes. Copy `loader.js` to `/var/www/hexxus/talk-tts-fix.js` after editing it. The nginx file is the one Safari loads.

Set `audio.tts.split_on` to `none` to send the finished reply as one clip. `punctuation` speaks one sentence at a time. `paragraphs` speaks each paragraph as it completes.
