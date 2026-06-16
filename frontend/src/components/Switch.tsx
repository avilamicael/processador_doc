interface SwitchProps {
  on: boolean
  onToggle: () => void
  title?: string
}

// Toggle/switch do design (track + knob), animado via CSS (.switch / .knob).
export function Switch({ on, onToggle, title }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      title={title}
      onClick={onToggle}
      className={on ? 'switch on' : 'switch'}
    >
      <span className="knob" />
    </button>
  )
}
