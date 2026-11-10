import { Alert, Loader, Stack, Text, Title } from '@mantine/core'
import { useState } from 'react'
import { useParams } from 'react-router'
import { useC4, useRisks } from '../api/queries'
import type { Reg } from '../api/types'
import { ApprovePanel } from '../components/architecture/ApprovePanel'
import { DiagramLinks } from '../components/architecture/DiagramLinks'
import { ItemDetail } from '../components/architecture/ItemDetail'
import { ItemTables } from '../components/architecture/ItemTables'
import { ModelStatus } from '../components/architecture/ModelStatus'
import { RoutesPanel } from '../components/architecture/RoutesPanel'
import { visible } from '../lib/visible'

export const NO_MODEL = (slug: string) =>
  `There's no C4 model for this system yet. The modeling agent drafts one in systems/${slug}/workspace.dsl.`

export function ArchitecturePage() {
  const { reg, slug } = useParams()
  const c4 = useC4(reg as Reg, slug as string)
  const risks = useRisks(reg as Reg, slug as string)
  const [selected, setSelected] = useState<string | null>(null)

  if (c4.isLoading) return <Loader m="xl" aria-label="Loading" />
  if (c4.error || !c4.data) return <Alert color="red">{visible(c4.error?.message ?? 'Could not load the model.')}</Alert>

  const data = c4.data
  const record = data.latest_record
  const none = data.preview === null && data.status.state === 'none'

  return (
    <Stack>
      <Title order={1} size="h3">
        Architecture
      </Title>
      {data.error && (
        <Alert color="red" title="The file cannot be read" style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>
          {visible(data.error)}
        </Alert>
      )}
      {none ? (
        !data.error && <Text>{NO_MODEL(slug as string)}</Text>
      ) : (
        <>
          <ModelStatus state={data.status.state} latest={data.status.latest} approvals={data.approvals} />
          <DiagramLinks reg={reg as Reg} slug={slug as string} />
          {record && (
            <>
              <Title order={2} size="h4">
                The approved model
              </Title>
              <ItemTables record={record} counts={data.counts} selected={selected} onSelect={setSelected} />
              {selected && (
                <ItemDetail
                  reg={reg as Reg}
                  slug={slug as string}
                  id={selected}
                  record={record}
                  risks={risks.data ?? []}
                />
              )}
              <Title order={2} size="h4">
                Routes
              </Title>
              <RoutesPanel reg={reg as Reg} slug={slug as string} record={record} />
            </>
          )}
          <ApprovePanel reg={reg as Reg} slug={slug as string} data={data} />
        </>
      )}
    </Stack>
  )
}
