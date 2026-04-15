import { useEffect, useRef, useState } from 'react'
import './VoteWeb.css'

interface Line {
  x1: number; y1: number
  x2: number; y2: number
  strokeWidth: number
  delay: number
}

interface Props {
  /** Votes snapshot frozen at day_vote close */
  votes: Record<string, string>
}

/** ADR-003 §2 — Reveal-all-at-once when voting closes.
 *  Uses getBoundingClientRect() once on mount to compute centroids. */
export default function VoteWeb({ votes }: Props) {
  const [lines, setLines] = useState<Line[]>([])
  const containerRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    // Compute vote counts per target
    const voteCounts: Record<string, number> = {}
    Object.values(votes).forEach(tid => {
      voteCounts[tid] = (voteCounts[tid] ?? 0) + 1
    })

    // Read DOM positions — single pass (ADR-003 consequence note)
    const cardMap = new Map<string, DOMRect>()
    document.querySelectorAll<HTMLElement>('[data-player-id]').forEach(el => {
      const pid = el.dataset.playerId!
      cardMap.set(pid, el.getBoundingClientRect())
    })

    const built: Line[] = []
    let idx = 0

    Object.entries(votes).forEach(([voterId, targetId]) => {
      const voterRect = cardMap.get(voterId)
      const targetRect = cardMap.get(targetId)
      if (!voterRect || !targetRect) return

      const voteCountOnTarget = voteCounts[targetId] ?? 1

      built.push({
        x1: voterRect.left + voterRect.width / 2,
        y1: voterRect.top + voterRect.height / 2,
        x2: targetRect.left + targetRect.width / 2,
        y2: targetRect.top + targetRect.height / 2,
        strokeWidth: 1 + voteCountOnTarget * 1.5,
        delay: idx * 80,
      })
      idx++
    })

    setLines(built)
  }, []) // only runs once on mount (votes are frozen)

  if (lines.length === 0) return null

  return (
    <svg
      ref={containerRef}
      className="vote-web"
      style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    >
      <defs>
        <filter id="vote-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {lines.map((line, i) => (
        <line
          key={i}
          x1={line.x1}
          y1={line.y1}
          x2={line.x2}
          y2={line.y2}
          stroke="rgba(255, 80, 80, 0.9)"
          strokeWidth={line.strokeWidth}
          strokeLinecap="round"
          filter="url(#vote-glow)"
          className="vote-web__line"
          style={{ animationDelay: `${line.delay}ms` }}
        />
      ))}
    </svg>
  )
}
