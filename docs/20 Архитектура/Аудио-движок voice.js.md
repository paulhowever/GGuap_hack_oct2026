---
tags: [архитектура, audio, паша]
status: draft
updated: 2026-10-08
---

# Аудио-движок voice.js

**Граф.**
- `new AudioContext({latencyHint:'interactive'})`, sampleRate не задаём.
- Минус: `fetch → decodeAudioData → BufferSource → Gain(music) → destination`, запуск `src.start(t0 = ctx.currentTime + 0.15)`.
- Микрофон: `getUserMedia({audio:{echoCancellation:aec, noiseSuppression:false, autoGainControl:false, channelCount:1}}) → MediaStreamSource → AudioWorklet 'tap' → Gain(0) → destination`.

**Время.** `L = lag_ms/1000`, по умолчанию `outputLatency + baseLatency + (track.getSettings().latency || 0.02)`.
- Позиция для Godot: `ts = ctx.getOutputTimestamp(); t_now = ts.contextTime + (performance.now() − ts.performanceTime)/1000 − t0`. Фолбэк: `ctx.currentTime − outputLatency − baseLatency − t0`.
- Кадр: tap отдаёт индекс конца хопа `E`. Центр окна 2048 — `E − 1024`, `t = (E−1024)/sr − t0 − L`.
- Если `outputLatency > 0.1`, выставляем `bt_suspect = true`, и Godot показывает «похоже на Bluetooth, нужен провод».

**Питч.** pitchy (MIT, метод McLeod, чистый JS) прямо в AudioWorklet, без WASM и Worker.
- `web/vendor/pitchy.bundle.js` собирается один раз: `npx esbuild node_modules/pitchy/dist/index.js --bundle --format=esm --outfile=web/vendor/pitchy.bundle.js` (pitchy тянет fft.js).
- Окно 2048, хоп 512 (≈10,7 мс при 48 кГц). Кольцевой буфер в worklet, `PitchDetector.forFloat32Array(2048)`, `findPitch(win, sampleRate) → [hz, clarity]`.
- `conf = clarity`; кадр озвучен при `clarity ≥ 0,85` и `rms > gate`, `gate = max(0.01, 3·noise_floor)`. Hz вне [65, 1100] обнуляется.
- Пачки кадров уходят в главный поток раз в ~30 мс; PCM-блоки для записи дубля идут тем же портом.
- Фолбэк, если import в worklet не заведётся: тот же код в Worker через MessagePort.
- Реализация за интерфейсом `PitchStrategy`.

```js
import { PitchDetector } from './vendor/pitchy.bundle.js'
class Tap extends AudioWorkletProcessor{
constructor(){super();this.W=2048;this.H=512;this.ring=new Float32Array(this.W);this.win=new Float32Array(this.W);this.pos=0;this.cnt=0;this.det=PitchDetector.forFloat32Array(this.W);this.rec=false;this.out=[];this.port.onmessage=e=>{this.rec=!!e.data.rec}}
process(inputs){const x=inputs[0][0];if(!x)return true
if(this.rec)this.port.postMessage({pcm:x.slice(),F:currentFrame})
for(let k=0;k<x.length;k++){this.ring[this.pos]=x[k];this.pos=(this.pos+1)%this.W;if(++this.cnt===this.H){this.cnt=0;this.emit(currentFrame+k+1)}}
if(this.out.length>=3){this.port.postMessage({frames:this.out});this.out=[]}
return true}
emit(E){let s=0;for(let j=0;j<this.W;j++){const v=this.ring[(this.pos+j)%this.W];this.win[j]=v;s+=v*v}
const [hz,clarity]=this.det.findPitch(this.win,sampleRate)
this.out.push({E,hz,clarity,rms:Math.sqrt(s/this.W)})}}
registerProcessor('tap',Tap)
```

**Запись дубля.**
- Worker копит Float32 от `start` до `stop` (60 с при 48 кГц ≈ 11,5 МБ) и запоминает `wav_t0 = F0/sr − t0`.
- На `stop`: `OfflineAudioContext(1, ceil(n·16000/sr), 16000)` → Int16 → WAV (~32 КБ/с). Фолбэк — родная частота.
- MediaRecorder не используем.

**Калибровка** `calibrate()`:
- 8 щелчков через 500 мс (OscillatorNode, 20 мс), пользователь хлопает или говорит «та».
- Онсет — момент, когда `rms > 4·floor`.
- `lag = median(onset − click)` после отбрасывания выбросов дальше 60 мс от медианы. Нужно ≥5 попаданий.
- Результат сохраняется в `localStorage['voice.lag_ms']` в try/catch. Ручная подстройка шагом ±10 мс.
- На демо `lag_ms` зашит в `web/config.js` после калибровки на целевой цепочке вывода (см. §8).

**Мок.**
- `?mock=perfect|offkey|octave|late200|silent`.
- Часы от `performance.now()`. Кадры по нотам: ±30 центов шума, в режиме octave ±12, в late200 +0,2 с.
- `submit` через 500 мс отдаёт `web/mock/result.<mode>.json`.
- Горячая клавиша `R` (план Б) прогоняет записанный дубль `web/mock/take.wav` через реальный POST /takes.

**Автоплей и HTTPS.**
- getUserMedia и AudioContext запускаются только из обработчика клика по HTML-оверлею. Дополнительно стоит `document.onpointerdown → ctx.resume()`.
- Локально подходит `http://localhost:8000`, онлайн нужен HTTPS.
- Минус в mp3, звуки во время пения через Godot не играем.

## Связанные
- [[Контракты]]
- [[ADR-002 Всё аудио в JS]]
- [[ADR-003 Живой питч pitchy]]
- [[Живой питч в браузере]]
