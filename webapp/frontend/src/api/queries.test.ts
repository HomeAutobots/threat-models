import { onlineManager } from '@tanstack/react-query'
import { afterEach, describe, expect, it } from 'vitest'
import { makeQueryClient } from './queries'

describe('makeQueryClient', () => {
  afterEach(() => {
    onlineManager.setOnline(true)
  })

  it('runs queries and mutations while the browser reports offline, since the server is local', async () => {
    onlineManager.setOnline(false)
    const client = makeQueryClient()
    await expect(client.fetchQuery({ queryKey: ['x'], queryFn: async () => 'read' })).resolves.toBe('read')
    const mutation = client.getMutationCache().build(client, { mutationFn: async () => 'written' })
    await expect(mutation.execute(undefined)).resolves.toBe('written')
  })
})
