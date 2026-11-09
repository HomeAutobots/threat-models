import { Alert, Button, Group, Loader, SegmentedControl, Stack, Switch, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams } from 'react-router'
import { apiGetText, apiPath } from '../api/client'
import type { Reg } from '../api/types'
import { visible } from '../lib/visible'

type Format = 'md' | 'csv' | 'html'

export function ReportsPage() {
  const { reg, slug } = useParams()
  const [format, setFormat] = useState<Format>('md')
  const [pending, setPending] = useState(false)
  const [rejected, setRejected] = useState(false)
  const [retired, setRetired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  const url = (download: boolean) =>
    `${apiPath(reg as Reg, slug as string, 'report')}?format=${format}&include_pending=${pending}` +
    `&include_rejected=${rejected}&include_retired=${retired}&download=${download}`

  const preview = useQuery({
    queryKey: [reg, slug, 'report', format, pending, rejected, retired],
    queryFn: () => apiGetText(url(false)),
    enabled: !!slug,
  })

  const download = async () => {
    setDownloading(true)
    setError(null)
    try {
      // A plain link cannot send the CSRF header, so fetch the text and save it from a Blob.
      const text = await apiGetText(url(true))
      const href = URL.createObjectURL(new Blob([text], { type: 'application/octet-stream' }))
      const a = document.createElement('a')
      a.href = href
      a.download = `${slug}-register.${format}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(href)
    } catch (e) {
      setError(visible(e instanceof Error ? e.message : String(e)))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Stack>
      <Title order={2}>Reports</Title>
      <Group align="flex-end">
        <SegmentedControl
          value={format}
          onChange={(v) => setFormat(v as Format)}
          data={[
            { value: 'md', label: 'md' },
            { value: 'csv', label: 'csv' },
            { value: 'html', label: 'html' },
          ]}
        />
        <Switch label="Include pending" checked={pending} onChange={(e) => setPending(e.currentTarget.checked)} />
        <Switch label="Include rejected" checked={rejected} onChange={(e) => setRejected(e.currentTarget.checked)} />
        <Switch label="Include retired" checked={retired} onChange={(e) => setRetired(e.currentTarget.checked)} />
        <Button onClick={download} loading={downloading}>
          Download
        </Button>
      </Group>
      {error && <Alert color="red">{error}</Alert>}
      {preview.isLoading ? (
        <Loader aria-label="Loading" />
      ) : preview.error ? (
        <Alert color="red">{visible(preview.error.message)}</Alert>
      ) : format === 'html' ? (
        <iframe
          title="Report preview"
          sandbox=""
          srcDoc={preview.data ?? ''}
          style={{ width: '100%', height: '70vh', border: '1px solid var(--mantine-color-gray-4)' }}
        />
      ) : (
        <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0 }}>{visible(preview.data ?? '')}</pre>
      )}
    </Stack>
  )
}
