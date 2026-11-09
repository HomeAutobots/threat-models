import { Loader } from '@mantine/core'
import { Navigate, Outlet, useParams, type RouteObject } from 'react-router'
import { useSession, useSignedOut } from './api/queries'
import type { Reg } from './api/types'
import { AppShell } from './components/AppShell'
import { DfdPage } from './pages/DfdPage'
import { EditRiskPage } from './pages/EditRiskPage'
import { HistoryPage } from './pages/HistoryPage'
import { Home } from './pages/Home'
import { RegisterPage } from './pages/RegisterPage'
import { ReportsPage } from './pages/ReportsPage'
import { ReviewPage } from './pages/ReviewPage'
import { RiskPage } from './pages/RiskPage'
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
          { path: 'register', element: <RegisterPage /> },
          { path: 'review', element: <ReviewPage /> },
          { path: 'risks/new', element: <EditRiskPage mode="add" /> },
          { path: 'risks/:id', element: <RiskPage /> },
          { path: 'risks/:id/edit', element: <EditRiskPage mode="edit" /> },
          { path: 'dfd', element: <DfdPage /> },
          { path: 'history', element: <HistoryPage /> },
          { path: 'reports', element: <ReportsPage /> },
        ],
      },
    ],
  },
]
