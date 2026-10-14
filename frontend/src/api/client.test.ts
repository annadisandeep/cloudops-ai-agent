import { describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, createInvestigation, getConfig } from './client'
import { fixtureConfig } from '../test/fixtures'

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('apiFetch', () => {
  it('returns parsed JSON on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(fixtureConfig)),
    )
    const config = await getConfig()
    expect(config.demo_mode).toBe(true)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/config',
      expect.objectContaining({}),
    )
  })

  it('throws a typed ApiError from the error envelope', async () => {
    // Response bodies are single-use — return a fresh one per call.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          jsonResponse(
            { error: { code: 'not_found', message: 'Investigation inv_x not found' } },
            404,
          ),
        ),
      ),
    )
    const promise = apiFetch('/investigations/inv_x')
    await expect(promise).rejects.toBeInstanceOf(ApiError)
    try {
      await apiFetch('/investigations/inv_x')
    } catch (err) {
      const apiError = err as ApiError
      expect(apiError.code).toBe('not_found')
      expect(apiError.message).toBe('Investigation inv_x not found')
      expect(apiError.status).toBe(404)
    }
  })

  it('handles non-JSON error bodies gracefully', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('boom', { status: 500 })),
    )
    await expect(apiFetch('/overview')).rejects.toMatchObject({
      code: 'http_error',
      status: 500,
    })
  })

  it('wraps network failures in an ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')))
    await expect(apiFetch('/health')).rejects.toMatchObject({
      code: 'network_error',
      status: 0,
    })
  })

  it('POSTs investigation payloads as JSON', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ id: 'inv_1', status: 'running' }, 201))
    vi.stubGlobal('fetch', fetchMock)
    await createInvestigation({ question: 'Why?', provider: 'demo' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/investigations')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ question: 'Why?', provider: 'demo' })
  })
})
