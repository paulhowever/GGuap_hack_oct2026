import { round } from './num.js'

export function playerName(raw) {
  return Array.from(String(raw ?? '').trim()).slice(0, 24).join('').trim() || 'Игрок'
}

export function buildMeta({ songId, clientId, sessionToken, player, difficulty, challengeId, wavT0, wavSr, lagMs, lagSource, frames, client }) {
  return {
    song_id: songId,
    client_id: clientId || null,
    session_token: sessionToken || null,
    player: playerName(player),
    difficulty,
    challenge_id: challengeId ? String(challengeId) : null,
    wav_t0: round(wavT0, 3),
    wav_sr: wavSr,
    lag_ms: Math.round(lagMs),
    lag_source: lagSource || null,
    frames,
    client
  }
}
