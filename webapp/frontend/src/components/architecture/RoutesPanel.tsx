import { Alert, Badge, Group, List, Loader, Select, Stack, Text } from '@mantine/core'
import { useMemo, useState } from 'react'
import { ApiError } from '../../api/client'
import { useC4Routes } from '../../api/queries'
import type { C4Record, Reg, RouteRisks } from '../../api/types'
import { visible } from '../../lib/visible'
import { byId, idName } from './order'

interface Props {
  reg: Reg
  slug: string
  record: C4Record
}

const ENDS = /^(A|S|C|K)\d+$/

export function endpointOptions(record: C4Record) {
  return Object.entries(record.items)
    .filter(([id]) => ENDS.test(id))
    .sort(([a], [b]) => byId(a, b))
    .map(([id, it]) => ({ value: id, label: idName(id, it.name) }))
}

function Risks({ risks }: { risks: RouteRisks }) {
  const parts = [
    risks.open.length > 0 && `open: ${risks.open.map(visible).join(', ')}`,
    risks.pending.length > 0 && `pending: ${risks.pending.map(visible).join(', ')}`,
  ].filter(Boolean)
  return parts.length > 0 ? <Text size="xs">Risks {parts.join('; ')}</Text> : null
}

export function RoutesPanel({ reg, slug, record }: Props) {
  const [from, setFrom] = useState<string | null>(null)
  const [to, setTo] = useState<string | null>(null)
  const options = useMemo(() => endpointOptions(record), [record])
  const routes = useC4Routes(reg, slug, from, to)
  const err = routes.error
  return (
    <Stack gap="xs">
      <Group align="flex-end">
        <Select label="From" data={options} value={from} onChange={setFrom} searchable clearable />
        <Select label="To" data={options} value={to} onChange={setTo} searchable clearable />
      </Group>
      {routes.isFetching && <Loader size="sm" aria-label="Finding routes" />}
      {err && (
        <Alert color="red" style={{ overflowWrap: 'anywhere' }}>
          {visible(err instanceof ApiError ? err.detail : err.message)}
        </Alert>
      )}
      {routes.data && routes.data.chains.length === 0 && <Text size="sm">No route found.</Text>}
      {routes.data?.chains.map((chain, i) => (
        <Stack key={i} gap={4} component="section" aria-label={`Route ${i + 1}`}>
          <Text fw={600} size="sm">
            Route {i + 1}
          </Text>
          <List size="sm" type="ordered">
            {chain.hops.map((h) => {
              const envs = Object.entries(h.crossings).filter(([, tbs]) => tbs.length > 0)
              return (
                <List.Item key={h.path + h.from}>
                  <Group gap="xs">
                    <Text span size="sm">
                      {visible(`${h.path}: ${h.from} → ${h.to}`)}
                    </Text>
                    {h.against_arrow && <Badge color="orange">against the arrow</Badge>}
                  </Group>
                  {envs.map(([env, tbs]) => (
                    <Text key={env} size="xs">
                      {visible(`${env} crosses ${tbs.join(', ')}`)}
                    </Text>
                  ))}
                  <Risks risks={h.risks} />
                </List.Item>
              )
            })}
          </List>
        </Stack>
      ))}
    </Stack>
  )
}
