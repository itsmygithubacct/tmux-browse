// audio.js — idle alert sound synthesis

function _schedNote(ctx, { freq, type = "sine", start = 0, dur = 0.35, peak = 0.035 }) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.value = 0.0001;
    osc.connect(gain);
    gain.connect(ctx.destination);
    const t0 = ctx.currentTime + start;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(peak, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
}

const IDLE_SOUND_PRESETS = {
    beep:  (ctx) => _schedNote(ctx, { freq: 880, type: "sine", dur: 0.35 }),
    chime: (ctx) => {
        _schedNote(ctx, { freq: 1046.5, type: "sine", start: 0.00, dur: 0.45 });
        _schedNote(ctx, { freq: 1318.5, type: "sine", start: 0.08, dur: 0.45 });
    },
    knock: (ctx) => {
        _schedNote(ctx, { freq: 180, type: "sine", start: 0.00, dur: 0.08, peak: 0.08 });
        _schedNote(ctx, { freq: 180, type: "sine", start: 0.14, dur: 0.08, peak: 0.08 });
    },
    bell:  (ctx) => _schedNote(ctx, { freq: 1760, type: "triangle", dur: 0.9, peak: 0.04 }),
    blip:  (ctx) => _schedNote(ctx, { freq: 440, type: "square", dur: 0.15, peak: 0.02 }),
    ding:  (ctx) => _schedNote(ctx, { freq: 2093, type: "sine", dur: 0.6, peak: 0.03 }),
};

function playIdleTone(name) {
    // Don't create an AudioContext here — Chrome logs a warning if one is
    // constructed before a user gesture. primeAudio() (below) constructs it
    // on the first pointerdown / keydown; until then, idle tones are silent.
    const ctx = state.audioCtx;
    if (!ctx || ctx.state !== "running") return;
    const preset = IDLE_SOUND_PRESETS[name] || IDLE_SOUND_PRESETS[state.config.idle_sound] || IDLE_SOUND_PRESETS.beep;
    preset(ctx);
}

function primeAudio() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!state.audioCtx) state.audioCtx = new Ctx();
    if (state.audioCtx.state === "suspended") {
        state.audioCtx.resume().catch(() => {});
    }
}

