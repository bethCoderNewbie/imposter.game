import { getAvatarColor, getInitials, isIconAvatar } from '../../types/game'
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

  if (isIconAvatar(player.avatar_id)) {
    return (
      <div
        role="img"
        aria-label={player.display_name}
        className={`player-avatar player-avatar--icon ${className}`}
        style={{ background: '#2d3748', ...sizeStyle, ...style }}
      >
        <img
          src={`/images/${player.avatar_id}.png`}
          alt={player.display_name}
          className="player-avatar__icon"
        />
      </div>
    )
  }

  // Legacy color avatar fallback (avatar_01–avatar_08)
  const bg = getAvatarColor(player.avatar_id)
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
