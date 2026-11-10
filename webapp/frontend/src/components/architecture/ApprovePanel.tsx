import { Alert, Button, Code, Group, List, Stack, Text, Textarea, Title } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, apiPath } from '../../api/client'
import { useAction, useC4, useMeta } from '../../api/queries'
import type { C4Record, C4Response, Reg, StructurizrVerdict } from '../../api/types'
import { noteLength } from '../../lib/pyStrip'
import { visible } from '../../lib/visible'
import { refusalText } from '../manage/errors'

export const MODEL_STALE_TEXT = 'workspace.dsl changed since it was shown. Review the current file.'

export function verdictText(v: StructurizrVerdict): string {
  if (v.state === 'accepted') return 'Structurizr accepted this file.'
  if (v.state === 'refused') return 'Structurizr refused this file: ' + visible(v.message ?? '')
  return 'Not checked yet: open the diagrams to check.'
}

const MONO = { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0, fontFamily: 'monospace', fontSize: 13 } as const

interface Props {
  reg: Reg
  slug: string
  data: C4Response
}

function entry(record: C4Record | null | undefined, id: string): Record<string, unknown> | null {
  const e = record?.items[id] ?? record?.rels[id] ?? record?.views[id]
  return (e as unknown as Record<string, unknown>) ?? null
}

function show(v: unknown): string {
  if (v === null || v === undefined || v === '') return '(none)'
  return typeof v === 'string' ? v : JSON.stringify(v)
}

/** Old -> new for each field core's `changed` names. Display only: core decides what changed. */
function changeLines(id: string, fields: string[], oldRecord: C4Record | null, newRecord: C4Record): string[] {
  const a = entry(oldRecord, id)
  const b = entry(newRecord, id)
  return fields.map((f) => `${f}: ${show(a?.[f])} → ${show(b?.[f])}`)
}

