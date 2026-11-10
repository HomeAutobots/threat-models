import { Navigate, type RouteObject } from 'react-router'
import { ArchitecturePage } from './pages/ArchitecturePage'
import { EditRiskPage } from './pages/EditRiskPage'
import { HistoryPage } from './pages/HistoryPage'
import { Home, RegisterHome } from './pages/Home'
import { RegisterPage } from './pages/RegisterPage'
import { ReportsPage } from './pages/ReportsPage'
import { ReviewPage } from './pages/ReviewPage'
import { RiskPage } from './pages/RiskPage'
import { Root, SystemLayout } from './pages/Layouts'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Root />,
    children: [
      { index: true, element: <Home reg="main" /> },
      { path: ':reg', element: <RegisterHome /> },
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
          { path: 'architecture', element: <ArchitecturePage /> },
          { path: 'dfd', element: <Navigate to="../architecture" replace /> },
          { path: 'history', element: <HistoryPage /> },
          { path: 'reports', element: <ReportsPage /> },
        ],
      },
    ],
  },
]
