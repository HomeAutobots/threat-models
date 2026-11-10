import { Alert, Anchor, Button, List, Stack, Text } from '@mantine/core'
import { ApiError } from '../../api/client'
import { useC4Export } from '../../api/queries'
import type { Reg, StructurizrVerdict } from '../../api/types'
import { visible } from '../../lib/visible'

interface Props {
  reg: Reg
  slug: string
  /** The file as shown: its sha256 and version, and the verdict recorded for those exact bytes. */
  sha256: string | null
  version: string | null
  verdict: StructurizrVerdict
}

export function DiagramLinks({ reg, slug, sha256, version, verdict }: Props) {
  const run = useC4Export(reg, slug)
  // The export just run, if it was of this file; otherwise an accepted export already kept for it.
  const fresh = run.data && run.data.sha256 === sha256 && run.data.views.length > 0 ? run.data.views : null
  const kept = verdict.state === 'accepted' ? verdict.views : []
  const views = fresh ?? kept
  const failure = run.error
    ? failureText(run.error)
    : null
  return (
    <Stack gap="xs">
      <div>
        <Button onClick={() => run.mutate()} loading={run.isPending}>
          Open diagrams
        </Button>
      </div>
      {failure && (
        <Alert color="red" style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>
          {failure}
        </Alert>
      )}
      {views.length > 0 && (
        <Text size="sm">{`Diagrams for version ${visible(version ?? '')}, sha256 ${visible(sha256 ?? '')}`}</Text>
      )}
      {views.length > 0 && (
        <List aria-label="Diagram views" size="sm">
          {views.map((v) => (
            <List.Item key={v.key}>
              <Anchor href={v.url} target="_blank" rel="noreferrer noopener">
                {visible(v.key)}
              </Anchor>
            </List.Item>
          ))}
        </List>
      )}
    </Stack>
  )
}

function failureText(e: unknown): string {
  return visible(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e))
}
