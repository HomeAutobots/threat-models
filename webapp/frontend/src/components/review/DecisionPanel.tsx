import { Alert, Badge, Button, Card, Group, Stack, Text, Textarea, Title } from '@mantine/core'

export interface DecisionPanelProps {
  riskId: string
  isReReview: boolean
  duplicateId: string | null
  noteMin: number
  /** The trial register: practice data. */
  trial?: boolean
  busy: boolean
  /** The risk is being reloaded after a 409; nothing can be decided yet. */
  reloading?: boolean
  error: string | null
  note: string
  onNote: (v: string) => void
  onApprove: () => void
  onReject: () => void
  onMerge: () => void
  onEdit: () => void
}

const PANEL_COPY =
  'You approve exactly the version on this page. If it changes while you read, nothing is saved and the new version is shown.'

/** The note rule is the core's: outer whitespace does not count, and length is in code points. */
export function DecisionPanel(p: DecisionPanelProps) {
  const length = [...p.note.trim()].length
  const noteOk = length >= p.noteMin
  const locked = p.busy || !noteOk

  return (
    <Card withBorder radius="md" padding="md" aria-label="Your decision" component="section">
      <Title order={2} size="sm" tt="uppercase" c="dimmed" mb="xs" style={{ letterSpacing: '0.06em' }}>
        Your decision
      </Title>
      {p.trial && (
        <Badge color="orange" variant="filled" mb="xs">
          Trial register
        </Badge>
      )}
      <Textarea
        label="Review note"
        placeholder="Why you're approving or rejecting this version"
        value={p.note}
        onChange={(e) => p.onNote(e.currentTarget.value)}
        disabled={p.busy}
        minRows={5}
        styles={{ input: { overflowWrap: 'anywhere', resize: 'vertical' } }}
      />
      <Group justify="space-between" mt={4} mb="sm">
        <Text size="xs" c="dimmed">
          At least {p.noteMin} characters
        </Text>
        <Text size="xs" c={noteOk ? 'green' : 'dimmed'}>
          {length} / {p.noteMin}
        </Text>
      </Group>
      {p.reloading && (
        <Text size="sm" c="dimmed" mb="sm">
          Reloading this risk…
        </Text>
      )}
      {p.error !== null && (
        <Alert color="red" mb="sm" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
          {p.error}
        </Alert>
      )}
      <Stack gap="xs">
        <Button disabled={locked} onClick={p.onApprove} style={{ overflowWrap: 'anywhere' }}>
          Approve {p.riskId}
        </Button>
        <Button color="red" variant="light" disabled={locked} onClick={p.onReject}>
          {p.isReReview ? 'Reject and restore last approved' : `Reject ${p.riskId}`}
        </Button>
        {p.duplicateId && !p.isReReview && (
          <Button variant="default" disabled={locked} onClick={p.onMerge}>
            Merge into {p.duplicateId}
          </Button>
        )}
        <Button variant="default" disabled={p.busy} onClick={p.onEdit}>
          Edit before deciding
        </Button>
      </Stack>
      <Text size="xs" c="dimmed" mt="sm">
        {PANEL_COPY}
      </Text>
    </Card>
  )
}
