import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ResourcesPage } from './ResourcesPage'
import { renderWithProviders, jsonResponse } from '../test/utils'
import { fixtureResources } from '../test/fixtures'

function stubResourcesFetch() {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/v1/resources')) {
      return Promise.resolve(jsonResponse(fixtureResources))
    }
    return Promise.resolve(jsonResponse({ items: [], total: 0, page: 1, page_size: 20 }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('ResourcesPage', () => {
  it('renders resource rows from the API', async () => {
    stubResourcesFetch()
    renderWithProviders(<ResourcesPage />)

    expect(await screen.findByText('web-frontend-1')).toBeInTheDocument()
    expect(screen.getByText('db-primary-1')).toBeInTheDocument()
    expect(screen.getByText('e2-standard-2')).toBeInTheDocument()
    // Pagination summary
    expect(screen.getByText('1–2 of 2')).toBeInTheDocument()
  })

  it('refetches with the q parameter when searching', async () => {
    const fetchMock = stubResourcesFetch()
    const user = userEvent.setup()
    renderWithProviders(<ResourcesPage />)

    await screen.findByText('web-frontend-1')
    const initialCalls = fetchMock.mock.calls.length

    await user.type(screen.getByRole('searchbox', { name: 'Search resources' }), 'web')

    await waitFor(
      () => {
        const urls = fetchMock.mock.calls.map((call) => String(call[0]))
        expect(urls.some((u) => u.includes('q=web'))).toBe(true)
      },
      { timeout: 2000 },
    )
    expect(fetchMock.mock.calls.length).toBeGreaterThan(initialCalls)
  })

  it('shows the empty state when no resources match', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(jsonResponse({ items: [], total: 0, page: 1, page_size: 20 })),
    )
    renderWithProviders(<ResourcesPage />)
    expect(await screen.findByText('No resources found')).toBeInTheDocument()
  })
})
