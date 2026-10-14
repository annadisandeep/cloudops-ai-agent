import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { HistoryPage } from './HistoryPage'
import { renderWithProviders, jsonResponse } from '../test/utils'
import { fixtureEmptyInvestigations } from '../test/fixtures'

describe('HistoryPage', () => {
  it('renders the empty state with a CTA when there are no investigations', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(fixtureEmptyInvestigations)),
    )

    renderWithProviders(<HistoryPage />)

    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByText('No investigations yet')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'New investigation' }),
    ).toBeInTheDocument()
  })
})
