import { Alert, Anchor, Button, List, Stack } from '@mantine/core'
import { ApiError } from '../../api/client'
import { useC4Export } from '../../api/queries'
import type { Reg } from '../../api/types'
import { visible } from '../../lib/visible'

interface Props {
  reg: Reg
  slug: string
}

export function DiagramLinks({ reg, slug }: Props) {
  const run = useC4Export(reg, slug)
  const views = run.data?.views ?? []
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
