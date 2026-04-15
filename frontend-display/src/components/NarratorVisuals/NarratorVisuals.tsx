import './NarratorVisuals.css'

interface Props {
  visible: boolean
}

export default function NarratorVisuals({ visible }: Props) {
  if (!visible) return null
  return (
    <div id="visuals" aria-hidden="true">
      <div className="visuals__cell" />
      <div className="visuals__cell" />
      <div className="visuals__cell" />
      <div className="visuals__cell" />
    </div>
  )
}
