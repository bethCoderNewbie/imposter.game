import { render, screen } from '@testing-library/react'
import NarratorSubtitle from '../../components/NarratorSubtitle/NarratorSubtitle'

describe('NarratorSubtitle', () => {
  it('renders nothing when text is null', () => {
    const { container } = render(<NarratorSubtitle text={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders the narrator text when provided', () => {
    render(<NarratorSubtitle text="Night falls over the village." />)
    expect(screen.getByText('Night falls over the village.')).toBeInTheDocument()
  })

  it('has the narrator-subtitle CSS class', () => {
    const { container } = render(<NarratorSubtitle text="Test narration." />)
    const el = container.firstChild as HTMLElement
    expect(el).toHaveClass('narrator-subtitle')
  })
})
