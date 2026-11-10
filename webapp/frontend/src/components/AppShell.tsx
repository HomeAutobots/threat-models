import { AppShell as MantineAppShell, Alert, Badge, Burger, Group, NavLink, SegmentedControl, Select, Text } from '@mantine/core'
import { useDisclosure, useElementSize } from '@mantine/hooks'
import { useEffect, useId, type ReactNode } from 'react'
import { NavLink as RouterLink, useLocation, useNavigate } from 'react-router'
import { useRisks, useSession, useSystems } from '../api/queries'
import type { Reg } from '../api/types'
import classes from './AppShell.module.css'

export const TRIAL_BANNER = 'Trial register: practice data, not the real register'

const SECTIONS = ['register', 'review', 'architecture', 'history', 'reports']
const HEADER_MIN_HEIGHT = 64

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
  const { pathname, search } = useLocation()
  // Below the `sm` breakpoint the navbar covers the page, so it starts closed behind a Burger.
  const [navOpened, nav] = useDisclosure(false)
  const navbarId = useId()
  // Any navigation closes the mobile navbar, not only a click on one of its links.
  const closeNav = nav.close
  useEffect(() => {
    closeNav()
  }, [pathname, search, closeNav])
  // The header wraps at narrow widths, so its height follows its content.
  const { ref: headerRef, height: headerContentHeight } = useElementSize()
  const headerHeight = Math.max(HEADER_MIN_HEIGHT, Math.ceil(headerContentHeight) + 16)

  // The page the owner is on, kept when the system or register changes.
  const section = SECTIONS.find((s) => pathname.split('/')[3] === s) ?? 'register'
  const pending = (risks.data ?? []).filter((r) => r.review_state === 'pending').length
  const base = slug ? `/${reg}/${encodeURIComponent(slug)}` : null

  const links: [string, string, ReactNode?][] = [
    ['register', 'Register'],
    ['review', 'Review queue', <PendingBadge key="n" count={pending} />],
    ['history', 'History'],
    ['architecture', 'Architecture'],
    ['reports', 'Reports'],
  ]

  return (
    <MantineAppShell
      header={{ height: headerHeight }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !navOpened } }}
      padding="md"
    >
      <MantineAppShell.Header px="md" className={classes.header}>
        <Group ref={headerRef} w="100%" justify="space-between" gap="sm" wrap="wrap">
          <Group gap="sm" wrap="wrap">
            <Burger
              className={classes.burger}
              opened={navOpened}
              onClick={nav.toggle}
              size="sm"
              aria-label="Toggle navigation"
              aria-expanded={navOpened}
              aria-controls={navbarId}
            />
            {/* The app's name, not a heading: each page has its own h1. */}
            <Text component="span" fw={700} fz="h3">
              Threat models
            </Text>
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
      <MantineAppShell.Navbar
        p="sm"
        id={navbarId}
        aria-label="Pages"
        className={classes.navbar}
        mod={{ collapsed: !navOpened }}
      >
        {base &&
          links.map(([path, label, right]) => (
            <NavLink
              key={path}
              component={RouterLink}
              to={`${base}/${path}`}
              label={label}
              rightSection={right}
              onClick={nav.close}
            />
          ))}
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
