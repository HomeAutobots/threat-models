import { Alert, Button, Code, Group, List, Stack, Text, Textarea, Title } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError, apiPath } from '../../api/client'
import { useAction, useC4, useMeta } from '../../api/queries'
import type { C4Response, Reg, StructurizrVerdict } from '../../api/types'
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
  // Set by a 409: the query's dataUpdateCount then. Approval stays off until a later fetch has
  // replaced what is shown.
  const [reload, setReload] = useState<{ base: number; failed: boolean } | null>(null)
  const count = client.getQueryState(key)?.dataUpdateCount ?? 0
  const reloaded = reload !== null && count > reload.base && !c4.isFetching
  const waiting = reload !== null && !reloaded

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
  const canApprove =
    !!preview && blockers.length === 0 && data.status.state !== 'current' && len >= noteMin && !busy && !waiting && !c4.isFetching

  const approve = async () => {
    if (!preview || busy) return
    setBusy(true)
    setError(null)
    try {
      await action.mutateAsync({
        path: apiPath(reg, slug, 'c4', 'approve'),
        body: { note, expected_sha256: preview.sha256 },
      })
      setNote('')
      setReload(null)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setReload({ base: client.getQueryState(key)?.dataUpdateCount ?? 0, failed: false })
        try {
          await c4.refetch({ throwOnError: true })
        } catch {
          setReload((r) => (r ? { ...r, failed: true } : r))
        }
      } else {
        setError(refusalText(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)))
      }
    } finally {
      setBusy(false)
    }
  }

  const changed = preview ? Object.entries(preview.changed) : []
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
                  <List.Item key={id}>{visible(`${id}: ${fields.join(', ')}`)}</List.Item>
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
      <Textarea
        label="Approval note"
        description={`${len} of at least ${noteMin} characters.`}
        value={note}
        onChange={(e) => setNote(e.currentTarget.value)}
        autosize
        minRows={2}
      />
      {reload && (
        <Alert color="yellow">
          {MODEL_STALE_TEXT}
          {reload.failed && ' Could not reload it; try again.'}
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
