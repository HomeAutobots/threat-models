import { Alert, Anchor, Button, Group, Loader, Text } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { useAction, useMeta, useRisk, useRiskHistory, useRisks } from '../api/queries'
import { ApiError, apiPath } from '../api/client'
import type { Conflict409, Reg, Risk, RiskDetail } from '../api/types'
import { ReReviewDiff } from '../components/review/ReReviewDiff'
import { DecisionPanel } from '../components/review/DecisionPanel'
import classes from '../components/layout/RecordLayout.module.css'
import { RiskRecord, visibleSections } from '../components/record/RiskRecord'
import { SectionOutline } from '../components/record/SectionOutline'
import { refusalText, STALE_TEXT } from '../components/manage/errors'
import { visible } from '../lib/visible'

type Decision = 'approve' | 'reject' | 'merge'

export function ReviewPage() {
  const { reg, slug } = useParams()
  const [params, setParams] = useSearchParams()
  const risks = useRisks(reg as Reg, slug ?? '')

  // Pin the shown item into the URL, so a background refetch of the list cannot switch it.
  const queue = (risks.data ?? []).filter((r) => r.review_state === 'pending')
  const firstPending = queue[0]?.id
  const wanted = params.get('id')
  // No id, or an id that is not pending (decided elsewhere, or mistyped): pin what is shown.
  const unpinned = (!wanted || !queue.some((r) => r.id === wanted)) && !!firstPending
  useEffect(() => {
    if (unpinned && firstPending) setParams({ id: firstPending }, { replace: true })
  }, [unpinned, firstPending, setParams])

  if (risks.isLoading) return <Loader m="xl" aria-label="Loading" />
  // A failed list refetch replaces the page only when there is nothing to show.
  if (risks.error && !risks.data) return <Alert color="red">{visible(risks.error.message)}</Alert>
  const listError = risks.error ? (
    <Alert color="red" mb="md">
      {visible(risks.error.message)}
    </Alert>
  ) : null

  if (queue.length === 0) {
    return (
      <div>
        {listError}
        <Text>No risks are waiting for review.</Text>
      </div>
    )
  }

  const index = Math.max(
    0,
    queue.findIndex((r) => r.id === wanted),
  )
  const go = (id: string | undefined) => setParams(id ? { id } : {})

  return (
    <>
      {listError}
      <ReviewItem
        key={queue[index].id}
        reg={reg as Reg}
        slug={slug as string}
        id={queue[index].id}
        position={index + 1}
        total={queue.length}
        previousId={queue[index - 1]?.id}
        nextId={queue[index + 1]?.id}
        afterDecisionId={queue[index + 1]?.id ?? queue[index - 1]?.id}
        go={go}
      />
    </>
  )
}

interface ItemProps {
  reg: Reg
  slug: string
  id: string
  position: number
  total: number
  previousId?: string
  nextId?: string
  afterDecisionId?: string
  go: (id: string | undefined) => void
}

