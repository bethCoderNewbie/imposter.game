import { useCallback, useEffect, useRef, useState } from 'react'
import type { GridRippleMessage, NightActions } from '../../types/game'
import './WolfRadarUI.css'

type Quadrant = 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right'

const QUADRANT_LABELS: Record<Quadrant, string> = {
  top_left: '↖',
  top_right: '↗',
  bottom_left: '↙',
  bottom_right: '↘',
}

const TIER_COLORS = { 1: '#38a169', 2: '#d69e2e', 3: '#e53e3e' } as const

const CHARGE_TOTAL_MS = 5000   // 5 s cumulative hold to fire (PRD-015 §2.1)
const CHARGE_TICK_MS  = 200    // update interval while holding
const CHARGE_REPORT_MS = 500   // send server update every N ms while active

interface Ripple {
  id: number
  quadrant: Quadrant
  tier: 1 | 2 | 3
}

interface ChargeState {
  accumulated: number   // ms accumulated so far
  holding: boolean
}

interface Props {
  nightActions: NightActions
  sendIntent: (payload: Record<string, unknown>) => void
  latestRipple?: GridRippleMessage | null
}

export default function WolfRadarUI({ nightActions, sendIntent, latestRipple }: Props) {
  const [ripples, setRipples] = useState<Ripple[]>([])
  const [pingTarget, setPingTarget] = useState<Quadrant | null>(null)
  const [firedQuadrant, setFiredQuadrant] = useState<Quadrant | null>(null)
  const rippleIdRef = useRef(0)

  // Charge state per quadrant — fully independent
  const [charges, setCharges] = useState<Record<Quadrant, ChargeState>>({
    top_left:     { accumulated: 0, holding: false },
    top_right:    { accumulated: 0, holding: false },
    bottom_left:  { accumulated: 0, holding: false },
    bottom_right: { accumulated: 0, holding: false },
  })

  // Timer refs: one tick interval + one server-report interval per quadrant
  const tickRefs   = useRef<Partial<Record<Quadrant, ReturnType<typeof setInterval>>>>({})
  const reportRefs = useRef<Partial<Record<Quadrant, ReturnType<typeof setInterval>>>>({})
  // Stable ref to charges so interval callbacks can read current value
  const chargesRef = useRef(charges)
  chargesRef.current = charges

  // ── Ripple animation ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!latestRipple) return
    const id = ++rippleIdRef.current
    setRipples(prev => [...prev, { id, quadrant: latestRipple.quadrant, tier: latestRipple.tier }])
    const t = setTimeout(() => setRipples(prev => prev.filter(r => r.id !== id)), 2000)
    return () => clearTimeout(t)
  }, [latestRipple])

  // ── Charge helpers ──────────────────────────────────────────────────────────

  const stopCharge = useCallback((q: Quadrant, fire: boolean) => {
    // Clear intervals
    if (tickRefs.current[q])   { clearInterval(tickRefs.current[q]!);   delete tickRefs.current[q] }
    if (reportRefs.current[q]) { clearInterval(reportRefs.current[q]!); delete reportRefs.current[q] }

    const current = chargesRef.current[q].accumulated

    if (fire) {
      // Charge complete — send CHARGE_TOTAL_MS so the server pack-pool check fires, then reset local state.
      sendIntent({ type: 'wolf_charge_update', quadrant: q, accumulated_ms: CHARGE_TOTAL_MS, is_active: false })
      setCharges(prev => ({ ...prev, [q]: { accumulated: 0, holding: false } }))
      setFiredQuadrant(q)
      setTimeout(() => setFiredQuadrant(prev => prev === q ? null : prev), 1500)
    } else {
      // Released before 5 s — pause (keep accumulated, clear under_attack on server)
      setCharges(prev => ({ ...prev, [q]: { ...prev[q], holding: false } }))
      sendIntent({ type: 'wolf_charge_update', quadrant: q, accumulated_ms: current, is_active: false })
    }
  }, [sendIntent])

  const startCharge = useCallback((q: Quadrant) => {
    if (chargesRef.current[q].holding) return  // already holding

    setCharges(prev => ({ ...prev, [q]: { ...prev[q], holding: true } }))

    const startAccumulated = chargesRef.current[q].accumulated

    // Tell server the charge is active
    sendIntent({
      type: 'wolf_charge_update',
      quadrant: q,
      accumulated_ms: startAccumulated,
      is_active: true,
    })

    // Tick interval: accumulate time locally
    const startTime = Date.now()
    tickRefs.current[q] = setInterval(() => {
      const elapsed = Date.now() - startTime
      const newAcc = startAccumulated + elapsed
      setCharges(prev => ({ ...prev, [q]: { ...prev[q], accumulated: newAcc } }))
      if (newAcc >= CHARGE_TOTAL_MS) {
        stopCharge(q, true)
      }
    }, CHARGE_TICK_MS)

    // Report interval: keep server informed while holding
    reportRefs.current[q] = setInterval(() => {
      const elapsed = Date.now() - startTime
      const newAcc = startAccumulated + elapsed
      sendIntent({
        type: 'wolf_charge_update',
        quadrant: q,
        accumulated_ms: Math.min(newAcc, CHARGE_TOTAL_MS),
        is_active: true,
      })
    }, CHARGE_REPORT_MS)
  }, [sendIntent, stopCharge])

  // Cleanup all intervals on unmount
  useEffect(() => {
    return () => {
      const quadrants: Quadrant[] = ['top_left', 'top_right', 'bottom_left', 'bottom_right']
      quadrants.forEach(q => {
        if (tickRefs.current[q])   clearInterval(tickRefs.current[q]!)
        if (reportRefs.current[q]) clearInterval(reportRefs.current[q]!)
      })
    }
  }, [])

  // ── Sonar ping ──────────────────────────────────────────────────────────────
  function handlePing(q: Quadrant) {
    setPingTarget(q)
    sendIntent({ type: 'sonar_ping', quadrant: q })
  }

  // ── Derived display values ──────────────────────────────────────────────────
  const gridActivity  = nightActions.grid_activity  ?? []
  const sonarResults  = nightActions.sonar_ping_results ?? []
  const heatMap: Record<Quadrant, number> = {
    top_left: 0, top_right: 0, bottom_left: 0, bottom_right: 0,
  }
  for (const e of gridActivity) {
    if (e.quadrant in heatMap) heatMap[e.quadrant as Quadrant]++
  }

  const quadrants: Quadrant[] = ['top_left', 'top_right', 'bottom_left', 'bottom_right']

  const used      = nightActions.sonar_pings_used ?? 0
  const MAX_PINGS = 4
  const pingsLeft = Math.max(0, MAX_PINGS - used)
  const pingsDone = pingsLeft === 0

  return (
    <div className="wolf-radar">
      <p className="wolf-radar__title">RADAR</p>
      <p className="wolf-radar__subtitle">
        {used} ping{used !== 1 ? 's' : ''} used
      </p>

      {/* Radar display */}
      <div className="wolf-radar__display">
        {quadrants.map(q => {
          const heat          = heatMap[q]
          const activeRipples = ripples.filter(r => r.quadrant === q)
          const pingedResult  = sonarResults.find(r => r.quadrant === q)
          const isPingTarget  = pingTarget === q
          const charge        = charges[q]
          const chargePct     = Math.min(charge.accumulated / CHARGE_TOTAL_MS, 1)
          const isFull        = chargePct >= 1

          return (
            <div
              key={q}
              className={[
                'wolf-radar__quadrant',
                heat > 0 ? 'wolf-radar__quadrant--active' : '',
                isPingTarget ? 'wolf-radar__quadrant--pinged' : '',
                charge.holding ? 'wolf-radar__quadrant--charging' : '',
                isFull ? 'wolf-radar__quadrant--charged' : '',
                firedQuadrant === q ? 'wolf-radar__quadrant--fired' : '',
              ].join(' ')}
              style={{ '--heat': Math.min(heat / 5, 1) } as React.CSSProperties}
              /* Hold-to-charge: mousedown/touchstart starts, mouseup/touchend stops */
              onMouseDown={() => startCharge(q)}
              onMouseUp={() => { if (charges[q].holding) stopCharge(q, false) }}
              onMouseLeave={() => { if (charges[q].holding) stopCharge(q, false) }}
              onTouchStart={e => { e.preventDefault(); startCharge(q) }}
              onTouchEnd={e => { e.preventDefault(); if (charges[q].holding) stopCharge(q, false) }}
            >
              {/* Ripples */}
              {activeRipples.map(r => (
                <span key={r.id} className="wolf-radar__ripple"
                  style={{ borderColor: TIER_COLORS[r.tier] }} />
              ))}

              {/* Charge arc (SVG circle) */}
              {charge.accumulated > 0 && (
                <svg className="wolf-radar__charge-arc" viewBox="0 0 36 36">
                  <circle
                    cx="18" cy="18" r="15"
                    fill="none"
                    stroke={isFull ? '#e53e3e' : 'rgba(255,100,100,0.7)'}
                    strokeWidth="2.5"
                    strokeDasharray={`${chargePct * 94.25} 94.25`}
                    strokeLinecap="round"
                    transform="rotate(-90 18 18)"
                  />
                </svg>
              )}

              {/* Heat count */}
              {heat > 0 && (
                <span className="wolf-radar__heat">{heat}</span>
              )}

              {/* Ping result overlay */}
              {pingedResult && (
                <div className="wolf-radar__ping-result">
                  <span>{pingedResult.heat}</span>
                  <div className="wolf-radar__tier-dots">
                    {([1, 2, 3] as const).map(t =>
                      (pingedResult.tier_counts?.[t] ?? 0) > 0 && (
                        <span key={t} style={{ color: TIER_COLORS[t] }}>
                          {pingedResult.tier_counts[t]}×T{t}
                        </span>
                      )
                    )}
                  </div>
                </div>
              )}

              {/* Charge progress label */}
              {charge.accumulated > 0 && !isFull && (
                <span className="wolf-radar__charge-pct">
                  {Math.round(chargePct * 100)}%
                </span>
              )}

              {/* Fired confirmation */}
              {firedQuadrant === q && (
                <span className="wolf-radar__fired-label">FIRED</span>
              )}
            </div>
          )
        })}

        <div className="wolf-radar__crosshair-h" />
        <div className="wolf-radar__crosshair-v" />
      </div>

      {/* Charge instruction */}
      <p className="wolf-radar__charge-hint">Hold 5 s to attack</p>

      {/* Ripple legend */}
      <p className="wolf-radar__ripple-legend">
        <span style={{ color: TIER_COLORS[1] }}>●</span>{' '}
        <span style={{ color: TIER_COLORS[2] }}>●</span>{' '}
        <span style={{ color: TIER_COLORS[3] }}>●</span>
      </p>

      {/* Sonar ping controls */}
      {(() => {
        return (
          <>
            <p className="wolf-radar__ping-label">
              PING{' '}
              <span className="wolf-radar__ping-budget">
                {pingsLeft}/{MAX_PINGS}
              </span>
            </p>
            <div className="wolf-radar__ping-grid">
              {quadrants.map(q => (
                <button
                  key={q}
                  className="wolf-radar__ping-btn"
                  disabled={pingsDone}
                  onClick={() => handlePing(q)}
                >
                  {QUADRANT_LABELS[q]}
                </button>
              ))}
            </div>
            {pingsDone && <p className="wolf-radar__ping-empty">All pings used.</p>}
          </>
        )
      })()}
    </div>
  )
}
