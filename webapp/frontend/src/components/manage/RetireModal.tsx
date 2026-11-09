import { Alert, Button, Group, Modal, Stack, Text, Textarea } from '@mantine/core'
import { useRef, useState } from 'react'
import { apiPath } from '../../api/client'
import { useAction } from '../../api/queries'
import type { Reg, Risk } from '../../api/types'
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
  const [reason, setReason] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef(false)

  // The note rule is the core's: outer whitespace does not count.
  const length = reason.trim().length
  const ok = length >= noteMin

  const retire = async () => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError(null)
    try {
      await action.mutateAsync({
        path: apiPath(reg, slug, 'risks', risk.id, 'retire'),
        body: { reason, seen: risk },
      })
      onClose()
    } catch (e) {
      const f = failure(e)
      setError(f.kind === 'stale' ? STALE_TEXT : f.message)
      setConfirming(false)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <Modal opened={opened} onClose={busy ? () => {} : onClose} title={`Retire ${risk.id}`} centered>
      <Stack gap="sm">
        {error !== null && (
          <Alert color="red" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {error}
          </Alert>
        )}
        {confirming ? (
          <>
            <Text style={{ overflowWrap: 'anywhere' }}>
              {`Retire ${risk.id}? It stays in the register under Retired and can't be edited.`}
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
                Retire {risk.id}
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Modal>
  )
}
