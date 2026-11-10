import { Alert, Anchor, Badge, Button, Checkbox, Group, Loader, NativeSelect, Table, Tabs, Text, TextInput, Title } from '@mantine/core'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useC4, useMeta, useRisks } from '../api/queries'
import type { Reg, Risk } from '../api/types'
import { WRAP_STYLE } from '../components/record/FieldValue'
import { formatActor, formatCategory, formatTime } from '../lib/format'
import { visible } from '../lib/visible'

type Tab = 'approved' | 'pending' | 'rejected' | 'retired'

const TABS: { id: Tab; label: string }[] = [
  { id: 'approved', label: 'Approved' },
  { id: 'pending', label: 'Pending review' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'retired', label: 'Retired' },
]

function tabOf(r: Risk): Tab {
  if (r.review_state === 'approved') return r.status === 'retired' ? 'retired' : 'approved'
  return r.review_state === 'rejected' ? 'rejected' : 'pending'
}

const sorted = (values: Iterable<string>) => [...new Set(values)].sort()
const options = (values: string[]) => [{ value: '', label: 'All' }, ...values.map((v) => ({ value: v, label: visible(v) }))]

export function RegisterPage() {
  const { reg, slug } = useParams()
  const navigate = useNavigate()
  const risks = useRisks(reg as Reg, slug ?? '')
  const meta = useMeta()
  const c4 = useC4(reg as Reg, slug ?? '')
  const model = c4.data?.latest_record ?? null
  const [tab, setTab] = useState<Tab>('approved')
  const [status, setStatus] = useState('')
  const [element, setElement] = useState('')
  const [inside, setInside] = useState(false)
  const [category, setCategory] = useState('')
  const [origin, setOrigin] = useState('')
  const [search, setSearch] = useState('')

  const all = useMemo(() => risks.data ?? [], [risks.data])
  const counts = useMemo(() => {
    const c: Record<Tab, number> = { approved: 0, pending: 0, rejected: 0, retired: 0 }
    for (const r of all) c[tabOf(r)]++
    return c
  }, [all])

  if (risks.error) return <Alert color="red">{visible(risks.error.message)}</Alert>
  if (meta.error) return <Alert color="red">{visible(meta.error.message)}</Alert>
  if (risks.isLoading || !meta.data) return <Loader m="xl" aria-label="Loading" />

  const base = `/${reg}/${encodeURIComponent(slug as string)}`
  const aiChanged = all.filter((r) => r.review_state === 'pending' && r.last_approved !== null).length
  // The chosen ID, and with the checkbox on every item whose `where` has it (its descendants).
  const wanted = new Set(element ? [element] : [])
  if (element && inside && model) {
    for (const [id, it] of Object.entries(model.items)) if (it.where.includes(element)) wanted.add(id)
  }
  const needle = search.trim().toLowerCase()

  const rows = all.filter(
    (r) =>
      tabOf(r) === tab &&
      (!status || r.status === status) &&
      (!element || (r.elements ?? []).some((e) => wanted.has(e))) &&
      (!category || r.category === category) &&
      (!origin || r.origin === origin) &&
      (!needle || r.id.toLowerCase().includes(needle) || (r.title ?? '').toLowerCase().includes(needle)),
  )
  const href = (r: Risk) =>
    tab === 'pending' ? `${base}/review?id=${encodeURIComponent(r.id)}` : `${base}/risks/${encodeURIComponent(r.id)}`

  return (
    <div>
      <Group justify="space-between" mb="md" wrap="wrap">
        <Title order={1} size="h3">
          Register
        </Title>
        <Group gap="xs">
          <Button component={Link} to={`${base}/risks/new`}>
            Add risk
          </Button>
          <Button component={Link} to={`${base}/reports`} variant="default">
            Report
          </Button>
        </Group>
      </Group>

      {aiChanged > 0 && (
        <Alert color="yellow" mb="md">
          <Group gap="sm">
            <Text inherit>
              {aiChanged === 1
                ? '1 approved risk was changed by AI and needs your review'
                : `${aiChanged} approved risks were changed by AI and need your review`}
            </Text>
            <Anchor component={Link} to={`${base}/review`} inherit>
              Review now
            </Anchor>
          </Group>
        </Alert>
      )}

      <Tabs value={tab} onChange={(v) => v && setTab(v as Tab)}>
        <Tabs.List mb="md">
          {TABS.map((t) => (
            <Tabs.Tab key={t.id} value={t.id} rightSection={<Badge variant="light">{counts[t.id]}</Badge>}>
              {t.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        {TABS.map((t) => (
          <Tabs.Panel key={t.id} value={t.id}>
            {t.id === tab && (
              <>
                <Group mb="md" align="end" wrap="wrap">
                  <TextInput label="Search" placeholder="ID or title" value={search} onChange={(e) => setSearch(e.currentTarget.value)} />
                  <NativeSelect
                    label="Status"
                    value={status}
                    onChange={(e) => setStatus(e.currentTarget.value)}
                    data={options(sorted([...(meta.data.statuses ?? []), ...all.map((r) => r.status).filter((s): s is string => !!s)]))}
                  />
                  <NativeSelect
                    label="Element"
                    value={element}
                    onChange={(e) => setElement(e.currentTarget.value)}
                    data={options(sorted(all.flatMap((r) => r.elements ?? [])))}
                  />
                  {model && (
                    <Checkbox
                      label="Include what's inside"
                      checked={inside}
                      onChange={(e) => setInside(e.currentTarget.checked)}
                      pb={6}
                    />
                  )}
                  <NativeSelect
                    label="Category"
                    value={category}
                    onChange={(e) => setCategory(e.currentTarget.value)}
                    data={[
                      { value: '', label: 'All' },
                      ...sorted(all.map((r) => r.category).filter((c): c is string => !!c)).map((c) => ({
                        value: c,
                        label: visible(formatCategory(c, meta.data)),
                      })),
                    ]}
                  />
                  <NativeSelect
                    label="Origin"
                    value={origin}
                    onChange={(e) => setOrigin(e.currentTarget.value)}
                    data={options(sorted([...(meta.data.origins ?? []), ...all.map((r) => r.origin).filter((o): o is string => !!o)]))}
                  />
                </Group>

                {rows.length === 0 ? (
                  <Text c="dimmed">No risks here.</Text>
                ) : (
                  <Table.ScrollContainer minWidth={900}>
                    <Table highlightOnHover>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>ID</Table.Th>
                          <Table.Th>Title</Table.Th>
                          <Table.Th>Elements</Table.Th>
                          <Table.Th>Category</Table.Th>
                          <Table.Th>Status</Table.Th>
                          <Table.Th>Origin</Table.Th>
                          <Table.Th>Drafted by</Table.Th>
                          <Table.Th>Updated</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {rows.map((r) => (
                          <Table.Tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => navigate(href(r))}>
                            <Table.Td style={WRAP_STYLE}>
                              <Anchor component={Link} to={href(r)} onClick={(e) => e.stopPropagation()}>
                                {visible(r.id)}
                              </Anchor>
                            </Table.Td>
                            <Table.Td style={WRAP_STYLE}>{visible(r.title ?? '')}</Table.Td>
                            <Table.Td style={WRAP_STYLE}>{visible((r.elements ?? []).join(', '))}</Table.Td>
                            <Table.Td style={WRAP_STYLE}>{visible(formatCategory(r.category, meta.data))}</Table.Td>
                            <Table.Td style={WRAP_STYLE}>{visible(r.status ?? '')}</Table.Td>
                            <Table.Td style={WRAP_STYLE}>{visible(r.origin ?? '')}</Table.Td>
                            <Table.Td style={WRAP_STYLE}>{visible(formatActor(r.drafted_by))}</Table.Td>
                            <Table.Td>{formatTime(r.updated_at)}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                )}
              </>
            )}
          </Tabs.Panel>
        ))}
      </Tabs>
    </div>
  )
}