export function ApprovePanel({ reg, slug, data }: Props) {
  const preview = data.preview
  const c4 = useC4(reg, slug)
  const meta = useMeta()
  const action = useAction(reg, slug)
  const client = useQueryClient()
  const key = [reg, slug, 'c4']
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The sha256 of the file the owner was shown. A later fetch that differs (an export refetch, a
  // 409 reload) does not move it; the owner re-pins by choosing to review the current file.
  const [pinned, setPinned] = useState<string | null>(preview?.sha256 ?? null)
  if (pinned === null && preview) setPinned(preview!.sha256)
  const moved = !!preview && pinned !== null && pinned !== preview.sha256
  // Set by a 409: the query's dataUpdateCount then. Approval stays off until a later fetch has
  // replaced what is shown.
  const [reload, setReload] = useState<{ base: number } | null>(null)
  const count = client.getQueryState(key)?.dataUpdateCount ?? 0
  const waiting = reload !== null && (count <= reload.base || c4.isFetching)

  const noteMin = meta.data?.note_min ?? 20
  const len = noteLength(note)

  const blockers: string[] = []
  if (preview) {
    blockers.push(...preview.problems)
    if (preview.reused.length > 0) blockers.push(`These IDs were used before and cannot be reused: ${preview.reused.join(', ')}`)
    for (const g of preview.adoption?.gaps ?? []) {
      blockers.push(`Adoption gap: ${g.id} is cited by ${g.cited_by.join(', ')} and claimed by nothing`)
    }
    for (const r of preview.adoption?.pending_rereviews ?? []) {
      blockers.push(`${r} awaits re-review; approve or reject it first`)
    }
  }
  const approved = data.status.state === 'current'
  const canApprove =
    !!preview && !moved && blockers.length === 0 && !approved && len >= noteMin && !busy && !waiting && !c4.isFetching

  const refetch = async () => {
    try {
      await c4.refetch({ throwOnError: true })
      return true
    } catch {
      return false
    }
  }

  const approve = async () => {
    if (!preview || busy || pinned === null) return
    setBusy(true)
    setError(null)
    try {
      await action.mutateAsync({
        path: apiPath(reg, slug, 'c4', 'approve'),
        body: { note, expected_sha256: pinned },
      })
      setNote('')
      setReload(null)
      setPinned(null)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setReload({ base: client.getQueryState(key)?.dataUpdateCount ?? 0 })
        await refetch()
      } else {
        setError(refusalText(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)))
        await refetch() // show the file as it is now
      }
    } finally {
      setBusy(false)
    }
  }

  const rewrites = Object.entries(preview?.adoption?.rewrites ?? {}) as [string, { from?: string[]; to?: string[] }][]
  const changed = preview ? Object.entries(preview.changed) : []
  const failedReload = reload !== null && waiting && !c4.isFetching
  return (
    <Stack gap="xs">
      <Title order={2} size="h4">
        Approve
      </Title>
      <Text size="sm" data-testid="verdict" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: data.structurizr.state === 'refused' ? 'monospace' : undefined }}>
        {verdictText(data.structurizr)}
      </Text>
      {preview && (
        <>
          <Text size="sm">{`File version ${visible(preview.version ?? '')}, sha256 ${visible(preview.sha256)}`}</Text>
          {preview.added.length > 0 && (
            <>
              <Text size="sm" fw={600}>Added</Text>
              <Text size="sm">{preview.added.map(visible).join(', ')}</Text>
            </>
          )}
          {preview.removed.length > 0 && (
            <>
              <Text size="sm" fw={600}>Removed</Text>
              <Text size="sm">{preview.removed.map(visible).join(', ')}</Text>
            </>
          )}
          {changed.length > 0 && (
            <>
              <Text size="sm" fw={600}>Changed</Text>
              <List size="sm">
                {changed.map(([id, fields]) => (
                  <List.Item key={id}>
                    <Text span size="sm" fw={600}>{visible(id)}</Text>
                    {changeLines(id, fields, data.latest_record, preview.record).map((l) => (
                      <Text key={l} size="sm" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                        {visible(l)}
                      </Text>
                    ))}
                  </List.Item>
                ))}
              </List>
            </>
          )}
          {rewrites.length > 0 && (
            <>
              <Text size="sm" fw={600}>Edits this approval makes to risks</Text>
              <List size="sm" listStyleType="none">
                {rewrites.map(([rid, r]) => (
                  <List.Item key={rid}>{visible(`${rid}: ${(r.from ?? []).join(', ')} → ${(r.to ?? []).join(', ')}`)}</List.Item>
                ))}
              </List>
            </>
          )}
          {preview.warnings.length > 0 && (
            <Alert color="yellow" title="Warnings">
              <List>
                {preview.warnings.map((w, i) => (
                  <List.Item key={i}>{visible(w)}</List.Item>
                ))}
              </List>
            </Alert>
          )}
          {preview.diff.length > 0 && (
            <Code block aria-label="Changes to workspace.dsl" style={MONO}>
              {visible(preview.diff.join('\n'))}
            </Code>
          )}
          {blockers.length > 0 && (
            <Alert color="red" title="Approval is blocked">
              <List>
                {blockers.map((b, i) => (
                  <List.Item key={i} style={{ overflowWrap: 'anywhere' }}>{visible(b)}</List.Item>
                ))}
              </List>
            </Alert>
          )}
        </>
      )}
      {data.text && (
        <details>
          <summary>The exact file</summary>
          <pre style={MONO}>{visible(data.text)}</pre>
        </details>
      )}
      {approved && data.status.latest && <Text size="sm">{`This file is already approved as ${visible(data.status.latest.id)}.`}</Text>}
      <Textarea
        label="Approval note"
        description={`${len} of at least ${noteMin} characters.`}
        value={note}
        onChange={(e) => setNote(e.currentTarget.value)}
        autosize
        minRows={2}
      />
      {(moved || waiting) && (
        <Alert color="yellow">
          <Text size="sm">
            {MODEL_STALE_TEXT}
            {failedReload && ' Could not reload it; try again.'}
          </Text>
          <Group mt="xs">
            {failedReload && (
              <Button size="compact-sm" variant="default" onClick={refetch}>
                Reload
              </Button>
            )}
            {moved && !waiting && (
              <Button
                size="compact-sm"
                onClick={() => {
                  setPinned(preview!.sha256)
                  setReload(null)
                }}
              >
                Review the current file
              </Button>
            )}
          </Group>
        </Alert>
      )}
      {error && <Alert color="red" style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{error}</Alert>}
      <Group>
        <Button onClick={approve} disabled={!canApprove} loading={busy}>
          Approve model
        </Button>
      </Group>
    </Stack>
  )
}
