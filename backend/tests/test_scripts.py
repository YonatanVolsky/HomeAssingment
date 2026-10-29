import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'


def run(script, *args):
    result = subprocess.run(
        ['bash', str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True
    )
    return result.returncode, result.stdout + result.stderr


# check-secrets.sh

# Built at runtime so this file never contains a token-shaped value.
FAKE_JWT = '.'.join(['eyJhbGciOiJIUzI1NiJ9', 'eyJzdWIiOiJ0ZXN0LXVzZXItMTIzNDU2In0', 'abc123def456'])


def scan(tmp_path, content):
    sample = tmp_path / 'sample.py'
    sample.write_text(content)
    return run('check-secrets.sh', sample)


def test_secrets_passes_code_that_builds_a_header_from_a_variable(tmp_path):
    assert scan(tmp_path, "headers['authorization'] = f'Bearer {token}'\nsession = 1\n")[0] == 0


def test_secrets_fails_on_a_jwt_without_printing_it(tmp_path):
    code, output = scan(tmp_path, f"token = '{FAKE_JWT}'\n")
    assert code == 1
    assert 'sample.py' in output
    assert FAKE_JWT not in output


@pytest.mark.parametrize(
    'content',
    [
        'curl -H "Authorization: Bearer ' + 'A' * 12 + 'b' * 12 + '"\n',
        '{"access_token": "' + 'x' * 10 + 'Y' * 10 + '"}\n',
    ],
)
def test_secrets_fails_on_literal_tokens(tmp_path, content):
    assert scan(tmp_path, content)[0] == 1


def test_secrets_passes_a_scrubbed_fixture(tmp_path):
    assert scan(tmp_path, '{"access_token": "REDACTED", "expires_in": 3600}\n')[0] == 0


# check-compliance.sh


def word(*parts):
    """Assembled at runtime so this file never contains the forbidden words verbatim."""
    return ''.join(parts)


def tree(tmp_path, files):
    for path, content in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return run('check-compliance.sh', tmp_path)


def test_compliance_passes_clean_source(tmp_path):
    code, _ = tree(tmp_path, {'backend/app/a.py': "url = 'https://www.reddit.com/r/x/'\n"})
    assert code == 0


@pytest.mark.parametrize(
    'forbidden',
    [
        word('pupp', 'eteer'),
        word('sele', 'nium'),
        word('play', 'wright'),
        word('pr', 'aw'),
        word('snoo', 'wrap'),
    ],
)
def test_compliance_fails_on_browser_automation_or_api_clients(tmp_path, forbidden):
    code, output = tree(tmp_path, {'backend/app/a.py': f'import {forbidden}\n'})
    assert code == 1
    assert 'backend/app/a.py' in output


def test_compliance_checks_python_requirements(tmp_path):
    assert tree(tmp_path, {'backend/requirements.txt': word('pr', 'aw') + '==7.7\n'})[0] == 1


def test_compliance_matches_whole_words_only(tmp_path):
    assert tree(tmp_path, {'backend/app/a.py': '# a sprawling comment\n'})[0] == 0


def test_compliance_fails_on_public_json_listings(tmp_path):
    content = "httpx.get('https://www.reddit.com/r/x/new" + ".json')\n"
    assert tree(tmp_path, {'backend/app/a.py': content})[0] == 1


def test_compliance_fails_on_a_reddit_host_not_on_the_allow_list(tmp_path):
    code, output = tree(tmp_path, {'backend/app/a.py': "host = 'https://" + "oauth.reddit.com'\n"})
    assert code == 1
    assert 'not on the allow-list' in output


def test_compliance_ignores_docs(tmp_path):
    content = f'We do not use {word("pupp", "eteer")}.\n'
    assert tree(tmp_path, {'docs/notes.md': content})[0] == 0
