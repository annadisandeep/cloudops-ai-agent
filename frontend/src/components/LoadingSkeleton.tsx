export function LoadingSkeleton({
  rows = 4,
  className = '',
}: {
  rows?: number
  className?: string
}) {
  return (
    <div
      data-testid="loading-skeleton"
      aria-busy="true"
      aria-label="Loading"
      className={`space-y-2.5 ${className}`}
    >
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded bg-surface"
          style={{ width: `${100 - (i % 3) * 12}%` }}
        />
      ))}
    </div>
  )
}
