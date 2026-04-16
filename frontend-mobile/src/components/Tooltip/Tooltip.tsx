import { useEffect, useRef, useState } from 'react'
import './Tooltip.css'

interface TooltipProps {
  text: string
  position?: 'above' | 'below'
}

const AUTO_DISMISS_MS = 4000

/** Inline ? button that shows a popover on tap/click.
 *  Auto-dismisses after 4 s. Tap again or click outside to dismiss early. */
export default function Tooltip({ text, position = 'above' }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const btnRef = useRef<HTMLButtonElement>(null)

  function show(e: React.MouseEvent | React.TouchEvent) {
    e.stopPropagation()
    if (open) { close(); return }
    setOpen(true)
    timerRef.current = setTimeout(close, AUTO_DISMISS_MS)
  }

  function close() {
    setOpen(false)
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  // Dismiss on outside tap
  useEffect(() => {
    if (!open) return
    function handleOutside(e: MouseEvent | TouchEvent) {
      if (btnRef.current && !btnRef.current.parentElement?.contains(e.target as Node)) {
        close()
      }
    }
    document.addEventListener('mousedown', handleOutside)
    document.addEventListener('touchstart', handleOutside)
    return () => {
      document.removeEventListener('mousedown', handleOutside)
      document.removeEventListener('touchstart', handleOutside)
    }
  }, [open])

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  return (
    <span className="tooltip-wrap">
      <button
        ref={btnRef}
        className="tooltip-trigger"
        aria-label="Help"
        aria-expanded={open}
        onClick={show}
        onTouchEnd={show}
        type="button"
      >
        ?
      </button>
      {open && (
        <span
          className={`tooltip-popover tooltip-popover--${position}`}
          role="tooltip"
        >
          {text}
        </span>
      )}
    </span>
  )
}
