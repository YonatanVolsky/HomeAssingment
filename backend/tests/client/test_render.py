import json

from app.client.render import render
from tests.helpers import make_post


def feed(posts=None, source='live'):
    if posts is None:
        posts = [make_post('t3_a', title='First', score=12, comment_count=3)]
    return {
        'collection': {
            'id': 1,
            'term': 'ubisoft',
            'source': source,
            'collectedAt': '2026-10-31T14:55:24.992Z',
            'postCount': len(posts),
        },
        'posts': [post.model_dump(by_alias=True) for post in posts],
    }


def ok(result):
    return {'ok': True, 'result': result}


def test_a_feed_has_a_summary_line_then_one_block_per_post():
    text = render('posts', ok(feed()), as_json=False)
    assert text.splitlines() == [
        'r/ubisoft · 1 post · live · collected 2026-10-31 14:55:24 UTC',
        '  1. First',
        '     u/someone · 12 points · 3 comments',
        '     https://www.reddit.com/r/ubisoft/comments/t3_a/',
    ]


def test_counts_are_plural_and_a_deleted_author_is_named():
    posts = [make_post('t3_a', author=None, score=1, comment_count=1), make_post('t3_b')]
    text = render('posts', ok(feed(posts, source='cache')), as_json=False)
    assert text.startswith('r/ubisoft · 2 posts · cache ·')
    assert 'u/[deleted] · 1 point · 1 comment' in text
    assert '  2. Post t3_b' in text


def test_an_empty_feed_says_so():
    text = render('posts', ok(feed([])), as_json=False)
    assert text.splitlines()[1] == '  No posts found.'


def test_a_term_never_collected():
    assert render('posts', ok({'collection': None, 'posts': []}), as_json=False) == (
        'Nothing stored for this subreddit yet.'
    )


def test_health():
    result = {'status': 'ok', 'db': 'ok', 'collectorMode': 'fixture', 'staleAfterSeconds': 600}
    assert render('health', ok(result), as_json=False) == (
        'status ok · database ok · mode fixture · stale after 600 s'
    )


def test_an_error_shows_code_and_message_once():
    # The collector's message already names the wait; it is not repeated.
    reply = {
        'ok': False,
        'error': {
            'code': 'RATE_LIMITED',
            'message': 'Reddit is limiting requests. Try again in 30 seconds.',
            'retryable': True,
            'retryAfterSeconds': 30,
        },
    }
    assert render('posts', reply, as_json=False) == (
        'error RATE_LIMITED: Reddit is limiting requests. Try again in 30 seconds. (can retry)'
    )


def test_an_error_that_cannot_be_retried_says_so():
    reply = {'ok': False, 'error': {'code': 'INVALID_TERM', 'message': 'Bad.', 'retryable': False}}
    assert render('posts', reply, as_json=False) == 'error INVALID_TERM: Bad. (no retry)'


def test_an_error_with_a_last_good_feed_shows_it_below():
    error = {'code': 'UPSTREAM_ERROR', 'message': 'Down.', 'retryable': True}
    reply = {'ok': False, 'error': error, 'lastGood': feed(source='cache')}
    lines = render('posts', reply, as_json=False).splitlines()
    assert lines[0] == 'error UPSTREAM_ERROR: Down. (can retry)'
    assert lines[1] == 'Last good feed:'
    assert lines[2].startswith('r/ubisoft · 1 post · cache')


def test_json_mode_prints_the_whole_reply_indented():
    reply = ok(feed())
    text = render('posts', reply, as_json=True)
    assert json.loads(text) == reply
    assert '\n  "ok": true' in text
