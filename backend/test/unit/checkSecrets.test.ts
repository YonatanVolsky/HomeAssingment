import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SCRIPT = resolve(__dirname, '../../../scripts/check-secrets.sh');

function scan(content: string): { code: number; output: string } {
  const dir = mkdtempSync(join(tmpdir(), 'secrets-'));
  const file = join(dir, 'sample.ts');
  writeFileSync(file, content);
  try {
    const output = execFileSync('bash', [SCRIPT, file], { encoding: 'utf8', stdio: 'pipe' });
    return { code: 0, output };
  } catch (error) {
    const failure = error as { status: number; stdout: string; stderr: string };
    return { code: failure.status, output: failure.stdout + failure.stderr };
  }
}

// Built at runtime so this test file itself never contains a token-shaped value.
const fakeJwt = [
  'eyJhbGciOiJIUzI1NiJ9',
  'eyJzdWIiOiJ0ZXN0LXVzZXItMTIzNDU2In0',
  'abc123def456',
].join('.');

describe('check-secrets.sh', () => {
  it('passes code that builds an Authorization header from a variable', () => {
    const result = scan('headers.authorization = `Bearer ${token}`;\nconst session = 1;\n');
    expect(result.code).toBe(0);
  });

  it('fails on a JWT-shaped value and does not print the value', () => {
    const result = scan(`const token = "${fakeJwt}";\n`);

    expect(result.code).toBe(1);
    expect(result.output).toContain('sample.ts');
    expect(result.output).not.toContain(fakeJwt);
  });

  it('fails on a literal bearer token', () => {
    const literal = 'Bearer ' + 'A'.repeat(12) + 'b'.repeat(12);
    expect(scan(`curl -H "Authorization: ${literal}"\n`).code).toBe(1);
  });

  it('fails on a long quoted access_token value', () => {
    const value = 'x'.repeat(10) + 'Y'.repeat(10);
    expect(scan(`{"access_token": "${value}"}\n`).code).toBe(1);
  });

  it('passes a scrubbed fixture', () => {
    expect(scan('{"access_token": "REDACTED", "expires_in": 3600}\n').code).toBe(0);
  });
});
