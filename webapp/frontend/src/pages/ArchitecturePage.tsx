import { Alert, Loader, SegmentedControl, Stack, Text, Title } from '@mantine/core'
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

export const REVIEW_LABEL = 'The file under review (not approved)'

export function ArchitecturePage() {
  const { reg, slug } = useParams()
  const c4 = useC4(reg as Reg, slug as string)
  const risks = useRisks(reg as Reg, slug as string)
  const [selected, setSelected] = useState<string | null>(null)
  const [which, setWhich] = useState<'file' | 'approved'>('file')

  if (c4.isLoading) return <Loader m="xl" aria-label="Loading" />
  // A failed refetch keeps the data on screen; only a page that never loaded shows the error.
  if (!c4.data) return <Alert color="red">{visible(c4.error?.message ?? 'Could not load the model.')}</Alert>

  const data = c4.data
  const approved = data.latest_record
  const approvedLabel = data.status.latest ? `Approved ${data.status.latest.id}` : 'Approved model'
  const review = data.status.state === 'current' ? null : (data.preview?.record ?? null)
  // Nothing approved and no file at all: the API's error says so, and the page says it better.
  const noFile = data.status.state === 'none' && data.status.current_sha256 === null
  const shown = review && approved && which === 'approved' ? approved : (review ?? approved)
  const shownIsReview = shown !== null && shown === review
  // Counts always come from the latest approval. IDs are never reused, so they also hold for the
  // IDs the file under review shares with it.
  const countsLabel = data.status.latest ? `Open risks (${visible(data.status.latest.id)})` : 'Open risks (none approved)'

  return (
    <Stack>
      <Title order={1} size="h3">
        Architecture
      </Title>
      {noFile ? (
        <Text>{NO_MODEL(slug as string)}</Text>
      ) : (
        <>
          {data.error && (
            <Alert color="red" title="The file cannot be read" style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>
              {visible(data.error)}
            </Alert>
          )}
          <ModelStatus state={data.status.state} latest={data.status.latest} approvals={data.approvals} />
          <DiagramLinks
            reg={reg as Reg}
            slug={slug as string}
            sha256={data.status.current_sha256}
            version={data.preview?.version ?? data.status.latest?.version ?? null}
            verdict={data.structurizr}
          />
          {shown && (
            <>
              {review && approved ? (
                <SegmentedControl
                  aria-label="Model shown"
                  value={which}
                  onChange={(v) => setWhich(v as 'file' | 'approved')}
                  data={[
                    { value: 'file', label: 'The file under review' },
                    { value: 'approved', label: approvedLabel },
                  ]}
                />
              ) : null}
              <Title order={2} size="h4">
                {shownIsReview ? REVIEW_LABEL : approvedLabel}
              </Title>
              <ItemTables
                record={shown}
                counts={data.counts}
                countsLabel={countsLabel}
                selected={selected}
                onSelect={setSelected}
              />
              {selected && (
                <ItemDetail reg={reg as Reg} slug={slug as string} id={selected} record={shown} risks={risks.data ?? []} />
              )}
            </>
          )}
          {approved && (
            <>
              <Title order={2} size="h4">
                {`Routes (${approvedLabel.replace(/^Approved/, 'approved')})`}
              </Title>
              <RoutesPanel reg={reg as Reg} slug={slug as string} record={approved} />
            </>
          )}
          <ApprovePanel reg={reg as Reg} slug={slug as string} data={data} />
        </>
      )}
    </Stack>
  )
}
