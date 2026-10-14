import { useMemo, useRef, useState } from 'react'
import type { MetricPoint } from '../api/types'

const VIEW_W = 600
const VIEW_H = 160
const PAD_X = 4
const PAD_Y = 10

function formatValue(value: number, unit?: string): string {
  const abs = Math.abs(value)
  let text: string
  if (abs >= 1_000_000) text = `${(value / 1_000_000).toFixed(1)}M`
  else if (abs >= 10_000) text = `${(value / 1_000).toFixed(1)}k`
  else if (Number.isInteger(value)) text = String(value)
  else text = value.toFixed(1)
  if (unit === 'percent') return `${text}%`
  if (unit && unit !== 'count') return `${text} ${unit}`
  return text
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toISOString().slice(11, 16) + ' UTC'
}

export function MetricChart({
  points,
  unit,
  threshold,
  height = 160,
  ariaLabel = 'Metric chart',
}: {
  points: MetricPoint[]
  unit?: string
  /** Optional threshold — the region above it is shaded subtly. */
  threshold?: number
  height?: number
  ariaLabel?: string
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  const { min, max, last, coords, polyline, thresholdY } = useMemo(() => {
    if (points.length === 0) {
      return {
        min: 0,
        max: 0,
        last: 0,
        coords: [] as { x: number; y: number }[],
        polyline: '',
        thresholdY: null as number | null,
      }
    }
    const values = points.map((p) => p.value)
    let lo = Math.min(...values)
    let hi = Math.max(...values)
    if (threshold !== undefined) {
      lo = Math.min(lo, threshold)
      hi = Math.max(hi, threshold)
    }
    if (hi === lo) {
      hi += 1
      lo -= 1
    }
    const span = hi - lo
    const plotW = VIEW_W - PAD_X * 2
    const plotH = VIEW_H - PAD_Y * 2
    const xFor = (i: number) =>
      points.length === 1
        ? PAD_X + plotW / 2
        : PAD_X + (i / (points.length - 1)) * plotW
    const yFor = (v: number) => PAD_Y + (1 - (v - lo) / span) * plotH
    const coords = points.map((p, i) => ({ x: xFor(i), y: yFor(p.value) }))
    return {
      min: Math.min(...values),
      max: Math.max(...values),
      last: values[values.length - 1],
      coords,
      polyline: coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' '),
      thresholdY: threshold !== undefined ? yFor(threshold) : null,
    }
  }, [points, threshold])

  if (points.length === 0) {
    return (
      <div
        data-testid="metric-chart-empty"
        className="flex items-center justify-center rounded border border-dashed border-line text-xs text-muted"
        style={{ height }}
      >
        No data points for this window
      </div>
    )
  }

  const handleMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    if (rect.width === 0) return
    const ratio = (e.clientX - rect.left) / rect.width
    const idx = Math.round(ratio * (points.length - 1))
    setHoverIndex(Math.max(0, Math.min(points.length - 1, idx)))
  }

  const hover = hoverIndex !== null ? points[hoverIndex] : null
  const hoverCoord = hoverIndex !== null ? coords[hoverIndex] : null
  const gridlines = [0.2, 0.4, 0.6, 0.8].map(
    (f) => PAD_Y + f * (VIEW_H - PAD_Y * 2),
  )

  return (
    <div ref={containerRef} className="relative" data-testid="metric-chart">
      <svg
        role="img"
        aria-label={ariaLabel}
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        className="block w-full"
        style={{ height }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {gridlines.map((y) => (
          <line
            key={y}
            x1={PAD_X}
            x2={VIEW_W - PAD_X}
            y1={y}
            y2={y}
            stroke="var(--color-border)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {thresholdY !== null && (
          <>
            <rect
              x={PAD_X}
              y={PAD_Y}
              width={VIEW_W - PAD_X * 2}
              height={Math.max(0, thresholdY - PAD_Y)}
              fill="#DC2626"
              opacity="0.06"
            />
            <line
              x1={PAD_X}
              x2={VIEW_W - PAD_X}
              y1={thresholdY}
              y2={thresholdY}
              stroke="#DC2626"
              strokeWidth="1"
              strokeDasharray="4 3"
              opacity="0.5"
              vectorEffect="non-scaling-stroke"
            />
          </>
        )}
        <polyline
          data-testid="metric-polyline"
          points={polyline}
          fill="none"
          stroke="var(--color-text)"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
        {hoverCoord && (
          <>
            <line
              x1={hoverCoord.x}
              x2={hoverCoord.x}
              y1={PAD_Y}
              y2={VIEW_H - PAD_Y}
              stroke="var(--color-text-secondary)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
            <circle
              cx={hoverCoord.x}
              cy={hoverCoord.y}
              r="3"
              fill="var(--color-text)"
            />
          </>
        )}
      </svg>

      {hover && hoverCoord && (
        <div
          data-testid="metric-tooltip"
          className="pointer-events-none absolute top-1 z-10 -translate-x-1/2 whitespace-nowrap rounded border border-line bg-bg px-2 py-1 font-mono text-2xs shadow-sm tnum"
          style={{
            left: `${Math.min(92, Math.max(8, (hoverCoord.x / VIEW_W) * 100))}%`,
          }}
        >
          <span className="text-muted">{formatTime(hover.timestamp)}</span>{' '}
          <span className="font-medium">{formatValue(hover.value, unit)}</span>
        </div>
      )}

      <div className="mt-1.5 flex items-center gap-4 font-mono text-2xs text-muted tnum">
        <span>
          min <span className="text-fg">{formatValue(min, unit)}</span>
        </span>
        <span>
          max <span className="text-fg">{formatValue(max, unit)}</span>
        </span>
        <span>
          last <span className="text-fg">{formatValue(last, unit)}</span>
        </span>
      </div>
    </div>
  )
}
