export type CauseIcon =
  | { type: 'image';     src: string; alt: string }
  | { type: 'emoji';     char: string }
  | { type: 'tombstone' }

/**
 * Returns the icon for an elimination cause.
 *
 * @param revealSpecific  false during active game phases — masks kill causes
 *                        to prevent spectators from inferring night actions.
 *                        true at game_over — full reveal.
 *
 * village_vote is always shown as a rope (it is public information).
 * All other causes show a generic tombstone SVG when revealSpecific=false.
 */
export function getCauseIcon(cause: string, revealSpecific = true): CauseIcon {
  if (cause === 'village_vote') {
    return { type: 'image', src: `${import.meta.env.BASE_URL}images/rope.png`, alt: 'hanged by village' }
  }
  if (!revealSpecific) {
    return { type: 'tombstone' }
  }
  switch (cause) {
    case 'wolf_kill':          return { type: 'image', src: `${import.meta.env.BASE_URL}images/claw.png`, alt: 'wolf claw' }
    case 'serial_killer_kill': return { type: 'emoji', char: '🔪' }
    case 'arsonist_ignite':    return { type: 'emoji', char: '🔥' }
    case 'broken_heart':       return { type: 'emoji', char: '💔' }
    case 'hunter_revenge':     return { type: 'emoji', char: '🔫' }
    default:                   return { type: 'emoji', char: '✕' }
  }
}
