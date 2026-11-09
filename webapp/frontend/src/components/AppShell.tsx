import { AppShell as MantineAppShell, Alert, Badge, Group, NavLink, SegmentedControl, Select, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import { NavLink as RouterLink, useLocation, useNavigate } from 'react-router'
import { useRisks, useSession, useSystems } from '../api/queries'
import type { Reg } from '../api/types'

export const TRIAL_BANNER = 'Trial register: practice data, not the real register'

const SECTIONS = ['register', 'review', 'dfd', 'history', 'reports']

interface Props {
  reg: Reg
  slug?: string
  children?: ReactNode
}

export function AppShell({ reg, slug, children }: Props) {
  const session = useSession()
  const systems = useSystems(reg)
  const risks = useRisks(reg, slug ?? '')
  const navigate = useNavigate()
  const { pathname } = useLocation()

  // The page the owner is on, kept when the system or register changes.
  const section = SECTIONS.find((s) => pathname.split('/')[3] === s) ?? 'register'
  const pending = (risks.data ?? []).filter((r) => r.review_state === 'pending').length
  const base = slug ? `/${reg}/${encodeURIComponent(slug)}` : null

  const links: [string, string, ReactNode?][] = [
    ['register', 'Register'],
    ['review', 'Review queue', <PendingBadge key="n" count={pending} />],
    ['history', 'History'],
    ['dfd', 'DFD'],
    ['reports', 'Reports'],
  ]

  return (
    <MantineAppShell header={{ height: 64 }} navbar={{ width: 220, breakpoint: 'sm' }} padding="md">
      <MantineAppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group wrap="nowrap">
            <Title order={1} size="h3">Threat models</Title>
            <Select
              aria-label="System"
              placeholder="Choose a system"
              data={(systems.data ?? []).map((s) => ({ value: s.slug, label: s.name || s.slug }))}
              value={slug ?? null}
              allowDeselect={false}
              onChange={(v) => v && navigate(`/${reg}/${encodeURIComponent(v)}/${section}`)}
            />
            {session.data?.trial && (
              <SegmentedControl
                aria-label="Register"
                value={reg}
                data={[
                  { value: 'main', label: 'Main' },
                  { value: 'trial', label: 'Trial' },
                ]}
                onChange={(v) => navigate(slug ? `/${v}/${encodeURIComponent(slug)}/${section}` : `/${v}`)}
              />
            )}
          </Group>
          {session.data && <Text size="sm">Signed in as {session.data.reviewer}</Text>}
        </Group>
      </MantineAppShell.Header>
      <MantineAppShell.Navbar p="sm">
        <nav aria-label="Pages">
          {base &&
            links.map(([path, label, right]) => (
              <NavLink
                key={path}
                component={RouterLink}
                to={`${base}/${path}`}
                label={label}
                rightSection={right}
              />
            ))}
        </nav>
      </MantineAppShell.Navbar>
      <MantineAppShell.Main>
        {reg === 'trial' && (
          <Alert color="orange" variant="filled" mb="md" role="status">
            {TRIAL_BANNER}
          </Alert>
        )}
        {children}
      </MantineAppShell.Main>
    </MantineAppShell>
  )
}

function PendingBadge({ count }: { count: number }) {
  return count > 0 ? <Badge size="sm" circle aria-label={`${count} pending`}>{count}</Badge> : null
}
