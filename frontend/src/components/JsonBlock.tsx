import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

export function JsonBlock({
  data,
  label = 'Raw data',
  defaultOpen = false,
}: {
  data: unknown
  label?: string
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const text =
    typeof data === 'string' ? data : JSON.stringify(data, null, 2)

  return (
    <div className="rounded border border-line">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-2xs font-medium text-muted transition-colors duration-150 hover:text-fg"
      >
        {open ? (
          <ChevronDown size={12} aria-hidden="true" />
        ) : (
          <ChevronRight size={12} aria-hidden="true" />
        )}
        {label}
      </button>
      {open && (
        <pre className="max-h-72 overflow-auto border-t border-line bg-surface px-3 py-2 font-mono text-2xs leading-4 text-fg">
          {text}
        </pre>
      )}
    </div>
  )
}
