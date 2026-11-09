import { Alert, Button, Group, Loader, Paper, Stack, Text, Title } from '@mantine/core'
import { Link, useParams } from 'react-router'
import { useMeta, useRisk, useRiskHistory } from '../api/queries'
import type { Reg } from '../api/types'
import classes from '../components/review/review.module.css'
import { RiskRecord, visibleSections } from '../components/record/RiskRecord'
import { SectionOutline } from '../components/record/SectionOutline'
import { visible } from '../lib/visible'

interface Props {
  /** Task 11 wires the status and retire modals here. */
  onChangeStatus?: () => void
  onRetire?: () => void
}

export function RiskPage({ onChangeStatus, onRetire }: Props = {}) {
  const { reg, slug, id } = useParams()
  const meta = useMeta()
  const fetched = useRisk(reg as Reg, slug ?? '', id ?? '')
  const history = useRiskHistory(reg as Reg, slug ?? '', id ?? '')

  if (fetched.error) return <Alert color="red">{fetched.error.message}</Alert>
  if (!fetched.data || !meta.data) return <Loader m="xl" aria-label="Loading" />

  const detail = fetched.data
  const risk = detail.risk
  const base = `/${reg}/${encodeURIComponent(slug as string)}`
  const retired = risk.review_state === 'approved' && risk.status === 'retired'
  const rejected = risk.review_state === 'rejected'
  const editable = !rejected && !retired

  return (
    <div>
      <Title order={1} size="h3" mb="md">
        {visible(risk.id)}
      </Title>
      <div className={classes.layout}>
        <main>
          <RiskRecord detail={detail} meta={meta.data} history={history.data ?? []} />
        </main>
        <aside className={classes.rail}>
          <SectionOutline sections={visibleSections(risk)} />
          <Paper withBorder p="md">
            <Stack gap="sm">
              <Title order={2} size="h5">
                Actions
              </Title>
              {risk.review_state === 'pending' && (
                <Button component={Link} to={`${base}/review?id=${encodeURIComponent(risk.id)}`}>
                  Review this risk
                </Button>
              )}
              {editable && (
                <Group gap="xs">
                  <Button component={Link} to={`${base}/risks/${encodeURIComponent(risk.id)}/edit`} variant="default">
                    Edit
                  </Button>
                  <Button variant="default" onClick={onChangeStatus}>
                    Change status
                  </Button>
                </Group>
              )}
              {risk.review_state === 'approved' && !retired && (
                <Button color="red" variant="outline" onClick={onRetire}>
                  Retire
                </Button>
              )}
              {rejected && <Text size="sm">Rejected risks are read-only.</Text>}
              {retired && <Text size="sm">Retired risks are read-only. To bring one back, add it as a new risk.</Text>}
            </Stack>
          </Paper>
        </aside>
      </div>
    </div>
  )
}
