// The only Node APIs the Playwright config and tests use; avoids a dependency on @types/node.
declare const process: { env: Record<string, string | undefined> }

declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf8'): string
}
