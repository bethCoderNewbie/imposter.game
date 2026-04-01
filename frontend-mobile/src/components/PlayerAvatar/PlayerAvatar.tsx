import { getAvatarColor, getInitials } from '../../types/game'
import type { PlayerState } from '../../types/game'
import './PlayerAvatar.css'

interface Props {
  player: PlayerState
  size?: number
  className?: string
  style?: React.CSSProperties
}

export default function PlayerAvatar({ player, size, className = '', style }: Props) {
  const bg = getAvatarColor(player.avatar_id)
  const initials = getInitials(player.display_name)
  const sizeStyle = size ? { width: size, height: size, fontSize: size * 0.38 } : {}

  return (
    <div
      role="img"
      aria-label={player.display_name}
      className={`player-avatar ${className}`}
      style={{ backgroundColor: bg, ...sizeStyle, ...style }}
    >
      {initials}
    </div>
  )
}
