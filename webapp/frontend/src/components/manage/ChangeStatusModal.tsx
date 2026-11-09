import { Alert, Button, Group, Modal, Select, Stack, Textarea } from '@mantine/core'
import { useRef, useState } from 'react'
import { apiPath } from '../../api/client'
import { useAction } from '../../api/queries'
import type { Meta, Reg, Risk } from '../../api/types'
import { failure, STALE_TEXT } from './errors'

interface Props {
  reg: Reg
  slug: string
  risk: Risk
  meta: Meta
  opened: boolean
  onClose: () => void
}

export function ChangeStatusModal({ reg, slug, risk, meta, opened, onClose }: Props) {
  const action = useAction(reg, slug)
  const [status, setStatus] = useState<string | null>(risk.status)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef(false)

  const save = async () => {
    if (inFlight.current || !status) return
    inFlight.current = true
    setBusy(true)
    setError(null)
    try {
      await action.mutateAsync({
        path: apiPath(reg, slug, 'risks', risk.id, 'edit'),
        body: { fields: { status }, seen: risk, reason },
      })
      onClose()
    } catch (e) {
      const f = failure(e)
      setError(f.kind === 'stale' ? STALE_TEXT : f.message)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <Modal opened={opened} onClose={busy ? () => {} : onClose} title="Change status" centered>
      <Stack gap="sm">
        <Select
          label="Status"
          data={meta.statuses}
          value={status}
          onChange={setStatus}
          allowDeselect={false}
          disabled={busy}
          comboboxProps={{ withinPortal: false }}
        />
        <Textarea
          label="Reason (optional)"
          value={reason}
          onChange={(e) => setReason(e.currentTarget.value)}
          disabled={busy}
          autosize
          minRows={2}
        />
        {error !== null && (
          <Alert color="red" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {error}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={save} disabled={busy || !status}>
            Save status
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
