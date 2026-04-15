import { getAvatarColor, getInitials } from '../../types/game'
import './PlayerAvatar.css'

interface AvatarPlayer {
  avatar_id: string
  display_name: string
  photo_url?: string | null
}

interface Props {
  player: AvatarPlayer
  size?: number
  className?: string
  style?: React.CSSProperties
}

export default function PlayerAvatar({ player, size, className = '', style }: Props) {
  const bg = getAvatarColor(player.avatar_id)
  const initials = getInitials(player.display_name)
  const sizeStyle = size ? { width: size, height: size, fontSize: size * 0.38 } : {}

  if (player.photo_url) {
    return (
      <div
        role="img"
        aria-label={player.display_name}
        className={`player-avatar ${className}`}
        style={{ ...sizeStyle, ...style }}
      >
        <img
          src={player.photo_url}
          alt={player.display_name}
          className="player-avatar__photo"
        />
      </div>
    )
  }

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
