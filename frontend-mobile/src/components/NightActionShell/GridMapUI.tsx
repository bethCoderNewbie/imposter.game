import { useState } from 'react'
import type { GridActivityEntry, HintPayload, PlayerState } from '../../types/game'
import PuzzleRenderer from './PuzzleRenderer'
import Tooltip from '../Tooltip/Tooltip'
import {
  TOOLTIP_NODE_GREEN,
  TOOLTIP_NODE_YELLOW,
  TOOLTIP_NODE_RED,
  TOOLTIP_NODE_COMPLETED,
} from '../Tooltip/Tooltip.constants'
import './ActionUI.css'
import './GridMapUI.css'

interface Props {
  myPlayer: PlayerState
  gridLayout: number[][] | null | undefined
  gridActivity?: GridActivityEntry[]
  sendIntent: (payload: Record<string, unknown>) => void
  latestHint?: HintPayload | null
}

const TIER_COLORS: Record<number, string> = {
  1: '#38a169',  // green
  2: '#d69e2e',  // yellow
  3: '#e53e3e',  // red
}

function _quadrant(row: number, col: number): string {
  const top = row <= 1
  const left = col <= 1
  if (top && left) return 'top_left'
  if (top) return 'top_right'
  if (left) return 'bottom_left'
  return 'bottom_right'
}

/** 5×5 data node grid for wakeOrder==0 players during night phase.
 *  Coexists with the Archive puzzle on the GRID tab (PRD-013). */
export default function GridMapUI({
  myPlayer,
  gridLayout,
  gridActivity = [],
  sendIntent,
  latestHint,
}: Props) {
  const [pendingNode, setPendingNode] = useState<{ row: number; col: number } | null>(null)

  const gps = myPlayer.grid_puzzle_state ?? null
  const completedSet = new Set(gridActivity.map(e => `${e.row},${e.col}`))
  const hasActivePuzzle = gps !== null && gps.active

  function handleNodeTap(row: number, col: number) {
    if (hasActivePuzzle) return
    if (completedSet.has(`${row},${col}`)) return
    setPendingNode({ row, col })
    sendIntent({ type: 'select_grid_node', row, col })
  }

  // Show active grid puzzle full-screen (replaces grid map while puzzle is live)
  if (gps?.active) {
    return (
      <div className="grid-map-ui">
        <PuzzleRenderer
          puzzle={gps}
          sendIntent={sendIntent}
          latestHint={latestHint}
          source="grid"
        />
      </div>
    )
  }

  if (!gridLayout) {
    return (
      <div className="action-ui action-ui--centered">
        <p className="action-ui__header">Grid initializing…</p>
      </div>
    )
  }

  const isSelecting = pendingNode !== null

  return (
    <div className="grid-map-ui">
      {/* Inline hint banner — shown after a correct solve while grid remains navigable */}
      {gps?.solved && latestHint && (
        <div className="grid-map-ui__hint-banner">
          <span className="grid-map-ui__hint-banner-label">🔷 Grid Intel</span>
          <span className="grid-map-ui__hint-banner-text">{latestHint.text}</span>
          {latestHint.expires_after_round !== null && (
            <span className="grid-map-ui__hint-banner-expiry">
              expires R{latestHint.expires_after_round}
            </span>
          )}
        </div>
      )}
      {/* Wrong-answer feedback — brief message, grid stays open for next node */}
      {gps?.solved === false && (
        <p className="grid-map-ui__wrong">Wrong answer — tap another node.</p>
      )}
      <p className="grid-map-ui__header">
        {isSelecting ? 'Traveling to node…' : 'Tap a Data Node to begin.'}
      </p>

      <div className="grid-map-ui__grid">
        {gridLayout.map((rowArr, row) =>
          rowArr.map((tier, col) => {
            const key = `${row},${col}`
            const completed = completedSet.has(key)
            const isPending = pendingNode?.row === row && pendingNode?.col === col
            const color = TIER_COLORS[tier] ?? '#38a169'
            const quadrant = _quadrant(row, col)

            return (
              <button
                key={key}
                className={[
                  'grid-map-ui__node',
                  `grid-map-ui__node--tier${tier}`,
                  completed ? 'grid-map-ui__node--completed' : '',
                  isPending ? 'grid-map-ui__node--pending' : '',
                ].join(' ')}
                style={{
                  background: completed ? '#2d3748' : color + (isPending ? 'cc' : '33'),
                  borderColor: completed ? '#4a5568' : color,
                  opacity: completed ? 0.4 : 1,
                }}
                disabled={completed || hasActivePuzzle}
                onClick={() => handleNodeTap(row, col)}
                aria-label={`${tier === 3 ? 'Red' : tier === 2 ? 'Yellow' : 'Green'} node at ${quadrant.replace('_', ' ')}`}
              >
                {completed ? '✓' : tier === 3 ? '◆' : tier === 2 ? '●' : '○'}
              </button>
            )
          })
        )}
      </div>

      {/* Legend row with inline tooltips */}
      <div className="grid-map-ui__legend-row">
        <span style={{ color: TIER_COLORS[1] }}>● 5s</span>
        <Tooltip text={TOOLTIP_NODE_GREEN} position="above" />
        <span className="grid-map-ui__legend-sep">·</span>
        <span style={{ color: TIER_COLORS[2] }}>● 10s</span>
        <Tooltip text={TOOLTIP_NODE_YELLOW} position="above" />
        <span className="grid-map-ui__legend-sep">·</span>
        <span style={{ color: TIER_COLORS[3] }}>◆ 20s</span>
        <Tooltip text={TOOLTIP_NODE_RED} position="above" />
        <span className="grid-map-ui__legend-sep">·</span>
        <span style={{ color: '#4a5568' }}>✓</span>
        <Tooltip text={TOOLTIP_NODE_COMPLETED} position="above" />
      </div>
    </div>
  )
}

