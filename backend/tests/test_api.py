import asyncio
import logging

import httpx
import pytest

from app.api import build_app
from app.config import load_config
from app.errors import AppError
from tests.fakes import FakeCollector, memory_repository
from tests.helpers import FakeClock, make_post

pytestmark = pytest.mark.anyio


@pytest.fixture
async def env():
    clock = FakeClock()
    collector = FakeCollector()
    db, repository = memory_repository(clock)
    app = build_app(
        repository=repository,
        collector=collector,
        clock=clock,
        config=load_config({'STALE_AFTER_SECONDS': '600'}),
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        yield client, collector, clock, db
    db.close()


async def post(client, body):
    return await client.post('/api/collections', json=body)


async def test_health_reports_mode_and_stale_threshold(env):
    client, *_ = env
    response = await client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {
        'status': 'ok',
        'db': 'ok',
        'collectorMode': 'live',
        'staleAfterSeconds': 600,
    }


async def test_health_is_503_when_the_database_is_unavailable(env):
    client, _, _, db = env
    db.close()
    response = await client.get('/api/health')
    assert response.status_code == 503
    assert response.json()['db'] == 'error'


async def test_collect_returns_the_stored_posts(env):
    client, *_ = env
    response = await post(client, {'term': 'r/ubisoft'})
    body = response.json()
    assert response.status_code == 200
    assert body['collection']['term'] == 'ubisoft'
    assert body['collection']['source'] == 'live'
    assert body['collection']['postCount'] == 2
    assert {'commentCount', 'createdAt', 'previewText'} <= set(body['posts'][0])


async def test_repeat_is_cached_and_force_is_live(env):
    client, collector, *_ = env
    await post(client, {'term': 'ubisoft'})
    assert (await post(client, {'term': 'ubisoft'})).json()['collection']['source'] == 'cache'
    forced = await post(client, {'term': 'ubisoft', 'force': True})
    assert forced.json()['collection']['source'] == 'live'
    assert len(collector.calls) == 2


async def test_zero_posts_is_200_with_an_empty_list(env):
    client, collector, *_ = env
    collector.result = []
    response = await post(client, {'term': 'quiet'})
    assert response.status_code == 200
    assert response.json()['posts'] == []


async def test_two_simultaneous_requests_make_one_collector_call(env):
    client, collector, *_ = env
    collector.hold()
    both = asyncio.gather(post(client, {'term': 'ubisoft'}), post(client, {'term': 'ubisoft'}))
    await asyncio.sleep(0.05)
    collector.release()
    a, b = await both
    assert len(collector.calls) == 1
    assert a.json()['collection']['id'] == b.json()['collection']['id']


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'term': 42},
        {'term': ''},
        {'term': 'x' * 201},
        {'term': 'r/'},
        {'term': 'ubisoft', 'force': 'yes'},
        [],
    ],
)
async def test_invalid_requests_are_400_invalid_term(env, body):
    client, collector, *_ = env
    response = await post(client, body)
    assert response.status_code == 400
    assert response.json() == {
        'error': {
            'code': 'INVALID_TERM',
            'message': 'Enter a subreddit name like r/ubisoft.',
            'retryable': False,
        }
    }
    assert collector.calls == []


async def test_malformed_json_is_400_invalid_term(env):
    client, *_ = env
    response = await client.post(
        '/api/collections', content=b'{"term":', headers={'content-type': 'application/json'}
    )
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'INVALID_TERM'


async def test_a_body_over_1_kb_is_rejected(env):
    client, *_ = env
    response = await post(client, {'term': 'ubisoft', 'padding': 'x' * 2000})
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'INVALID_TERM'


@pytest.mark.parametrize(
    ('code', 'status', 'retryable'),
    [
        ('NOT_FOUND_SUBREDDIT', 404, False),
        ('UPSTREAM_AUTH', 502, True),
        ('UPSTREAM_ERROR', 502, True),
        ('UPSTREAM_TIMEOUT', 504, True),
        ('CONTRACT_ERROR', 502, True),
    ],
)
async def test_collector_errors_map_to_http_statuses(env, code, status, retryable):
    client, collector, *_ = env
    collector.result = AppError(code)
    response = await post(client, {'term': 'ubisoft'})
    assert response.status_code == status
    assert response.json()['error']['code'] == code
    assert response.json()['error']['retryable'] is retryable


async def test_rate_limits_are_429_with_retry_after(env):
    client, collector, *_ = env
    collector.result = AppError('RATE_LIMITED', retry_after_seconds=17)
    response = await post(client, {'term': 'ubisoft'})
    assert response.status_code == 429
    assert response.headers['retry-after'] == '17'
    assert response.json()['error']['retryAfterSeconds'] == 17


