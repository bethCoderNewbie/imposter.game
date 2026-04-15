import './NarratorVisuals.css'

interface Props {
  visible: boolean
}

export default function NarratorVisuals({ visible }: Props) {
  if (!visible) return null
  return (
    <div id="visuals" aria-hidden="true">
      <svg viewBox="0 0 320 320" className="narrator-avatar-svg">
        <defs>
          <clipPath id="narrator-clip">
            <circle cx="50%" cy="50%" r="25%" />
          </clipPath>
        </defs>

        {/* Pulse ring — expands and fades to indicate active narration */}
        <circle cx="50%" cy="50%" r="50%" fill="white" fillOpacity="0.55">
          <animate
            attributeName="r"
            values="25%;30%;40%;25%;30%;25%;40%;25%"
            dur="2s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="fill-opacity"
            values="0.55;0.35;0.1;0.55;0.35;0.55;0.1;0.55"
            dur="2s"
            repeatCount="indefinite"
          />
        </circle>

        {/* Host avatar — circular clip */}
        <image
          height="50%"
          width="50%"
          x="25%"
          y="25%"
          href="/images/host.jpeg"
          clipPath="url(#narrator-clip)"
          preserveAspectRatio="xMidYMid slice"
        />
      </svg>
    </div>
  )
}
