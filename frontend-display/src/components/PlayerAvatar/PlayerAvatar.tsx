import { getAvatarColor, getInitials } from '../../types/game'
import './PlayerAvatar.css'

interface PlayerLike {
  player_id: string
  display_name: string
  avatar_id: string
  photo_url?: string | null
}

interface Props {
  player: PlayerLike
  size?: number   // diameter in px (used in non-vmin contexts, e.g. NightResolution)
  className?: string
  style?: React.CSSProperties
  'data-player-id'?: string
}

export default function PlayerAvatar({ player, size, className = '', style, ...rest }: Props) {
  const bg = getAvatarColor(player.avatar_id)
  const initials = getInitials(player.display_name)
  const sizeStyle = size ? { width: size, height: size, fontSize: size * 0.38 } : {}
  const dataPlayerId = rest['data-player-id'] ?? player.player_id

  if (player.photo_url) {
    return (
      <div
        className={`player-avatar ${className}`}
        style={{ ...sizeStyle, ...style }}
        data-player-id={dataPlayerId}
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
      className={`player-avatar ${className}`}
      style={{ backgroundColor: bg, ...sizeStyle, ...style }}
      data-player-id={dataPlayerId}
    >
      {initials}
    </div>
  )
}
