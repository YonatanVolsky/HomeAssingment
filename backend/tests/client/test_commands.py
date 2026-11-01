import pytest

from app.client.commands import Help, Invalid, Quit, Send, ToggleJson, parse


def posts(term, freshness):
    args = {'term': term, 'freshness': freshness}
    return Send({'v': 1, 'command': 'GET', 'resource': 'posts', 'args': args})


@pytest.mark.parametrize('line', ['', '   ', '\n'])
def test_a_blank_line_does_nothing(line):
    assert parse(line) is None


def test_a_plain_term_gets_posts_with_auto_freshness():
    assert parse('  r/ubisoft  ') == posts('r/ubisoft', 'auto')


@pytest.mark.parametrize('freshness', ['auto', 'live', 'stored'])
def test_a_freshness_command_names_the_freshness(freshness):
    assert parse(f':{freshness} r/ubisoft') == posts('r/ubisoft', freshness)


def test_the_term_is_sent_as_typed_for_the_collector_to_normalize():
    assert parse(':live  https://www.reddit.com/r/Ubisoft/ ') == posts(
        'https://www.reddit.com/r/Ubisoft/', 'live'
    )


def test_health():
    assert parse(':health') == Send({'v': 1, 'command': 'GET', 'resource': 'health'})


@pytest.mark.parametrize(('line', 'expected'), [(':json', ToggleJson()), (':help', Help())])
def test_local_commands(line, expected):
    assert parse(line) == expected


@pytest.mark.parametrize('line', [':quit', ':exit', ':q', ':QUIT'])
def test_quit(line):
    assert parse(line) == Quit()


def test_commands_are_case_insensitive_but_terms_are_not():
    assert parse(':LIVE Ubisoft') == posts('Ubisoft', 'live')


@pytest.mark.parametrize('line', [':live', ':stored   '])
def test_a_freshness_command_needs_a_term(line):
    assert isinstance(parse(line), Invalid)


@pytest.mark.parametrize('line', [':nope', ':health now', ':json please'])
def test_unknown_commands_and_extra_words_are_invalid(line):
    result = parse(line)
    assert isinstance(result, Invalid)
    assert ':help' in result.reason
