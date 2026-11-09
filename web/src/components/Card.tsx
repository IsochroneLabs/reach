// Sidebar card: a title that collapses the body (state kept in the settings), optional controls
// next to the title and a one-line "What does this show?" toggle with a short explanation.
// A button with aria-expanded instead of <details>, so controls in the header stay usable.
import { useId, useState, type ReactNode } from 'react'

interface Props {
  title: string
  label?: string
  id?: string
  open: boolean
  onToggle: (open: boolean) => void
  help?: string
  extra?: ReactNode
  className?: string
  busy?: boolean
  children: ReactNode
}

export default function Card({ title, label, id, open, onToggle, help, extra, className, busy, children }: Props) {
  const [helpOpen, setHelpOpen] = useState(false)
  const bodyId = useId()
  return (
    <section id={id} className={`card${className ? ` ${className}` : ''}`} aria-label={label ?? title} aria-busy={busy}>
      <header className="card-head">
        <h2>
          <button type="button" className="card-toggle" aria-expanded={open} aria-controls={bodyId} onClick={() => onToggle(!open)}>
            <span className="chevron" aria-hidden="true">
              {open ? '▾' : '▸'}
            </span>
            {title}
          </button>
        </h2>
        {extra}
      </header>
      <div id={bodyId} hidden={!open}>
        {help && (
          <div className="card-help">
            <button type="button" className="link-btn small help-btn" aria-expanded={helpOpen} onClick={() => setHelpOpen(!helpOpen)}>
              What does this show?
            </button>
            {helpOpen && <p className="muted small">{help}</p>}
          </div>
        )}
        {children}
      </div>
    </section>
  )
}
