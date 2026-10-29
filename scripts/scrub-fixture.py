#!/usr/bin/env python3
"""Extract a GraphQL response from a mitmproxy/HTTP-Toolkit HAR into a test fixture.

Trims the post list to a few representative nodes and blanks any value whose key looks
secret (defence in depth: a listing response holds public post data, not tokens).

Usage: scripts/scrub-fixture.py <capture.har> <operationName> <out.json> [--limit N]
"""
import argparse
import json
import re

SECRET_KEY = re.compile(r'token|loid|session|device|secret|email|authorization|cookie', re.I)


def scrub(value):
    if isinstance(value, dict):
        return {k: ('REDACTED' if SECRET_KEY.search(k) and isinstance(v, str) else scrub(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('har')
    parser.add_argument('operation')
    parser.add_argument('out')
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()

    har = json.load(open(args.har))
    marker = f'"{args.operation}"'
    entry = next(e for e in har['log']['entries']
                 if marker in ((e['request'].get('postData') or {}).get('text') or '')[:200])
    body = json.loads(entry['response']['content']['text'])

    edges = body.get('data', {}).get('postFeed', {}).get('elements', {}).get('edges')
    if edges is not None:
        kept = [e for e in edges if e['node']['__typename'] == 'SubredditPost'][: args.limit]
        body['data']['postFeed']['elements']['edges'] = kept

    json.dump(scrub(body), open(args.out, 'w'), indent=2)
    print(f'wrote {args.out}: {len(json.dumps(body)) // 1024} KB')


if __name__ == '__main__':
    main()
