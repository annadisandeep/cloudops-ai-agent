import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from './StatusBadge'
import { ProviderBadge } from './ProviderBadge'
import { SimulatedBadge } from './SimulatedBadge'

describe('StatusBadge', () => {
  it('renders the status label', () => {
    render(<StatusBadge status="completed" />)
    expect(screen.getByText('completed')).toBeInTheDocument()
  })

  it('maps statuses and severities to the right dot color', () => {
    const cases: Array<[string, string]> = [
      ['completed', 'bg-ok'],
      ['failed', 'bg-crit'],
      ['running', 'bg-warn'],
      ['queued', 'bg-muted'],
      ['critical', 'bg-crit'],
      ['high', 'bg-crit'],
      ['medium', 'bg-warn'],
      ['low', 'bg-muted'],
    ]
    for (const [status, dotClass] of cases) {
      const { unmount } = render(<StatusBadge status={status} />)
      const dot = screen.getByTestId('status-dot')
      expect(dot.className).toContain(dotClass)
      unmount()
    }
  })

  it('shows a spinner instead of a dot while running when requested', () => {
    render(<StatusBadge status="running" showSpinner />)
    expect(screen.getByRole('status', { name: 'Running' })).toBeInTheDocument()
    expect(screen.queryByTestId('status-dot')).not.toBeInTheDocument()
  })
})

describe('ProviderBadge', () => {
  it.each(['gcp', 'aws', 'demo'])('renders the %s provider badge', (provider) => {
    const { unmount } = render(<ProviderBadge provider={provider} />)
    const badge = screen.getByTestId('provider-badge')
    expect(badge).toHaveTextContent(provider)
    expect(badge.className).toContain('uppercase')
    unmount()
  })
})

describe('SimulatedBadge', () => {
  it('renders', () => {
    render(<SimulatedBadge />)
    expect(screen.getByText('Simulated')).toBeInTheDocument()
  })
})
