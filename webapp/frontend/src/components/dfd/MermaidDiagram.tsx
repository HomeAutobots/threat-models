import { Code, Stack, Text } from '@mantine/core'
import { useEffect, useId, useState } from 'react'

let counter = 0

export function MermaidDiagram({ source }: { source: string }) {
  const base = useId().replace(/[^A-Za-z0-9]/g, '')
  const [svg, setSvg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    setSvg(null)
    setError(null)
    ;(async () => {
      try {
        const { default: mermaid } = await import('mermaid')
        // "strict" encodes HTML in labels and disables click handlers; never loosen it.
        mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' })
        const out = await mermaid.render(`mmd${base}${counter++}`, source)
        if (live) setSvg(out.svg)
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      live = false
    }
  }, [source, base])

  if (error !== null) {
    return (
      <Stack gap="xs">
        <Text c="red" size="sm" style={{ overflowWrap: 'anywhere' }}>
          Diagram error: {error}
        </Text>
        <Code block>{source}</Code>
      </Stack>
    )
  }
  if (svg === null) return <Text size="sm">Drawing diagram</Text>
  // The SVG comes from mermaid in strict mode, which sanitizes label text; it is the only
  // HTML this app inserts from file content.
  return <div style={{ overflowX: 'auto' }} dangerouslySetInnerHTML={{ __html: svg }} />
}
