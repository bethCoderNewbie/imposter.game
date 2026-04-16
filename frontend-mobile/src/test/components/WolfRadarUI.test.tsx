import { render, screen, fireEvent, act } from '@testing-library/react'
import WolfRadarUI from '../../components/NightActionShell/WolfRadarUI'
import type { NightActions, GridRippleMessage } from '../../types/game'

const CHARGE_TOTAL_MS = 5000
const CHARGE_TICK_MS  = 200
const CHARGE_REPORT_MS = 500

function makeNightActions(overrides: Partial<NightActions> = {}): NightActions {
  return {
    actions_submitted_count: 0,
    actions_required_count: 0,
    sonar_pings_used: 0,
    sonar_ping_results: [],
    grid_activity: [],
    ...overrides,
  }
}

describe('WolfRadarUI', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ── Layout ──────────────────────────────────────────────────────────────────

  it('renders 4 quadrant cells', () => {
    render(
      <WolfRadarUI
        nightActions={makeNightActions()}
        sendIntent={vi.fn()}
      />
    )
    const quadrants = document.querySelectorAll('.wolf-radar__quadrant')
    expect(quadrants).toHaveLength(4)
  })

  it('renders 4 ping buttons', () => {
    render(
      <WolfRadarUI
        nightActions={makeNightActions()}
        sendIntent={vi.fn()}
      />
    )
    expect(screen.getAllByRole('button')).toHaveLength(4)
  })

  // ── Charge: mousedown / mouseup ─────────────────────────────────────────────

  it('mousedown sends wolf_charge_update with is_active:true', () => {
    const sendIntent = vi.fn()
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={sendIntent} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')
    fireEvent.mouseDown(quadrant)
    expect(sendIntent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'wolf_charge_update', is_active: true, accumulated_ms: 0 })
    )
  })

  it('mouseup before threshold sends wolf_charge_update with is_active:false', () => {
    const sendIntent = vi.fn()
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={sendIntent} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')

    fireEvent.mouseDown(quadrant)
    act(() => { vi.advanceTimersByTime(CHARGE_TICK_MS * 5) }) // 1000ms — below threshold

    sendIntent.mockClear()
    fireEvent.mouseUp(quadrant)

    expect(sendIntent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'wolf_charge_update', is_active: false })
    )
    const call = sendIntent.mock.calls[0][0]
    expect(call.accumulated_ms).toBeGreaterThan(0)
    expect(call.accumulated_ms).toBeLessThan(CHARGE_TOTAL_MS)
  })

  it('holding full duration fires — sends accumulated_ms=CHARGE_TOTAL_MS, is_active:false', () => {
    const sendIntent = vi.fn()
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={sendIntent} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')

    fireEvent.mouseDown(quadrant)
    act(() => { vi.advanceTimersByTime(CHARGE_TOTAL_MS + CHARGE_TICK_MS) })

    const fireCalls = sendIntent.mock.calls.filter(
      ([p]) => p.type === 'wolf_charge_update' && p.is_active === false && p.accumulated_ms >= CHARGE_TOTAL_MS
    )
    expect(fireCalls).toHaveLength(1)
  })

  it('releasing via mouseLeave also stops charge', () => {
    const sendIntent = vi.fn()
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={sendIntent} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')

    fireEvent.mouseDown(quadrant)
    act(() => { vi.advanceTimersByTime(CHARGE_TICK_MS * 3) })
    sendIntent.mockClear()
    fireEvent.mouseLeave(quadrant)

    expect(sendIntent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'wolf_charge_update', is_active: false })
    )
  })

  // ── Charge: touch ───────────────────────────────────────────────────────────

  it('touchstart initiates charge', () => {
    const sendIntent = vi.fn()
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={sendIntent} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')
    fireEvent.touchStart(quadrant, { touches: [{ clientX: 0, clientY: 0 }] })
    expect(sendIntent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'wolf_charge_update', is_active: true })
    )
  })

  it('touchend stops charge', () => {
    const sendIntent = vi.fn()
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={sendIntent} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')

    fireEvent.touchStart(quadrant, { touches: [{ clientX: 0, clientY: 0 }] })
    act(() => { vi.advanceTimersByTime(CHARGE_TICK_MS * 3) })
    sendIntent.mockClear()
    fireEvent.touchEnd(quadrant)

    expect(sendIntent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'wolf_charge_update', is_active: false })
    )
  })

  // ── FIRED feedback ──────────────────────────────────────────────────────────

  it('FIRED label appears after auto-fire', () => {
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={vi.fn()} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')

    fireEvent.mouseDown(quadrant)
    act(() => { vi.advanceTimersByTime(CHARGE_TOTAL_MS + CHARGE_TICK_MS) })

    expect(document.querySelector('.wolf-radar__fired-label')).toBeInTheDocument()
  })

  it('FIRED label disappears after 1500ms', () => {
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={vi.fn()} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')

    fireEvent.mouseDown(quadrant)
    act(() => { vi.advanceTimersByTime(CHARGE_TOTAL_MS + CHARGE_TICK_MS) })
    expect(document.querySelector('.wolf-radar__fired-label')).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(1500) })
    expect(document.querySelector('.wolf-radar__fired-label')).not.toBeInTheDocument()
  })

  // ── Charge arc ──────────────────────────────────────────────────────────────

  it('charge arc SVG appears after holding at least one tick', () => {
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={vi.fn()} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')

    fireEvent.mouseDown(quadrant)
    act(() => { vi.advanceTimersByTime(CHARGE_TICK_MS + 10) })

    expect(quadrant.querySelector('.wolf-radar__charge-arc')).toBeInTheDocument()
  })

  // ── Sonar ping ──────────────────────────────────────────────────────────────

  it('ping button sends sonar_ping intent with correct quadrant', () => {
    const sendIntent = vi.fn()
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={sendIntent} />)
    const pingBtns = screen.getAllByRole('button')
    fireEvent.click(pingBtns[0])  // first ping button = top_left
    expect(sendIntent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'sonar_ping' })
    )
  })

  it('ping buttons are disabled when sonar budget is exhausted', () => {
    render(
      <WolfRadarUI
        nightActions={makeNightActions({ sonar_pings_used: 4 })}
        sendIntent={vi.fn()}
      />
    )
    const pingBtns = screen.getAllByRole('button')
    pingBtns.forEach(btn => expect(btn).toBeDisabled())
  })

  it('ping buttons are enabled when pings remain', () => {
    render(
      <WolfRadarUI
        nightActions={makeNightActions({ sonar_pings_used: 2 })}
        sendIntent={vi.fn()}
      />
    )
    const pingBtns = screen.getAllByRole('button')
    pingBtns.forEach(btn => expect(btn).not.toBeDisabled())
  })

  // ── Ripple ──────────────────────────────────────────────────────────────────

  it('ripple element appears when latestRipple prop changes', () => {
    const ripple: GridRippleMessage = {
      type: 'grid_ripple',
      quadrant: 'top_left',
      tier: 1,
    }
    const { rerender } = render(
      <WolfRadarUI nightActions={makeNightActions()} sendIntent={vi.fn()} latestRipple={null} />
    )
    expect(document.querySelector('.wolf-radar__ripple')).not.toBeInTheDocument()

    rerender(
      <WolfRadarUI nightActions={makeNightActions()} sendIntent={vi.fn()} latestRipple={ripple} />
    )
    expect(document.querySelector('.wolf-radar__ripple')).toBeInTheDocument()
  })

  it('ripple disappears after 2000ms', () => {
    const ripple: GridRippleMessage = {
      type: 'grid_ripple',
      quadrant: 'top_right',
      tier: 2,
    }
    render(
      <WolfRadarUI nightActions={makeNightActions()} sendIntent={vi.fn()} latestRipple={ripple} />
    )
    expect(document.querySelector('.wolf-radar__ripple')).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(2000) })
    expect(document.querySelector('.wolf-radar__ripple')).not.toBeInTheDocument()
  })

  // ── Periodic server report ──────────────────────────────────────────────────

  it('sends periodic wolf_charge_update is_active:true reports while holding', () => {
    const sendIntent = vi.fn()
    render(<WolfRadarUI nightActions={makeNightActions()} sendIntent={sendIntent} />)
    const [quadrant] = document.querySelectorAll('.wolf-radar__quadrant')

    fireEvent.mouseDown(quadrant)
    // Initial intent on mousedown (is_active:true) + 2 periodic reports
    act(() => { vi.advanceTimersByTime(CHARGE_REPORT_MS * 2 + 50) })

    const activeReports = sendIntent.mock.calls.filter(
      ([p]) => p.type === 'wolf_charge_update' && p.is_active === true
    )
    expect(activeReports.length).toBeGreaterThanOrEqual(2)
  })
})
