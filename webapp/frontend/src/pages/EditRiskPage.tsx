import { Alert, Button, Card, Group, Loader, Stack, Textarea, Title } from '@mantine/core'
import { useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { apiPath } from '../api/client'
import { useAction, useMeta, useRisk } from '../api/queries'
import { visible } from '../lib/visible'
import type { Meta, Reg, Risk, RiskWriteResponse } from '../api/types'
import { failure, STALE_TEXT } from '../components/manage/errors'
import {
  changedFields,
  FieldInput,
  groupedFields,
  isList,
  sameValue,
  toForm,
  type FormValue,
  type FormValues,
} from '../components/manage/fieldInputs'

interface Props {
  mode: 'add' | 'edit'
}

export function EditRiskPage({ mode }: Props) {
  const { reg, slug, id } = useParams()
  const meta = useMeta()
  const fetched = useRisk(reg as Reg, slug ?? '', mode === 'edit' ? (id ?? '') : '')

  if (!meta.data) return meta.error ? <Alert color="red">{visible(meta.error.message)}</Alert> : <Loader m="xl" aria-label="Loading" />
  if (mode === 'add') {
    return <Form key="add" mode="add" reg={reg as Reg} slug={slug as string} meta={meta.data} seen={null} />
  }
  if (fetched.error) return <Alert color="red">{visible(fetched.error.message)}</Alert>
  if (!fetched.data) return <Loader m="xl" aria-label="Loading" />
  return <Form key={id} mode="edit" reg={reg as Reg} slug={slug as string} meta={meta.data} seen={fetched.data.risk} />
}

interface FormProps {
  mode: 'add' | 'edit'
  reg: Reg
  slug: string
  meta: Meta
  seen: Risk | null
}

function initialValues(meta: Meta, risk: Risk | null): FormValues {
  return Object.fromEntries(meta.editable.map((f) => [f, toForm(f, risk?.[f])]))
}

function Form({ mode, reg, slug, meta, seen: initialSeen }: FormProps) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const action = useAction(reg, slug)
  // `seen` is the record the owner is editing from. It changes only when a 409 hands us a newer one.
  const [seen, setSeen] = useState<Risk | null>(initialSeen)
  const [values, setValues] = useState<FormValues>(() => initialValues(meta, initialSeen))
  const [reason, setReason] = useState('')
  const [stale, setStale] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inFlight = useRef(false)

  const base = `/${reg}/${encodeURIComponent(slug)}`
  // Cancel stays in the app: back to the risk, to its review when that is where the owner came from,
  // or to the register for a new risk.
  const cancelTo =
    mode === 'add'
      ? `${base}/register`
      : params.get('return') === 'review'
        ? `${base}/review?id=${encodeURIComponent(seen!.id)}`
        : `${base}/risks/${encodeURIComponent(seen!.id)}`
  const retired = seen !== null && seen.review_state === 'approved' && seen.status === 'retired'
  const rejected = seen !== null && seen.review_state === 'rejected'
  if (retired || rejected) {
    return <Alert color="yellow">{`${seen!.id} is ${retired ? 'retired' : 'rejected'} and can't be edited.`}</Alert>
  }

  const required = new Set(mode === 'add' ? meta.human_required : [])
  const edits = seen ? changedFields(meta.editable, values, seen) : {}
  const nothingToSave = mode === 'edit' && Object.keys(edits).length === 0

  const set = (field: string, value: FormValue) => setValues((v) => ({ ...v, [field]: value }))

  const save = async () => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError(null)
    setStale(false)
    try {
      let result: RiskWriteResponse
      if (mode === 'add') {
        const fields: FormValues = {}
        for (const f of meta.editable) {
          const v = values[f]
          if (isList(f) ? (v as string[]).length > 0 : (v as string).trim() !== '') fields[f] = v
        }
        result = (await action.mutateAsync({ path: apiPath(reg, slug, 'risks'), body: { fields } })) as RiskWriteResponse
        navigate(`${base}/review?id=${encodeURIComponent(result.risk.id)}`)
      } else {
        result = (await action.mutateAsync({
          path: apiPath(reg, slug, 'risks', seen!.id, 'edit'),
          body: { fields: edits, seen, reason },
        })) as RiskWriteResponse
        const saved = result.risk
        navigate(
          saved.review_state === 'approved'
            ? `${base}/risks/${encodeURIComponent(saved.id)}`
            : `${base}/review?id=${encodeURIComponent(saved.id)}`,
        )
      }
    } catch (e) {
      const f = failure(e)
      if (f.kind === 'stale') {
        setStale(true)
        const current = f.current
        if (current && seen) {
          // Fields the owner has not touched follow the current record; typed ones stay.
          setValues((v) =>
            Object.fromEntries(
              meta.editable.map((k) => [k, sameValue(v[k], toForm(k, seen[k])) ? toForm(k, current[k]) : v[k]]),
            ),
          )
          setSeen(current)
        }
      } else {
        setError(f.message)
      }
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
      style={{ maxWidth: 820 }}
    >
      <Title order={1} size="h3" mb="md">
        {mode === 'add' ? 'New risk' : `Edit ${seen!.id}`}
      </Title>
      <Stack gap="md">
        {mode === 'edit' && seen!.review_state === 'approved' && (
          <Alert color="blue">Your edit keeps the approval.</Alert>
        )}
        {stale && <Alert color="yellow">{STALE_TEXT}</Alert>}
        {groupedFields(meta.editable).map((g) => (
          <Card key={g.title} withBorder padding="md">
            <Title order={2} size="h5" mb="sm">
              {g.title}
            </Title>
            <Stack gap="sm">
              {g.fields.map((f) => (
                <FieldInput
                  key={f}
                  field={f}
                  meta={meta}
                  value={values[f]}
                  required={required.has(f)}
                  disabled={busy}
                  onChange={(v) => set(f, v)}
                />
              ))}
            </Stack>
          </Card>
        ))}
        {mode === 'edit' && (
          <Textarea
            label="Reason for change (optional)"
            value={reason}
            onChange={(e) => setReason(e.currentTarget.value)}
            disabled={busy}
            autosize
            minRows={2}
          />
        )}
        {error !== null && (
          <Alert color="red" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {error}
          </Alert>
        )}
        <Group>
          <Button type="submit" disabled={busy || nothingToSave}>
            Save
          </Button>
          <Button variant="default" disabled={busy} onClick={() => navigate(cancelTo)}>
            Cancel
          </Button>
        </Group>
      </Stack>
    </form>
  )
}
