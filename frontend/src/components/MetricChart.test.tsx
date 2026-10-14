import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MetricChart } from './MetricChart'
import type { MetricPoint } from '../api/types'

const points: MetricPoint[] = [
  { timestamp: '2026-02-01T14:00:00Z', value: 10 },
  { timestamp: '2026-02-01T14:01:00Z', value: 93.4 },
  { timestamp: '2026-02-01T14:02:00Z', value: 50 },
]

describe('MetricChart', () => {
  it('renders a polyline with one coordinate per point', () => {
    render(<MetricChart points={points} unit="percent" />)
    const polyline = screen.getByTestId('metric-polyline')
    const coords = polyline.getAttribute('points')?.trim().split(' ') ?? []
    expect(coords).toHaveLength(points.length)
  })

  it('shows min / max / last summary values', () => {
    render(<MetricChart points={points} unit="percent" />)
    expect(screen.getByText('10%')).toBeInTheDocument()
    expect(screen.getByText('93.4%')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('min')).toBeInTheDocument()
    expect(screen.getByText('max')).toBeInTheDocument()
    expect(screen.getByText('last')).toBeInTheDocument()
  })

  it('renders an empty state when there are no points', () => {
    render(<MetricChart points={[]} />)
    expect(screen.getByTestId('metric-chart-empty')).toBeInTheDocument()
    expect(screen.queryByTestId('metric-polyline')).not.toBeInTheDocument()
  })

  it('handles a single point without NaN coordinates', () => {
    render(<MetricChart points={[points[0]]} />)
    const polyline = screen.getByTestId('metric-polyline')
    expect(polyline.getAttribute('points')).not.toContain('NaN')
  })
})
