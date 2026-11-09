import { Alert, Anchor, Button, Group, Loader, Text, Title } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { useAction, useMeta, useRisk, useRiskHistory, useRisks } from '../api/queries'
import { ApiError, apiPath } from '../api/client'
import type { Conflict409, Reg, Risk, RiskDetail } from '../api/types'
import { ReReviewDiff } from '../components/review/ReReviewDiff'
import { DecisionPanel } from '../components/review/DecisionPanel'
import classes from '../components/review/review.module.css'
import { RiskRecord, visibleSections } from '../components/record/RiskRecord'
import { SectionOutline } from '../components/record/SectionOutline'
import { visible } from '../lib/visible'

const STALE_TEXT = 'This risk changed after you opened it. Review the current version.'

type Decision = 'approve' | 'reject' | 'merge'

export function ReviewPage() {
  const { reg, slug } = useParams()
  const [params, setParams] = useSearchParams()
  const risks = useRisks(reg as Reg, slug ?? '')

  // Pin the shown item into the URL, so a background refetch of the list cannot switch it.
  const firstPending = (risks.data ?? []).find((r) => r.review_state === 'pending')?.id
  const unpinned = !params.get('id') && !!firstPending
  useEffect(() => {
    if (unpinned && firstPending) setParams({ id: firstPending }, { replace: true })
  }, [unpinned, firstPending, setParams])

  if (risks.isLoading) return <Loader m="xl" aria-label="Loading" />
  if (risks.error) return <Alert color="red">{risks.error.message}</Alert>

  const queue = (risks.data ?? []).filter((r) => r.review_state === 'pending')
  if (queue.length === 0) return <Text>No risks are waiting for review.</Text>

  const wanted = params.get('id')
  const index = Math.max(0, queue.findIndex((r) => r.id === wanted))
  const go = (id: string | undefined) => setParams(id ? { id } : {})

  return (
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
  const [reloadFailed, setReloadFailed] = useState(false)

  // Compare a fetched record with the pinned one. Equal: keep the pinned object and take the
  // fresh context. Different: swap it in and show the banner.
  const reconcile = (data: RiskDetail | undefined) => {
    if (!data) return
    const prev = shownRef.current
    if (!prev) return show(data)
    if (JSON.stringify(prev.risk) === JSON.stringify(data.risk)) return show({ ...data, risk: prev.risk })
    setStale(true)
    show(data)
  }
  const latest = () => client.getQueryData<RiskDetail>([reg, slug, 'risk', id])

  const data = fetched.data
  useEffect(() => {
    if (inFlight.current) return
    reconcile(data)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  if (fetched.error) return <Alert color="red">{fetched.error.message}</Alert>
  if (!shown || !meta.data) return <Loader m="xl" aria-label="Loading" />

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
      await action.mutateAsync({ path: apiPath(reg, slug, 'risks', risk.id, kind), body })
      go(afterDecisionId)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const current = (e.body as Conflict409 | null)?.current
        if (current) show({ ...shown, risk: current as Risk })
        setStale(true)
        // The context (elements, duplicate, DFD) belongs to the old record: reload it before any
        // decision, and keep every button disabled until it is here.
        try {
          await client.refetchQueries({ queryKey: [reg, slug, 'risk', id], exact: true }, { throwOnError: true })
          reconcile(latest())
        } catch {
          setReloadFailed(true)
          setError('Could not reload this risk. Reload the page before deciding.')
        }
      } else {
        setError(visible(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)))
        reconcile(latest())
      }
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const dfd = shown.dfd
  return (
    <div>
      <Group justify="space-between" mb="md" wrap="wrap">
        <Title order={1} size="h3">
          Review queue
        </Title>
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
        <main>
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
          {dfd.state === 'changed' && (
            <Alert color="yellow" mb="md">
              <Text inherit>
                {visible(
                  `DFD has moved on. This draft was written against ${dfd.written_against ?? 'an unknown version'}, and dfd.md has changed since. Element IDs may be out of date.`,
                )}
              </Text>
              <Anchor component={Link} to={`${base}/dfd`} inherit>
                Open the DFD page
              </Anchor>
            </Alert>
          )}
          {isReReview && <ReReviewDiff risk={risk} editable={meta.data.editable} labels={meta.data.labels} />}
          <RiskRecord detail={shown} meta={meta.data} history={history.data ?? []} />
        </main>
        <aside className={classes.rail}>
          <SectionOutline sections={visibleSections(risk)} />
          <DecisionPanel
            riskId={visible(risk.id)}
            isReReview={isReReview}
            duplicateId={risk.possible_duplicate_of ? visible(risk.possible_duplicate_of) : null}
            noteMin={meta.data.note_min}
            busy={busy || reloadFailed}
            error={error}
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
