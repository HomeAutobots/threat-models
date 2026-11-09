import { Alert, Badge, Button, Group, List, Loader, Stack, Table, Tabs, Text, Textarea, Title } from '@mantine/core'
import { useState } from 'react'
import Markdown from 'react-markdown'
import { useParams } from 'react-router'
import remarkGfm from 'remark-gfm'
import { ApiError, apiPath } from '../api/client'
import { useAction, useDfd, useMeta } from '../api/queries'
import type { Reg } from '../api/types'
import { MermaidDiagram } from '../components/dfd/MermaidDiagram'
import { formatActor, formatTime } from '../lib/format'
import { visible } from '../lib/visible'

const STALE = 'dfd.md changed since it was shown. Review the current file.'
const HIDDEN = /<!--|<\/?[A-Za-z][^>]*>/

export function DfdPage() {
  const { reg, slug } = useParams()
  const dfd = useDfd(reg as Reg, slug as string)
  const meta = useMeta()
  const action = useAction(reg as Reg, slug as string)
  const [tab, setTab] = useState<string>('readable')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [stale, setStale] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (dfd.isLoading) return <Loader m="xl" aria-label="Loading" />
  if (dfd.error || !dfd.data) return <Alert color="red">{visible(dfd.error?.message ?? 'Could not load the DFD.')}</Alert>

  const data = dfd.data
  const noteMin = meta.data?.note_min ?? 20
  const hidden = data.text !== null && HIDDEN.test(data.text)
  const canApprove =
    data.status.state !== 'current' &&
    !data.preview_error &&
    !!data.preview &&
    note.trim().length >= noteMin &&
    !busy &&
    !refreshing &&
    !dfd.isFetching

  const approve = async () => {
    if (!data.preview || busy) return
    setBusy(true)
    setError(null)
    setStale(false)
    try {
      await action.mutateAsync({
        path: apiPath(reg as Reg, slug as string, 'dfd', 'approve'),
        body: { note, expected_sha256: data.preview.sha256 },
      })
      setNote('')
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setStale(true)
        setRefreshing(true)
        try {
          await dfd.refetch()
        } finally {
          setRefreshing(false)
        }
      } else {
        setError(visible(e instanceof Error ? e.message : String(e)))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack>
      <Group>
        <Title order={1} size="h3">
          DFD
        </Title>
        <Badge color={data.status.state === 'current' ? 'green' : data.status.state === 'changed' ? 'yellow' : 'gray'}>
          {data.status.state}
        </Badge>
      </Group>

      <Title order={2} size="h4">
        Approvals
      </Title>
      {data.approvals.length === 0 ? (
        <Text size="sm">No approvals yet.</Text>
      ) : (
        <Table.ScrollContainer minWidth={500}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>ID</Table.Th>
                <Table.Th>Version</Table.Th>
                <Table.Th>Approved by</Table.Th>
                <Table.Th>When</Table.Th>
                <Table.Th>Note</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.approvals.map((a) => (
                <Table.Tr key={a.id}>
                  <Table.Td>{visible(a.id)}</Table.Td>
                  <Table.Td>{visible(a.version ?? '')}</Table.Td>
                  <Table.Td>{visible(formatActor(a.approved_by))}</Table.Td>
                  <Table.Td>{formatTime(a.approved_at)}</Table.Td>
                  <Table.Td style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{visible(a.note ?? '')}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {data.preview_error && <Alert color="red" title="The file cannot be approved">{visible(data.preview_error)}</Alert>}
      {data.preview && (
        <Stack gap="xs">
          <Title order={2} size="h4">
            Preview of the current file
          </Title>
          <Text size="sm">Added IDs: {data.preview.added.length === 0 && 'none'}</Text>
          <List size="sm">
            {data.preview.added.map((id) => (
              <List.Item key={id}>{visible(id)}</List.Item>
            ))}
          </List>
          <Text size="sm">Removed IDs: {data.preview.removed.length === 0 && 'none'}</Text>
          <List size="sm">
            {data.preview.removed.map((id) => (
              <List.Item key={id}>{visible(id)}</List.Item>
            ))}
          </List>
          {data.preview.warnings.length > 0 && (
            <Alert color="yellow" title="Warnings">
              <List>
                {data.preview.warnings.map((w, i) => (
                  <List.Item key={i}>{visible(w)}</List.Item>
                ))}
              </List>
            </Alert>
          )}
        </Stack>
      )}

      {data.text === null ? (
        <Text>There is no dfd.md yet.</Text>
      ) : (
        <Tabs value={tab} onChange={(v) => setTab(v ?? 'readable')}>
          <Tabs.List>
            <Tabs.Tab value="readable">Readable</Tabs.Tab>
            <Tabs.Tab value="exact">Exact file</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="readable" pt="md">
            {/* No rehype-raw: raw HTML in the file is not rendered as HTML. */}
            <div style={{ overflowWrap: 'anywhere' }}>
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // Never render an <img>: a remote image in AI-writable content is a beacon.
                  img({ alt }) {
                    return (
                      <Text span c="dimmed" fs="italic">
                        Image not loaded: {visible(alt ?? '')}
                      </Text>
                    )
                  },
                  code({ className, children, ...rest }) {
                    if (/language-mermaid/.test(className ?? '')) {
                      return <MermaidDiagram source={String(children).replace(/\n$/, '')} />
                    }
                    return (
                      <code className={className} {...rest}>
                        {children}
                      </code>
                    )
                  },
                }}
              >
                {data.text}
              </Markdown>
            </div>
          </Tabs.Panel>
          <Tabs.Panel value="exact" pt="md">
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0 }}>{visible(data.text)}</pre>
          </Tabs.Panel>
        </Tabs>
      )}

      {hidden && (
        <Alert color="yellow">
          <Text span>
            This file contains content the readable view doesn't show (HTML comments or raw HTML). Check the Exact file view
            before approving.{' '}
          </Text>
          <Button variant="subtle" size="compact-sm" onClick={() => setTab('exact')}>
            Exact file view
          </Button>
        </Alert>
      )}

      <Textarea
        label="Approval note"
        description={`At least ${noteMin} characters.`}
        value={note}
        onChange={(e) => setNote(e.currentTarget.value)}
        autosize
        minRows={2}
      />
      {stale && <Alert color="yellow">{STALE}</Alert>}
      {error && <Alert color="red" style={{ overflowWrap: 'anywhere' }}>{error}</Alert>}
      <Group>
        <Button onClick={approve} disabled={!canApprove} loading={busy}>
          Approve DFD
        </Button>
      </Group>
    </Stack>
  )
}
