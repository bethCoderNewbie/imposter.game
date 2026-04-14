import './NarratorSubtitle.css'

interface Props {
  text: string | null
}

export default function NarratorSubtitle({ text }: Props) {
  if (!text) return null
  return (
    <div className="narrator-subtitle" role="status" aria-live="polite">
      {text}
    </div>
  )
}
