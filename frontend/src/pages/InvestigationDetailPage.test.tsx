import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { InvestigationDetailPage } from './InvestigationDetailPage'
import { renderWithProviders, jsonResponse } from '../test/utils'
import { fixtureCompletedInvestigation } from '../test/fixtures'

describe('InvestigationDetailPage', () => {
  it('renders steps, evidence and report for a completed investigation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(fixtureCompletedInvestigation)),
    )

    renderWithProviders(<InvestigationDetailPage />, {
      route: '/investigations/inv_8f3a2c',
      path: '/investigations/:id',
    })

    // Header
    expect(
      await screen.findByText('Why is my GCP VM experiencing high CPU utilization?'),
    ).toBeInTheDocument()

    // Steps (tool timeline)
    expect(screen.getAllByTestId('step-row')).toHaveLength(2)
    expect(screen.getByText('get_metrics')).toBeInTheDocument()
    expect(screen.getByText('get_logs')).toBeInTheDocument()
    expect(
      screen.getByText('60 points; min 12.1%, max 96.8%, last 94.2%'),
    ).toBeInTheDocument()

    // Evidence cards
    expect(screen.getAllByTestId('evidence-card')).toHaveLength(2)
    expect(screen.getByText('cpu_utilization for web-frontend-1')).toBeInTheDocument()

    // Report
    expect(screen.getByTestId('report-section')).toBeInTheDocument()
    expect(
      screen.getByText(/worker pool saturation/, { selector: 'p' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Traffic spike exceeding instance capacity'),
    ).toBeInTheDocument()
    expect(screen.getByText('Scale the instance group horizontally')).toBeInTheDocument()
    expect(screen.getByText('Export Markdown')).toBeInTheDocument()
    expect(screen.getByText('Copy link')).toBeInTheDocument()
  })

  it('stops polling once the investigation is completed', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(fixtureCompletedInvestigation))
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<InvestigationDetailPage />, {
      route: '/investigations/inv_8f3a2c',
      path: '/investigations/:id',
    })

    await screen.findByTestId('report-section')
    const callsAfterLoad = fetchMock.mock.calls.length

    // Wait past the 1s polling interval; a completed investigation must not refetch.
    await new Promise((resolve) => setTimeout(resolve, 1300))
    expect(fetchMock.mock.calls.length).toBe(callsAfterLoad)
  }, 10000)

  it('shows the failure banner for a failed investigation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          ...fixtureCompletedInvestigation,
          status: 'failed',
          report: null,
          error: 'tool timeout exceeded',
        }),
      ),
    )

    renderWithProviders(<InvestigationDetailPage />, {
      route: '/investigations/inv_8f3a2c',
      path: '/investigations/:id',
    })

    expect(await screen.findByText('Investigation failed')).toBeInTheDocument()
    expect(screen.getByText('tool timeout exceeded')).toBeInTheDocument()
    expect(screen.queryByTestId('report-section')).not.toBeInTheDocument()
  })
})
