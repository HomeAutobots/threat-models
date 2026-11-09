import { Loader, Text } from '@mantine/core'
import { Navigate, useParams } from 'react-router'
import { useSystems } from '../api/queries'
import type { Reg } from '../api/types'
import { AppShell } from '../components/AppShell'

/** `/` and `/:reg`: open the register's first system, or say there is none. */
export function Home({ reg }: { reg: Reg }) {
  const systems = useSystems(reg)
  let body
  if (systems.isLoading) {
    body = <Loader size="sm" aria-label="Loading" />
  } else if (systems.data && systems.data.length > 0) {
    return <Navigate to={`/${reg}/${encodeURIComponent(systems.data[0].slug)}/register`} replace />
  } else if (systems.isError) {
    body = <Text c="red">Could not load systems: {systems.error.message}</Text>
  } else {
    body = <Text>No systems yet. Create one in the terminal with ./tmreg init-system.</Text>
  }
  return <AppShell reg={reg}>{body}</AppShell>
}

/** `/:reg`: Home for that register; any other first segment goes to `/`. */
export function RegisterHome() {
  const { reg } = useParams()
  if (reg !== 'main' && reg !== 'trial') return <Navigate to="/" replace />
  return <Home reg={reg} />
}
