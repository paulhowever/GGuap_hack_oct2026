import { round } from './num.js'

export function buildMeta({ songId, player, difficulty, challengeId, wavT0, wavSr, lagMs, frames, client }) {
  return {
    song_id: songId,
    player: String(player ?? '').trim().slice(0, 24) || 'Игрок',
    difficulty,
    challenge_id: challengeId ? String(challengeId) : null,
    wav_t0: round(wavT0, 3),
    wav_sr: wavSr,
    lag_ms: Math.round(lagMs),
    frames,
    client
  }
}
