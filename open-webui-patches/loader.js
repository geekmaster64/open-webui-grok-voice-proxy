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
