// The only Node API the Playwright config and tests use; avoids a dependency on @types/node.
declare const process: { env: Record<string, string | undefined> }
