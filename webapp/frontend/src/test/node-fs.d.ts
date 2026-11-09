// The one Node call the tests make (AppShell.test.tsx reads a stylesheet), declared here so the
// build does not need @types/node.
declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf8'): string
}
