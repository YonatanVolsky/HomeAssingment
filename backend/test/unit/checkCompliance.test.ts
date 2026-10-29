import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SCRIPT = resolve(__dirname, '../../../scripts/check-compliance.sh');

function check(files: Record<string, string>): { code: number; output: string } {
  const root = mkdtempSync(join(tmpdir(), 'compliance-'));
  for (const [path, content] of Object.entries(files)) {
    mkdirSync(join(root, path, '..'), { recursive: true });
    writeFileSync(join(root, path), content);
  }
  try {
    return { code: 0, output: execFileSync('bash', [SCRIPT, root], { encoding: 'utf8' }) };
  } catch (error) {
    const failure = error as { status: number; stdout: string; stderr: string };
    return { code: failure.status, output: failure.stdout + failure.stderr };
  }
}

// Assembled at runtime so this test file never contains the forbidden words verbatim.
const word = (...parts: string[]) => parts.join('');

describe('check-compliance.sh', () => {
  it('passes clean source', () => {
    const result = check({ 'backend/src/a.ts': 'const url = "https://www.reddit.com/r/x/";\n' });
    expect(result.code).toBe(0);
  });

  it.each([
    word('pupp', 'eteer'),
    word('sele', 'nium'),
    word('play', 'wright'),
    word('pr', 'aw'),
    word('snoo', 'wrap'),
  ])('fails when source uses %s', (forbidden) => {
    const result = check({ 'backend/src/a.ts': `import x from '${forbidden}';\n` });
    expect(result.code).toBe(1);
    expect(result.output).toContain('backend/src/a.ts');
  });

  it('fails when a dependency manifest lists a browser automation package', () => {
    const result = check({ 'package.json': `{"dependencies":{"${word('pupp', 'eteer')}":"1"}}` });
    expect(result.code).toBe(1);
  });

  it('matches whole words only', () => {
    expect(check({ 'backend/src/a.ts': '// a sprawling comment\n' }).code).toBe(0);
  });

  it("fails on Reddit's public .json listing endpoints", () => {
    const result = check({
      'backend/src/a.ts': `fetch('https://www.reddit.com/r/x/new${'.json'}')\n`,
    });
    expect(result.code).toBe(1);
  });

  it('fails on a Reddit host that is not on the allow-list', () => {
    const result = check({ 'backend/src/a.ts': `const host = 'https://${'oauth'}.reddit.com';\n` });
    expect(result.code).toBe(1);
    expect(result.output).toMatch(/not on the allow-list/);
  });

  it('ignores docs and markdown, which may name the forbidden tools', () => {
    const result = check({ 'docs/notes.md': `We do not use ${word('pupp', 'eteer')}.\n` });
    expect(result.code).toBe(0);
  });
});
