import json
from pathlib import Path

import pytest

from app.collector.reddit.parse_listing import parse_listing
from app.errors import AppError

FIXTURES = Path(__file__).parent / 'fixtures'
REAL = json.loads((FIXTURES / 'listing-new-ok.json').read_text())


def envelope(nodes, *, prefixed='r/ubisoft', end_cursor='CURSOR'):
    edges = [{'node': n} for n in nodes]
    return {
        'data': {
            'postFeed': {
                '__typename': 'PostFeed',
                'prefixedName': prefixed,
                'elements': {'pageInfo': {'endCursor': end_cursor}, 'edges': edges},
            }
        }
    }


def post_node(**overrides):
    node = {
        '__typename': 'SubredditPost',
        'id': 't3_abc',
        'createdAt': '2026-09-10T11:14:02.764000+0000',
        'title': 'A title',
        'permalink': '/r/ubisoft/comments/abc/a_title/',
        'url': 'https://i.redd.it/x.jpeg',
        'score': 12,
        'commentCount': 3,
        'isStickied': False,
        'authorInfo': {'__typename': 'Redditor', 'name': 'alice'},
        'content': None,
        'flair': None,
    }
    node.update(overrides)
    return node


# Happy path against the real captured response


def test_parses_the_real_captured_listing():
    posts = parse_listing(REAL, limit=25)

    assert len(posts) == 5
    first = posts[0]
    assert first.id == 't3_1wcg6wx'
    assert first.title == 'No more Connect requirement on Steam'
    assert first.author == 'joujoubox'
    assert first.subreddit == 'ubisoft'
    assert first.permalink == (
        'https://www.reddit.com/r/ubisoft/comments/1wcg6wx/no_more_connect_requirement_on_steam/'
    )
    assert first.created_at == '2026-09-10T11:14:02.764Z'
    assert first.comment_count == 43
    assert first.flair == 'News & Announcements'


def test_a_text_post_keeps_its_preview():
    posts = parse_listing(REAL, limit=25)
    media = next(p for p in posts if p.id == 't3_1xiinei')
    assert media.preview_text is not None
    assert 'watch dogs' in media.preview_text.lower()


# Field mapping on controlled nodes


def test_converts_timestamp_and_relative_permalink():
    post = parse_listing(envelope([post_node()]), limit=25)[0]
    assert post.created_at == '2026-09-10T11:14:02.764Z'
    assert post.permalink.startswith('https://www.reddit.com/r/ubisoft/comments/abc/')


def test_a_deleted_author_becomes_none():
    deleted = post_node(authorInfo={'__typename': 'DeletedRedditor', 'name': '[deleted]'})
    assert parse_listing(envelope([deleted]), limit=25)[0].author is None

    missing = post_node(authorInfo=None)
    assert parse_listing(envelope([missing]), limit=25)[0].author is None


def test_flair_without_text_is_none():
    node = post_node(flair={'__typename': 'Flair', 'text': None})
    assert parse_listing(envelope([node]), limit=25)[0].flair is None


# Filtering and limits


def test_ad_and_non_post_nodes_are_skipped():
    nodes = [post_node(id='t3_a'), {'__typename': 'AdPost', 'id': 't3_ad'}, post_node(id='t3_b')]
    posts = parse_listing(envelope(nodes), limit=25)
    assert [p.id for p in posts] == ['t3_a', 't3_b']


def test_duplicate_ids_are_removed():
    posts = parse_listing(envelope([post_node(id='t3_a'), post_node(id='t3_a')]), limit=25)
    assert len(posts) == 1


def test_the_limit_is_respected():
    nodes = [post_node(id=f't3_{i}') for i in range(30)]
    assert len(parse_listing(envelope(nodes), limit=25)) == 25


def test_a_node_missing_a_required_field_is_skipped_not_fatal():
    nodes = [post_node(id='t3_ok'), post_node(id='t3_bad', title=None)]
    posts = parse_listing(envelope(nodes), limit=25)
    assert [p.id for p in posts] == ['t3_ok']


# Empty and contract errors


def test_zero_posts_is_a_valid_empty_result():
    assert parse_listing(envelope([]), limit=25) == []


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'data': None},
        {'data': {'postFeed': {'prefixedName': 'r/x', 'elements': {}}}},
        {'errors': [{'message': 'something'}], 'data': None},
        {'errors': [{'message': 'something'}], 'data': {'postFeed': None}},
    ],
)
def test_a_broken_envelope_raises_contract_error(body):
    with pytest.raises(AppError) as raised:
        parse_listing(body, limit=25)
    assert raised.value.code == 'CONTRACT_ERROR'


# Reddit answers HTTP 200 for these, so the body is the only signal (seen live 2026-10-31).
@pytest.mark.parametrize(
    'body',
    [
        {'data': {'postFeed': None}},  # the subreddit does not exist
        {'data': {'postFeed': {'__typename': 'UnavailableSubreddit'}}},  # banned or private
    ],
)
def test_a_missing_or_unavailable_subreddit_raises_not_found(body):
    with pytest.raises(AppError) as raised:
        parse_listing(body, limit=25)
    assert raised.value.code == 'NOT_FOUND_SUBREDDIT'


def test_all_posts_unmappable_while_some_existed_raises_contract_error():
    nodes = [post_node(id=None), post_node(permalink=None)]
    with pytest.raises(AppError) as raised:
        parse_listing(envelope(nodes), limit=25)
    assert raised.value.code == 'CONTRACT_ERROR'
