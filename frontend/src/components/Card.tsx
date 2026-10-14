import type { ReactNode } from 'react'

export function Card({
  children,
  className = '',
  title,
  actions,
}: {
  children: ReactNode
  className?: string
  title?: ReactNode
  actions?: ReactNode
}) {
  return (
    <section className={`rounded-md border border-line bg-bg ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <h2 className="text-[13px] font-semibold">{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}
