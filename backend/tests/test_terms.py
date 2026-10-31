import pytest

from app.errors import AppError
from app.terms.normalizer import TermNormalizer, TermProtocol
from app.terms.presets import DEFAULT_PRESET, PRESETS
from app.terms.steps import (
    extract_reddit_link,
    lowercase,
    require_pattern,
    strip_r_prefix,
    strip_trailing_slash,
    trim,
)


def assert_invalid(call, *args):
    with pytest.raises(AppError) as raised:
        call(*args)
    assert raised.value.code == 'INVALID_TERM'


# Steps


def test_trim_strips_surrounding_whitespace():
    assert trim('  a b  ') == 'a b'


@pytest.mark.parametrize(
    ('link', 'name'),
    [
        ('https://www.reddit.com/r/Ubisoft/', 'Ubisoft'),
        ('reddit.com/r/ubisoft/new', 'ubisoft'),
        ('https://old.reddit.com/r/Ubisoft/new/?sort=new', 'Ubisoft'),
        ('www.reddit.com/r/Ubisoft/comments/abc/x/', 'Ubisoft'),
    ],
)
def test_extract_reddit_link_takes_the_segment_after_r(link, name):
    assert extract_reddit_link(link) == name


@pytest.mark.parametrize('link', ['reddit.com', 'https://www.reddit.com/user/x'])
def test_extract_reddit_link_rejects_a_reddit_link_without_r(link):
    assert_invalid(extract_reddit_link, link)


@pytest.mark.parametrize(
    'text', ['ubisoft', 'r/ubisoft', 'https://reddit.com.evil.com/r/x', 'https://example.com/r/x']
)
def test_extract_reddit_link_passes_other_text_through(text):
    assert extract_reddit_link(text) == text


@pytest.mark.parametrize(
    ('text', 'expected'), [('r/x', 'x'), ('/R/x', 'x'), ('x', 'x'), ('xr/y', 'xr/y')]
)
def test_strip_r_prefix(text, expected):
    assert strip_r_prefix(text) == expected


@pytest.mark.parametrize(('text', 'expected'), [('x/', 'x'), ('x', 'x'), ('x//', 'x/')])
def test_strip_trailing_slash(text, expected):
    assert strip_trailing_slash(text) == expected


def test_require_pattern_matches_the_whole_text():
    step = require_pattern('[a-z]{2}')
    assert step('ab') == 'ab'
    assert_invalid(step, 'abc')
    assert_invalid(step, 'a')


def test_lowercase():
    assert lowercase('AbC') == 'abc'


# Normalizer


def test_normalizer_runs_the_steps_in_order():
    protocol = TermProtocol('test', (trim, str.upper, lambda text: text + '!'))
    assert TermNormalizer(protocol).normalize('  ab ') == 'AB!'


def test_normalizer_rejects_an_empty_result():
    assert_invalid(TermNormalizer(TermProtocol('test', (trim,))).normalize, '   ')


def test_normalizer_lets_step_errors_through():
    error = AppError('INVALID_TERM')

    def reject(_text):
        raise error

    with pytest.raises(AppError) as raised:
        TermNormalizer(TermProtocol('test', (reject,))).normalize('x')
    assert raised.value is error


def test_a_protocol_needs_at_least_one_step():
    with pytest.raises(ValueError):
        TermProtocol('x', ())


# The reddit-subreddit preset: reproduces the rules of the former normalize_term exactly.


def reddit_subreddit():
    return TermNormalizer(PRESETS['reddit-subreddit'])


@pytest.mark.parametrize(
    ('term', 'expected'),
    [
        ('ubisoft', 'ubisoft'),
        ('r/Ubisoft', 'ubisoft'),
        ('/r/Ubisoft/', 'ubisoft'),
        ('  R/UBISOFT  ', 'ubisoft'),
        ('https://www.reddit.com/r/ubisoft/', 'ubisoft'),
        ('https://old.reddit.com/r/Ubisoft/new/?sort=new', 'ubisoft'),
        ('reddit.com/r/ubisoft', 'ubisoft'),
        ('de', 'de'),
        ('Ask_Reddit_2', 'ask_reddit_2'),
        ('a' * 21, 'a' * 21),
        ('reddit.com/r/ubisoft/new', 'ubisoft'),
        ('www.reddit.com/r/Ubisoft/comments/abc/some_post/', 'ubisoft'),
    ],
)
def test_reddit_subreddit_accepts(term, expected):
    assert reddit_subreddit().normalize(term) == expected


@pytest.mark.parametrize(
    'term',
    [
        '',
        '   ',
        'r/',
        '/r/',
        'a',
        'a' * 22,
        'bad name!',
        'ubisoft crash',
        'r/ubi-soft',
        'https://example.com/r/ubisoft',
        'r/ubisoft/new',
        'https://reddit.com.evil.com/r/x',
        'reddit.com',
        'u/someone',
        'ubisöft',
    ],
)
def test_reddit_subreddit_rejects(term):
    assert_invalid(reddit_subreddit().normalize, term)


def test_the_default_preset_exists():
    assert DEFAULT_PRESET in PRESETS
    assert PRESETS[DEFAULT_PRESET].name == DEFAULT_PRESET


def test_presets_are_read_only():
    with pytest.raises(TypeError):
        PRESETS['x'] = PRESETS[DEFAULT_PRESET]  # type: ignore[index]
