/* Safari talk-mode TTS via Web Audio.
 *
 * Do not read audio.currentSrc — Safari keeps the previous blob there because
 * we never load the new clip into the <audio> element, so turn 2 replayed
 * turn 1. Play the src that was just assigned. Fade in/out to avoid MP3 pops.
 */
(function () {
	if (window.__hexxusTalkTtsFix === 'safari-webaudio-2') return;
	window.__hexxusTalkTtsFix = 'safari-webaudio-2';

	var ctx = null;
	var activeSource = null;
	var activeGain = null;
	var playGen = 0;
	var FADE = 0.02;

	function audioCtx() {
		var Ctx = window.AudioContext || window.webkitAudioContext;
		if (!Ctx) return null;
		if (!ctx || ctx.state === 'closed') ctx = new Ctx();
		if (ctx.state === 'suspended') ctx.resume();
		return ctx;
	}

	function stopSource(fade) {
		var source = activeSource;
		var gain = activeGain;
		activeSource = null;
		activeGain = null;
		if (!source) return;
		try {
			source.onended = null;
			if (fade && gain && ctx) {
				var now = ctx.currentTime;
				gain.gain.cancelScheduledValues(now);
				gain.gain.setValueAtTime(gain.gain.value, now);
				gain.gain.linearRampToValueAtTime(0, now + FADE);
				source.stop(now + FADE);
			} else {
				source.stop();
			}
		} catch (e) {}
	}

	function decode(ac, buffer) {
		return new Promise(function (resolve, reject) {
			var copy = buffer.slice(0);
			var settled = false;
			function ok(decoded) {
				if (settled) return;
				settled = true;
				resolve(decoded);
			}
			function fail(err) {
				if (settled) return;
				settled = true;
				reject(err || new Error('decodeAudioData failed'));
			}
			try {
				var ret = ac.decodeAudioData(copy, ok, fail);
				if (ret && typeof ret.then === 'function') ret.then(ok, fail);
			} catch (err) {
				fail(err);
			}
		});
	}

	function playViaWebAudio(url) {
		var ac = audioCtx();
		if (!ac) return Promise.reject(new Error('no AudioContext'));
		var gen = ++playGen;
		stopSource(true);
		return ac.resume().then(function () {
			return fetch(url);
		}).then(function (res) {
			return res.arrayBuffer();
		}).then(function (buf) {
			return decode(ac, buf);
		}).then(function (decoded) {
			if (gen !== playGen) return;
			stopSource(false);
			var gain = ac.createGain();
			var source = ac.createBufferSource();
			source.buffer = decoded;
			source.connect(gain);
			gain.connect(ac.destination);
			var now = ac.currentTime;
			gain.gain.setValueAtTime(0, now);
			gain.gain.linearRampToValueAtTime(1, now + FADE);
			var dur = decoded.duration || 0;
			if (dur > FADE * 3) {
				gain.gain.setValueAtTime(1, now + dur - FADE);
				gain.gain.linearRampToValueAtTime(0, now + dur);
			}
			activeSource = source;
			activeGain = gain;
			return new Promise(function (resolve, reject) {
				source.onended = function () {
					if (gen !== playGen) return;
					if (activeSource === source) {
						activeSource = null;
						activeGain = null;
					}
					resolve();
				};
				try {
					// Skip a few ms of MP3 encoder padding that clicks on Safari.
					source.start(0, Math.min(0.008, Math.max(0, dur / 4)));
				} catch (err) {
					reject(err);
				}
			});
		});
	}

	function finishElement(el, ok) {
		try {
			if (ok && typeof el.onended === 'function') el.onended();
			else if (!ok && typeof el.onerror === 'function') el.onerror();
		} catch (e) {}
	}

	function clipUrl(el) {
		return el.__hexxusSrc || el.getAttribute('src') || '';
	}

	function attach(el) {
		if (!el || el.__hexxusWebAudioPlay === 2) return;
		el.__hexxusWebAudioPlay = 2;
		el.setAttribute('playsinline', '');
		el.setAttribute('webkit-playsinline', '');

		var desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
		if (desc && desc.set && desc.get) {
			Object.defineProperty(el, 'src', {
				configurable: true,
				enumerable: true,
				get: function () {
					return desc.get.call(el);
				},
				set: function (value) {
					el.__hexxusSrc = value ? String(value) : '';
					desc.set.call(el, value);
				}
			});
		}

		Object.defineProperty(el, 'onpause', {
			configurable: true,
			enumerable: true,
			get: function () {
				return null;
			},
			set: function () {}
		});

		var nativePlay = HTMLMediaElement.prototype.play.bind(el);
		el.play = function () {
			var url = clipUrl(el);
			var talkMode = el.muted && url && url.indexOf('blob:') === 0;
			if (!talkMode) return nativePlay();

			var gen = playGen + 1;
			playViaWebAudio(url)
				.then(function () {
					if (gen !== playGen) return;
					finishElement(el, true);
				})
				.catch(function () {
					if (gen !== playGen) return;
					el.muted = true;
					nativePlay()
						.then(function () {
							el.muted = false;
						})
						.catch(function () {
							finishElement(el, false);
						});
				});
			return Promise.resolve();
		};

		var nativePause = HTMLMediaElement.prototype.pause.bind(el);
		el.pause = function () {
			stopSource(true);
			return nativePause();
		};
	}

	function scan() {
		attach(document.getElementById('audioElement'));
	}

	function unlock() {
		try {
			audioCtx();
		} catch (e) {}
		scan();
	}

	if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
		var gum = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
		navigator.mediaDevices.getUserMedia = function (constraints) {
			return gum(constraints).then(function (stream) {
				unlock();
				return stream;
			});
		};
	}

	['pointerdown', 'touchstart', 'click'].forEach(function (type) {
		document.addEventListener(type, unlock, true);
	});

	scan();
	new MutationObserver(scan).observe(document.documentElement, {
		childList: true,
		subtree: true
	});
})();

