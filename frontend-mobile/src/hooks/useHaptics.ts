/** Wraps navigator.vibrate with a silent no-op fallback for iOS Safari.
 *  ADR-003 §4 — no visible fallback; secrecy constraint takes precedence. */
export function useHaptics() {
  const vibrate = (pattern: number | number[]) => {
    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
      navigator.vibrate(pattern)
    }
  }
  return { vibrate }
}
