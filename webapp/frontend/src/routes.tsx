import { Loader, Text } from '@mantine/core'
import { Navigate, Outlet, useParams, type RouteObject } from 'react-router'
import { useSession, useSignedOut } from './api/queries'
import type { Reg } from './api/types'
import { AppShell } from './components/AppShell'
import { Home } from './pages/Home'
import { ReviewPage } from './pages/ReviewPage'
import { SignedOut } from './pages/SignedOut'

function Root() {
  const signedOut = useSignedOut()
  const session = useSession()
  if (signedOut) return <SignedOut />
  if (session.isLoading) return <Loader m="xl" aria-label="Loading" />
  return <Outlet />
}

function SystemLayout() {
  const { reg, slug } = useParams()
  if ((reg !== 'main' && reg !== 'trial') || !slug) return <Navigate to="/" replace />
  return (
    <AppShell reg={reg as Reg} slug={slug}>
      <Outlet />
    </AppShell>
  )
}

// Tasks 9 to 12 replace these placeholders with the pages.
function Placeholder({ name }: { name: string }) {
  return <Text>{name}</Text>
}

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Root />,
    children: [
      { index: true, element: <Home /> },
      {
        path: ':reg/:slug',
        element: <SystemLayout />,
        children: [
          { index: true, element: <Navigate to="register" replace /> },
          { path: 'register', element: <Placeholder name="Register" /> },
          { path: 'review', element: <ReviewPage /> },
          { path: 'risks/new', element: <Placeholder name="New risk" /> },
          { path: 'risks/:id', element: <Placeholder name="Risk" /> },
          { path: 'risks/:id/edit', element: <Placeholder name="Edit risk" /> },
          { path: 'dfd', element: <Placeholder name="DFD" /> },
          { path: 'history', element: <Placeholder name="History" /> },
          { path: 'reports', element: <Placeholder name="Reports" /> },
        ],
      },
    ],
  },
]
