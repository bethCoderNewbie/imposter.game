import { getAvatarColor, getInitials } from '../../types/game'
import type { PlayerState } from '../../types/game'
import './PlayerAvatar.css'

interface Props {
  player: PlayerState
  size?: number   // diameter in px (used in non-vmin contexts, e.g. NightResolution)
  className?: string
  style?: React.CSSProperties
  'data-player-id'?: string
}

export default function PlayerAvatar({ player, size, className = '', style, ...rest }: Props) {
  const bg = getAvatarColor(player.avatar_id)
  const initials = getInitials(player.display_name)
  const sizeStyle = size ? { width: size, height: size, fontSize: size * 0.38 } : {}

  return (
    <div
      className={`player-avatar ${className}`}
      style={{ backgroundColor: bg, ...sizeStyle, ...style }}
      data-player-id={rest['data-player-id'] ?? player.player_id}
    >
      {initials}
    </div>
  )
}
