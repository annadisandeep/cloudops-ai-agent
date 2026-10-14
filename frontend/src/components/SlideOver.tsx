import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

export function SlideOver({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    panelRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40" role="presentation">
      <button
        type="button"
        aria-label="Close panel"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-black/20"
        tabIndex={-1}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : 'Detail panel'}
        tabIndex={-1}
        className="absolute inset-y-0 right-0 flex w-full max-w-[440px] flex-col border-l border-line bg-bg shadow-sm outline-none"
      >
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-line px-4">
          <h2 className="truncate text-sm font-semibold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-muted transition-colors duration-150 hover:bg-surface hover:text-fg"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
      </div>
    </div>
  )
}