/* Voice-mode TTS speaks each line as it arrives. An unclosed ``` block
 * is not skipped yet, so those lines get read aloud. The speaker button
 * waits until the reply is done and already skips a finished block.
 * Drop text from an unclosed fence. If the reply continues after the block,
 * speak that part when the reply finishes.
 */
(function () {
	if (window.__hexxusTtsSkipCode === 'skip-unclosed-fence-1') return;
	window.__hexxusTtsSkipCode = 'skip-unclosed-fence-1';

	var muteId = null;
	var spoken = [];
	var origDispatch = EventTarget.prototype.dispatchEvent;

	function fenceIndexes(text) {
		var out = [];
		var i = 0;
		while ((i = text.indexOf('```', i)) !== -1) {
			out.push(i);
			i += 3;
		}
		return out;
	}

	function stripClosedFences(text) {
		return text.replace(/```[\s\S]*?```/g, '');
	}

	function cleanSpoken(text) {
		return text
			.replace(/[ \t]+\n/g, '\n')
			.replace(/\n[ \t]+/g, '\n')
			.replace(/[ \t]{2,}/g, ' ')
			.replace(/\n{3,}/g, '\n\n')
			.trim();
	}

	function shape(id, content, mute) {
		var text = String(content || '');
		if (mute && mute !== id) mute = null;

		if (mute === id) {
			var closing = fenceIndexes(text);
			if (!closing.length) return { text: '', mute: mute };
			text = text.slice(closing[closing.length - 1] + 3);
			mute = null;
		}

		text = stripClosedFences(text);
		var open = fenceIndexes(text);
		if (open.length % 2 === 1) {
			text = text.slice(0, open[open.length - 1]);
			mute = id;
		}
		return { text: cleanSpoken(text), mute: mute };
	}

	function sentencesAfterLastFence(full) {
		var text = String(full || '');
		var idxs = fenceIndexes(text);
		if (!idxs.length || idxs.length % 2 === 1) return [];
		var after = stripClosedFences(text.slice(idxs[idxs.length - 1] + 3));
		var parts = after.split(/(?<=[.!?])\s+|\n+/);
		var merged = [];
		for (var i = 0; i < parts.length; i++) {
			var piece = cleanSpoken(parts[i].replace(/^#{1,6}\s+/, '').replace(/^\s*[-*+]\s+/, ''));
			if (!piece) continue;
			if (!merged.length) {
				merged.push(piece);
				continue;
			}
			var prev = merged[merged.length - 1];
			if (prev.split(/\s+/).length < 4 || prev.length < 50) merged[merged.length - 1] = prev + ' ' + piece;
			else merged.push(piece);
		}
		return merged;
	}

	function remember(text) {
		if (text) spoken.push(text);
	}

	function alreadySpoken(sentence) {
		for (var i = 0; i < spoken.length; i++) {
			if (spoken[i] === sentence || spoken[i].indexOf(sentence) !== -1) return true;
		}
		return false;
	}

	function emitChat(target, id, content) {
		remember(content);
		origDispatch.call(
			target,
			new CustomEvent('chat', { detail: { id: id, content: content } })
		);
	}

	EventTarget.prototype.dispatchEvent = function (event) {
		if (!event || !event.type) return origDispatch.call(this, event);

		if (event.type === 'chat:start') {
			muteId = null;
			spoken = [];
			return origDispatch.call(this, event);
		}

		if (event.type === 'chat:finish') {
			var detail = event.detail || {};
			var finishId = detail.id;
			var extras = muteId && muteId === finishId ? sentencesAfterLastFence(detail.content) : [];
			muteId = null;
			for (var i = 0; i < extras.length; i++) {
				if (!alreadySpoken(extras[i])) emitChat(this, finishId, extras[i]);
			}
			spoken = [];
			return origDispatch.call(this, event);
		}

		if (event.type === 'chat' && event.detail && typeof event.detail.content === 'string') {
			var shaped = shape(event.detail.id, event.detail.content, muteId);
			muteId = shaped.mute;
			if (!shaped.text) return true;
			remember(shaped.text);
			if (shaped.text !== event.detail.content) {
				event = new CustomEvent('chat', {
					detail: { id: event.detail.id, content: shaped.text }
				});
			}
		}
		return origDispatch.call(this, event);
	};
})();
