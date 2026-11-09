import '@mantine/core/styles.css'
import { MantineProvider } from '@mantine/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { initCsrf } from './api/client'
import { makeQueryClient } from './api/queries'
import { routes } from './routes'

const queryClient = makeQueryClient()
const router = createBrowserRouter(routes)

// The token must be in place before the first API call. A rejection still renders the app, whose
// first call then shows the signed-out page.
initCsrf()
  .catch(() => {})
  .finally(() => {
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <MantineProvider defaultColorScheme="auto">
          <QueryClientProvider client={queryClient}>
            <RouterProvider router={router} />
          </QueryClientProvider>
        </MantineProvider>
      </StrictMode>,
    )
  })
