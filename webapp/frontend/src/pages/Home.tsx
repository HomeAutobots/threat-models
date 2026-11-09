import { Loader, Text } from '@mantine/core'
import { Navigate } from 'react-router'
import { useSystems } from '../api/queries'
import { AppShell } from '../components/AppShell'

export function Home() {
  const systems = useSystems('main')
  let body
  if (systems.isLoading) {
    body = <Loader size="sm" aria-label="Loading" />
  } else if (systems.data && systems.data.length > 0) {
    return <Navigate to={`/main/${encodeURIComponent(systems.data[0].slug)}/register`} replace />
  } else if (systems.isError) {
    body = <Text c="red">Could not load systems: {systems.error.message}</Text>
  } else {
    body = <Text>No systems yet. Create one in the terminal with ./tmreg init-system.</Text>
  }
  return <AppShell reg="main">{body}</AppShell>
}