async def test_a_failed_save_is_500_db_error(env):
    client, collector, *_ = env
    collector.result = [make_post('t3_bad', comment_count=-1)]
    response = await post(client, {'term': 'ubisoft'})
    assert response.status_code == 500
    assert response.json()['error']['code'] == 'DB_ERROR'


async def test_errors_carry_the_last_good_feed_when_there_is_one(env):
    client, collector, *_ = env
    collector.result = AppError('UPSTREAM_TIMEOUT')
    assert 'lastGood' not in (await post(client, {'term': 'ubisoft'})).json()

    collector.result = [make_post('t3_a')]
    await post(client, {'term': 'ubisoft', 'force': True})
    collector.result = AppError('UPSTREAM_TIMEOUT')
    response = await post(client, {'term': 'ubisoft', 'force': True})

    assert response.status_code == 504
    assert response.json()['lastGood']['collection']['source'] == 'cache'
    assert len(response.json()['lastGood']['posts']) == 1


async def test_responses_never_leak_causes_or_tracebacks(env):
    client, collector, *_ = env
    collector.result = AppError('UPSTREAM_AUTH', cause=RuntimeError('Bearer secret-token-123'))
    body = (await post(client, {'term': 'ubisoft'})).text
    assert 'secret-token-123' not in body
    assert 'Traceback' not in body


async def test_an_unexpected_exception_is_a_safe_500(env):
    client, collector, *_ = env
    collector.result = TypeError("'NoneType' object is not subscriptable")
    response = await post(client, {'term': 'ubisoft'})
    assert response.status_code == 500
    assert response.json() == {
        'error': {'code': 'INTERNAL', 'message': 'Something went wrong.', 'retryable': True}
    }


async def test_authorization_and_cookie_headers_are_never_logged(env, caplog):
    client, *_ = env
    caplog.set_level(logging.DEBUG)
    await client.post(
        '/api/collections',
        json={'term': 'ubisoft'},
        headers={'authorization': 'Bearer leaked-value', 'cookie': 'session=leaked-cookie'},
    )
    assert 'leaked-value' not in caplog.text
    assert 'leaked-cookie' not in caplog.text


async def test_get_posts_for_a_term_never_collected(env):
    client, *_ = env
    response = await client.get('/api/posts', params={'term': 'ubisoft'})
    assert response.status_code == 200
    assert response.json() == {'collection': None, 'posts': []}


async def test_get_posts_returns_the_last_collection_from_the_database(env):
    client, collector, clock, _ = env
    collected = (await post(client, {'term': 'ubisoft'})).json()
    clock.advance(3600)

    response = await client.get('/api/posts', params={'term': 'r/Ubisoft'})

    assert response.json()['posts'] == collected['posts']
    assert response.json()['collection']['source'] == 'cache'
    assert len(collector.calls) == 1


@pytest.mark.parametrize('query', ['', '?term=', '?term=r/'])
async def test_get_posts_rejects_invalid_terms(env, query):
    client, *_ = env
    response = await client.get(f'/api/posts{query}')
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'INVALID_TERM'


# Static frontend serving


@pytest.fixture
def dist(tmp_path):
    (tmp_path / 'index.html').write_text('<!doctype html><title>Reddit Collector</title>')
    return tmp_path


async def static_client(static_dir):
    clock = FakeClock()
    _, repository = memory_repository(clock)
    app = build_app(
        repository=repository,
        collector=FakeCollector(),
        clock=clock,
        config=load_config({}),
        static_dir=static_dir,
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


async def test_serves_the_built_page_and_client_routes(dist):
    async with await static_client(dist) as client:
        assert 'Reddit Collector' in (await client.get('/')).text
        assert '<title>' in (await client.get('/some/page')).text


async def test_unknown_api_routes_are_json_404s(dist):
    async with await static_client(dist) as client:
        response = await client.get('/api/nope')
        assert response.status_code == 404
        assert response.json() == {'message': 'Not found'}


async def test_starts_without_static_serving_when_the_build_is_missing(dist):
    async with await static_client(dist / 'missing') as client:
        assert (await client.get('/')).status_code == 404


async def test_files_outside_the_build_folder_are_never_served(tmp_path):
    root = tmp_path / 'dist'
    root.mkdir()
    (root / 'index.html').write_text('<title>Reddit Collector</title>')
    (tmp_path / 'secret.txt').write_text('do-not-serve')
    async with await static_client(root) as client:
        for path in ('/..%2Fsecret.txt', '/%2E%2E/secret.txt', '/../secret.txt'):
            response = await client.get(path)
            assert 'do-not-serve' not in response.text
