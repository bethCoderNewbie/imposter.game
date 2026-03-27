import '@testing-library/jest-dom'

// jsdom does not implement HTMLMediaElement.play/pause
Object.defineProperty(window.HTMLMediaElement.prototype, 'play', {
  writable: true,
  value: vi.fn().mockResolvedValue(undefined),
})
Object.defineProperty(window.HTMLMediaElement.prototype, 'pause', {
  writable: true,
  value: vi.fn(),
})

// jsdom does not implement requestFullscreen
Object.defineProperty(document.documentElement, 'requestFullscreen', {
  writable: true,
  value: vi.fn().mockResolvedValue(undefined),
})
