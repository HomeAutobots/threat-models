import { Alert, Button, Group, Modal, Stack, Text, Textarea } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { apiPath } from '../../api/client'
import { useAction } from '../../api/queries'
import type { Reg, Risk } from '../../api/types'
import { noteLength } from '../../lib/pyStrip'
import { visible } from '../../lib/visible'
import { failure, STALE_TEXT } from './errors'

interface Props {
  reg: Reg
  slug: string
  risk: Risk
  noteMin: number
  opened: boolean
  onClose: () => void
}

export function RetireModal({ reg, slug, risk, noteMin, opened, onClose }: Props) {
  const action = useAction(reg, slug)
  const client = useQueryClient()
  // `seen` is the record this dialog acts on; a 409 replaces it with the current one.
  const [seen, setSeen] = useState<Risk>(risk)
  const [stale, setStale] = useState(false)
  // A 409 without the current record: the page refetches it, and the next one to arrive replaces `seen`.
  const [adoptFrom, setAdoptFrom] = useState<Risk | null>(null)
  const [reason, setReason] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef(false)

  // The note rule is the core's: outer whitespace (Python's set) does not count, and length is in code points.
  const id = visible(risk.id)
  const length = noteLength(reason)
  const ok = length >= noteMin

  // Adjusted while rendering, not in an effect: the refetched record has arrived.
  if (adoptFrom !== null && risk !== adoptFrom) {
    setSeen(risk)
    setAdoptFrom(null)
  }

  const retire = async () => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError(null)
    setStale(false)
    setAdoptFrom(null)
    try {
      await action.mutateAsync({
        path: apiPath(reg, slug, 'risks', risk.id, 'retire'),
        body: { reason, seen },
      })
      onClose()
    } catch (e) {
      const f = failure(e)
      if (f.kind === 'stale') {
        setStale(true)
        if (f.current) setSeen(f.current)
        else setAdoptFrom(risk)
        void client.invalidateQueries({ queryKey: [reg, slug] })
      } else {
        setError(f.message)
      }
      setConfirming(false)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <Modal opened={opened} onClose={busy ? () => {} : onClose} title={`Retire ${id}`} centered>
      <Stack gap="sm">
        {stale && (
          <Alert color="yellow">
            {STALE_TEXT} Current status: {seen.status ?? 'none'}.
          </Alert>
        )}
        {error !== null && (
          <Alert color="red" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {error}
          </Alert>
        )}
        {confirming ? (
          <>
            <Text style={{ overflowWrap: 'anywhere' }}>
              {`Retire ${id}? It stays in the register under Retired and can't be edited.`}
            </Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setConfirming(false)} disabled={busy}>
                Cancel
              </Button>
              <Button color="red" onClick={retire} disabled={busy}>
                Retire
              </Button>
            </Group>
          </>
        ) : (
          <>
            <Textarea
              label="Reason"
              placeholder="Why this risk is no longer tracked"
              value={reason}
              onChange={(e) => setReason(e.currentTarget.value)}
              autosize
              minRows={4}
            />
            <Group justify="space-between">
              <Text size="xs" c="dimmed">
                At least {noteMin} characters
              </Text>
              <Text size="xs" c={ok ? 'green' : 'dimmed'}>
                {length} / {noteMin}
              </Text>
            </Group>
            <Group justify="flex-end">
              <Button variant="default" onClick={onClose}>
                Cancel
              </Button>
              <Button color="red" disabled={!ok} onClick={() => setConfirming(true)} style={{ overflowWrap: 'anywhere' }}>
                Retire {id}
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Modal>
  )
}
