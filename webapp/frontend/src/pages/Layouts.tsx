import { Loader } from '@mantine/core'
import { Navigate, Outlet, useParams } from 'react-router'
import { useSession, useSignedOut } from '../api/queries'
import type { Reg } from '../api/types'
import { AppShell } from '../components/AppShell'
import { SignedOut } from './SignedOut'

export function Root() {
  const signedOut = useSignedOut()
  const session = useSession()
  if (signedOut) return <SignedOut />
  if (session.isLoading) return <Loader m="xl" aria-label="Loading" />
  return <Outlet />
}

export function SystemLayout() {
  const { reg, slug } = useParams()
  if ((reg !== 'main' && reg !== 'trial') || !slug) return <Navigate to="/" replace />
  return (
    <AppShell reg={reg as Reg} slug={slug}>
      <Outlet />
    </AppShell>
  )
}
