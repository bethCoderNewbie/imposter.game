export type CauseIcon =
  | { type: 'image'; src: string; alt: string }
  | { type: 'emoji'; char: string }

export function getCauseIcon(cause: string): CauseIcon {
  switch (cause) {
    case 'wolf_kill':          return { type: 'image', src: `${import.meta.env.BASE_URL}images/claw.png`, alt: 'wolf claw' }
    case 'village_vote':       return { type: 'image', src: `${import.meta.env.BASE_URL}images/rope.png`, alt: 'hanged by village' }
    case 'serial_killer_kill': return { type: 'emoji', char: '🔪' }
    case 'arsonist_ignite':    return { type: 'emoji', char: '🔥' }
    case 'broken_heart':       return { type: 'emoji', char: '💔' }
    case 'hunter_revenge':     return { type: 'emoji', char: '🔫' }
    default:                   return { type: 'emoji', char: '✕' }
  }
}
