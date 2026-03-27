import { render, waitFor } from '@testing-library/react'
import VoteWeb from '../../components/VoteWeb/VoteWeb'

// Stub getBoundingClientRect for all elements in these tests
function stubBoundingRect(el: Element, rect: Partial<DOMRect>) {
  vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
    left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0,
    toJSON: () => '',
    ...rect,
  } as DOMRect)
}

describe('VoteWeb', () => {
  afterEach(() => vi.restoreAllMocks())

  it('renders null when votes is an empty object', async () => {
    const { container } = render(<VoteWeb votes={{}} />)
    // Effect runs, builds nothing, component stays null
    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('renders null when no [data-player-id] elements are in the DOM', async () => {
    const { container } = render(<VoteWeb votes={{ p1: 'p2' }} />)
    // cardMap is empty, nothing pushed to built
    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('renders SVG lines after mount when player DOM elements exist', async () => {
    const { container } = render(
      <div>
        <div data-player-id="p1" />
        <div data-player-id="p2" />
        <VoteWeb votes={{ p1: 'p2' }} />
      </div>
    )
    await waitFor(() =>
      expect(container.querySelector('line')).toBeInTheDocument()
    )
  })

  it('strokeWidth scales with vote count on the same target', async () => {
    const { container } = render(
      <div>
        <div data-player-id="p1" />
        <div data-player-id="p2" />
        <div data-player-id="p3" />
        <VoteWeb votes={{ p1: 'p3', p2: 'p3' }} /> {/* 2 votes on p3 */}
      </div>
    )
    await waitFor(() => {
      const lines = container.querySelectorAll('line')
      expect(lines.length).toBeGreaterThan(0)
      // strokeWidth = 1 + 2 * 1.5 = 4
      lines.forEach(line => {
        expect(parseFloat(line.getAttribute('stroke-width') ?? '0')).toBe(4)
      })
    })
  })

  it('renders one line per vote entry', async () => {
    const { container } = render(
      <div>
        <div data-player-id="p1" />
        <div data-player-id="p2" />
        <div data-player-id="p3" />
        <div data-player-id="p4" />
        <VoteWeb votes={{ p1: 'p2', p2: 'p3', p3: 'p4' }} />
      </div>
    )
    await waitFor(() => {
      expect(container.querySelectorAll('line')).toHaveLength(3)
    })
  })

  it('skips vote when voter DOM element is not found', async () => {
    const { container } = render(
      <div>
        {/* p1 is the voter but has no DOM element */}
        <div data-player-id="p2" />
        <VoteWeb votes={{ p1: 'p2' }} />
      </div>
    )
    await waitFor(() => expect(container.querySelector('line')).not.toBeInTheDocument())
  })

  it('skips vote when target DOM element is not found', async () => {
    const { container } = render(
      <div>
        <div data-player-id="p1" />
        {/* p2 is the target but has no DOM element */}
        <VoteWeb votes={{ p1: 'p2' }} />
      </div>
    )
    await waitFor(() => expect(container.querySelector('line')).not.toBeInTheDocument())
  })
})