function ReviewItem({ reg, slug, id, position, total, previousId, nextId, afterDecisionId, go }: ItemProps) {
  const navigate = useNavigate()
  const meta = useMeta()
  const fetched = useRisk(reg, slug, id)
  const history = useRiskHistory(reg, slug, id)
  const action = useAction(reg, slug)

  // `shown` is the record on the page, and the only source of `seen`. It changes in two ways, and
  // both show the stale banner: a 409 body, or a later fetch that differs.
  const [shown, setShown] = useState<RiskDetail | null>(null)
  const [stale, setStale] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inFlight = useRef(false)

  const shownRef = useRef<RiskDetail | null>(null)
  const show = (next: RiskDetail) => {
    shownRef.current = next
    setShown(next)
  }

  const client = useQueryClient()
  // Set by a 409. `base` is the risk query's `dataUpdateCount` at that moment. `shownAt` is the
  // count `shown` was last reconciled from. The reload is done only when `shown` comes from a
  // fetch after the 409, so buttons and context change in the same render, and an offline
  // refetch cannot unlock anything.
  const [shownAt, setShownAt] = useState(0)
  const [conflict, setConflict] = useState<{
    base: number
    histBase: number
    failed: boolean
  } | null>(null)
  const riskKey = [reg, slug, 'risk', id]
  const histKey = [...riskKey, 'history']

  // Compare a fetched record with the pinned one. Equal: keep the pinned object and take the
  // fresh context. Different: swap it in and show the banner.
  const reconcile = (data: RiskDetail | undefined) => {
    if (!data) return
    setShownAt(client.getQueryState(riskKey)?.dataUpdateCount ?? 0)
    const prev = shownRef.current
    if (!prev) return show(data)
    if (JSON.stringify(prev.risk) === JSON.stringify(data.risk)) return show({ ...data, risk: prev.risk })
    setStale(true)
    show(data)
  }
  const latest = () => client.getQueryData<RiskDetail>(riskKey)

  const data = fetched.data
  const updatedAt = fetched.dataUpdatedAt
  useEffect(() => {
    if (inFlight.current) return
    reconcile(data)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, updatedAt])

  // An error with a record on the page shows inside the item, below.
  if (fetched.error && !shown) return <Alert color="red">{visible(fetched.error.message)}</Alert>
  if (!shown || !meta.data) return <Loader m="xl" aria-label="Loading" />

  // The history must also have been refetched since the 409, or the old one would show as current.
  // Reading `dataUpdatedAt` subscribes this component to a refetch that returns equal data, which
  // the observer would otherwise not report.
  void history.dataUpdatedAt
  const histCount = client.getQueryState(histKey)?.dataUpdateCount ?? 0
  const awaiting = conflict !== null && (shownAt <= conflict.base || histCount <= conflict.histBase)
  const reloadFailed = awaiting && conflict.failed
  const risk = shown.risk
  const isReReview = !!risk.last_approved
  const base = `/${reg}/${encodeURIComponent(slug)}`

  const decide = async (kind: Decision) => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError(null)
    setStale(false)
    const body = kind === 'merge' ? { into: risk.possible_duplicate_of, note, seen: risk } : { note, seen: risk }
    try {
      await action.mutateAsync({
        path: apiPath(reg, slug, 'risks', risk.id, kind),
        body,
      })
      go(afterDecisionId)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const current = (e.body as Conflict409 | null)?.current
        if (current) show({ ...shown, risk: current as Risk })
        setStale(true)
        const seenAt = client.getQueryState(riskKey)?.dataUpdateCount ?? 0
        const histSeenAt = client.getQueryState(histKey)?.dataUpdateCount ?? 0
        setConflict({ base: seenAt, histBase: histSeenAt, failed: false })
        // The context (elements, duplicate, DFD) belongs to the old record: reload it before any
        // decision, and keep every button disabled until it is here.
        try {
          await Promise.all([
            client.refetchQueries({ queryKey: histKey, exact: true }, { throwOnError: true }),
            client.refetchQueries({ queryKey: riskKey, exact: true }, { throwOnError: true }),
          ])
          // A paused refetch resolves without fetching: only a record newer than the 409 counts.
          if ((client.getQueryState(riskKey)?.dataUpdateCount ?? 0) > seenAt) reconcile(latest())
        } catch {
          setConflict({ base: seenAt, histBase: histSeenAt, failed: true })
        }
      } else {
        setError(refusalText(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)))
        reconcile(latest())
      }
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const model = shown.model
  return (
    <div>
      <Group justify="space-between" mb="md" wrap="wrap">
        <Text fw={700} fz="h3">
          Review queue
        </Text>
        <Group gap="xs">
          <Text size="sm">
            {position} of {total} pending
          </Text>
          <Button variant="default" size="xs" disabled={busy || !previousId} onClick={() => go(previousId)}>
            Previous
          </Button>
          <Button variant="default" size="xs" disabled={busy || !nextId} onClick={() => go(nextId)}>
            Next
          </Button>
        </Group>
      </Group>

      <div className={classes.layout}>
        <div>
          {fetched.error && !reloadFailed && (
            <Alert color="red" mb="md">
              {visible(fetched.error.message)}
            </Alert>
          )}
          {stale && (
            <Alert color="yellow" mb="md">
              {STALE_TEXT}
            </Alert>
          )}
          {risk.possible_duplicate_of && (
            <Alert color="yellow" mb="md">
              <Anchor href="#dup" inherit>
                {visible(`Possible duplicate of ${risk.possible_duplicate_of}.`)}
              </Anchor>
            </Alert>
          )}
          {model.moved_on && !awaiting && (
            <Alert color="yellow" mb="md">
              {visible(
                `The model has moved on: written against ${model.written_against ?? 'an unknown version'}, latest is ${model.latest_id ?? 'none'}. Changed: ${model.changed.join(', ') || 'nothing listed'}.`,
              )}
            </Alert>
          )}
          {isReReview && <ReReviewDiff risk={risk} editable={meta.data.editable} labels={meta.data.labels} />}
          <RiskRecord
            detail={shown}
            meta={meta.data}
            history={history.data ?? []}
            reloading={awaiting}
          />
        </div>
        <aside className={classes.rail}>
          <SectionOutline sections={visibleSections(risk)} />
          <DecisionPanel
            riskId={visible(risk.id)}
            isReReview={isReReview}
            duplicateId={risk.possible_duplicate_of ? visible(risk.possible_duplicate_of) : null}
            noteMin={meta.data.note_min}
            trial={reg === 'trial'}
            busy={busy || awaiting}
            reloading={awaiting && !reloadFailed}
            error={error ?? (reloadFailed ? 'Could not reload this risk. Reload the page before deciding.' : null)}
            note={note}
            onNote={setNote}
            onApprove={() => decide('approve')}
            onReject={() => decide('reject')}
            onMerge={() => decide('merge')}
            onEdit={() => navigate(`${base}/risks/${encodeURIComponent(risk.id)}/edit?return=review`)}
          />
        </aside>
      </div>
    </div>
  )
}
