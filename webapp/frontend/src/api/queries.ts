import { MutationCache, QueryCache, QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSyncExternalStore } from 'react'
import { ApiError, apiGet, apiPath, apiPost } from './client'
import type { C4ExportResponse, C4Response, C4RoutesResponse, Change, DfdResponse, Meta, Reg, Risk, RiskDetail, Session, System } from './types'

// ---- signed-out flag: set when any query or mutation fails with 401 ----------------------------

let signedOut = false
const listeners = new Set<() => void>()

function markSignedOut(error: unknown) {
  if (error instanceof ApiError && error.status === 401 && !signedOut) {
    signedOut = true
    listeners.forEach((l) => l())
  }
}

export function useSignedOut(): boolean {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => signedOut,
  )
}

/** For tests: forget a previous 401. */
export function resetSignedOut(): void {
  signedOut = false
  listeners.forEach((l) => l())
}

export function makeQueryClient(): QueryClient {
  resetSignedOut()
  return new QueryClient({
    queryCache: new QueryCache({ onError: markSignedOut }),
    mutationCache: new MutationCache({ onError: markSignedOut }),
    // The server is on this machine, so a window `offline` event must not pause requests.
    defaultOptions: {
      queries: {
        networkMode: 'always',
        refetchOnWindowFocus: false,
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
      },
      mutations: { networkMode: 'always' },
    },
  })
}

// ---- queries -----------------------------------------------------------------------------------

export function useSession() {
  return useQuery({ queryKey: ['session'], queryFn: () => apiGet<Session>('/api/session') })
}

export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: () => apiGet<Meta>('/api/meta'),
    staleTime: Infinity,
  })
}

export function useSystems(reg: Reg) {
  return useQuery({
    queryKey: [reg, 'systems'],
    queryFn: () => apiGet<System[]>(`/api/${reg}/systems`),
  })
}

export function useRisks(reg: Reg, slug: string) {
  return useQuery({
    queryKey: [reg, slug, 'risks'],
    queryFn: () => apiGet<Risk[]>(apiPath(reg, slug, 'risks')),
    enabled: !!slug,
  })
}

export function useRisk(reg: Reg, slug: string, id: string) {
  return useQuery({
    queryKey: [reg, slug, 'risk', id],
    queryFn: () => apiGet<RiskDetail>(apiPath(reg, slug, 'risks', id)),
    enabled: !!slug && !!id,
  })
}

export function useRiskHistory(reg: Reg, slug: string, id: string) {
  return useQuery({
    queryKey: [reg, slug, 'risk', id, 'history'],
    queryFn: () => apiGet<Change[]>(apiPath(reg, slug, 'risks', id, 'history')),
    enabled: !!slug && !!id,
  })
}

export function useHistory(reg: Reg, slug: string) {
  return useQuery({
    queryKey: [reg, slug, 'history'],
    queryFn: () => apiGet<Change[]>(apiPath(reg, slug, 'history')),
    enabled: !!slug,
  })
}

export function useVerify(reg: Reg, slug: string) {
  return useQuery({
    queryKey: [reg, slug, 'verify'],
    queryFn: () => apiGet<{ problems: string[] }>(apiPath(reg, slug, 'verify')),
    enabled: !!slug,
  })
}

export function useDfd(reg: Reg, slug: string) {
  return useQuery({
    queryKey: [reg, slug, 'dfd'],
    queryFn: () => apiGet<DfdResponse>(apiPath(reg, slug, 'dfd')),
    enabled: !!slug,
  })
}

export function useC4(reg: Reg, slug: string) {
  return useQuery({
    queryKey: [reg, slug, 'c4'],
    queryFn: () => apiGet<C4Response>(apiPath(reg, slug, 'c4')),
    enabled: !!slug,
  })
}

/** Chains of paths between two items; runs only when both ends are chosen. */
export function useC4Routes(reg: Reg, slug: string, from: string | null, to: string | null) {
  return useQuery({
    queryKey: [reg, slug, 'c4', 'routes', from, to],
    queryFn: () =>
      apiGet<C4RoutesResponse>(`${apiPath(reg, slug, 'c4', 'routes')}?from=${encodeURIComponent(from ?? '')}&to=${encodeURIComponent(to ?? '')}`),
    enabled: !!slug && !!from && !!to,
    retry: false,
  })
}

/** Exports the current file with Structurizr; on success the system's queries are refetched. */
export function useC4Export(reg: Reg, slug: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<C4ExportResponse>(apiPath(reg, slug, 'c4', 'export'), {}),
    onSuccess: () => client.invalidateQueries({ queryKey: [reg, slug] }),
  })
}

/** POST to a path from `apiPath`; on success every query of that system is refetched. */
export function useAction(reg: Reg, slug: string) {
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) => apiPost<unknown>(path, body),
    onSuccess: () => client.invalidateQueries({ queryKey: [reg, slug] }),
  })
  return { ...mutation, mutateAsync: mutation.mutateAsync }
}
