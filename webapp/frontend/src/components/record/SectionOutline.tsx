import { Box, Text, VisuallyHidden } from '@mantine/core'
import { useEffect, useState } from 'react'
import type { Section } from './sections'

/** One dot per section. A dot fills when its card first intersects the viewport and stays filled. */
export function SectionOutline({ sections }: { sections: Pick<Section, 'id' | 'n' | 'title'>[] }) {
  const [seen, setSeen] = useState<Set<string>>(new Set())
  const key = sections.map((s) => s.id).join(',')

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      const hit = entries.filter((e) => e.isIntersecting).map((e) => e.target.id)
      if (hit.length === 0) return
      setSeen((prev) => {
        if (hit.every((id) => prev.has(id))) return prev
        return new Set([...prev, ...hit])
      })
    })
    for (const id of key.split(',')) {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [key])

  return (
    <nav aria-label="Sections">
      <Box component="ul" m={0} p={0} style={{ listStyle: 'none' }}>
        {sections.map((s) => (
          <Box component="li" key={s.id} py={4} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span
              aria-hidden
              data-testid={`dot-${s.id}`}
              data-seen={seen.has(s.id) ? 'true' : 'false'}
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                flex: 'none',
                border: '1.5px solid var(--mantine-color-dimmed)',
                background: seen.has(s.id) ? 'var(--mantine-color-green-6)' : 'transparent',
                borderColor: seen.has(s.id) ? 'var(--mantine-color-green-6)' : undefined,
              }}
            />
            <VisuallyHidden>{seen.has(s.id) ? 'seen' : 'not yet read'}</VisuallyHidden>
            <Text component="a" href={`#${s.id}`} size="sm" td="none" c="inherit">
              {s.n} {s.title}
            </Text>
          </Box>
        ))}
      </Box>
    </nav>
  )
}
