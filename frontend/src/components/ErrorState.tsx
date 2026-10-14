import { AlertCircle, RotateCw } from 'lucide-react'

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div
      role="alert"
      data-testid="error-state"
      className="flex flex-col items-center justify-center gap-2 rounded-md border border-line px-6 py-12 text-center"
    >
      <AlertCircle aria-hidden="true" size={20} className="text-crit" />
      <p className="text-sm font-medium">Something went wrong</p>
      <p className="max-w-md text-xs text-muted">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary mt-2">
          <RotateCw size={13} aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  )
}
