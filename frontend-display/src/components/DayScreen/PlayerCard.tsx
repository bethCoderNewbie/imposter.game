import React from 'react'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import { getCauseIcon } from '../../utils/elimination'
import type { PlayerState } from '../../types/game'
import './PlayerCard.css'

interface Props {
  player: PlayerState
  voteCount: number
  hasMajority: boolean
  index: number
  isSoundActive: boolean
  eliminationCause: string | null
}

export default function PlayerCard({ player, voteCount, hasMajority, index, isSoundActive, eliminationCause }: Props) {
  const isDead = !player.is_alive

  return (
    <div
      className={[
        'player-card',
        isDead ? 'player-card--dead' : '',
        hasMajority ? 'player-card--majority' : '',
        isSoundActive ? 'player-card--sound-active' : '',
      ].filter(Boolean).join(' ')}
      data-player-id={player.player_id}
      style={{ '--i': index } as React.CSSProperties}
    >
      <div className="player-card__avatar-wrap">
        <PlayerAvatar player={player} />

        {/* Cause icon or tombstone fallback for eliminated players */}
        {isDead && eliminationCause && (() => {
          const icon = getCauseIcon(eliminationCause)
          return icon.type === 'image'
            ? <img className="player-card__cause-icon" src={icon.src} alt={icon.alt} />
            : <span className="player-card__cause-icon player-card__cause-icon--emoji" aria-hidden="true">{icon.char}</span>
        })()}
        {isDead && !eliminationCause && (
          <div className="player-card__tombstone" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M6 21V10a6 6 0 1 1 12 0v11" />
              <path d="M3 21h18" />
              <path d="M10 14v3" />
              <path d="M14 14v3" />
            </svg>
          </div>
        )}
      </div>

      {/* Vote tally badge — outside avatar-wrap so overflow:hidden doesn't clip it */}
      {voteCount > 0 && (
        <div className="player-card__vote-badge">{voteCount}</div>
      )}

      <p className="player-card__name">{player.display_name}</p>
    </div>
  )
}
