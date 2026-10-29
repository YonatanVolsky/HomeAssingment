from app.contracts import CollectionResponse, CollectionSummary, Post


def test_post_serializes_with_camel_case_keys():
    post = Post(
        id='t3_a',
        title='Hello',
        author=None,
        comment_count=3,
        score=-1,
        created_at='2026-10-29T10:00:00.000Z',
        permalink='https://www.reddit.com/r/x/comments/a/',
        subreddit='x',
        preview_text=None,
        flair='Question',
    )

    assert post.model_dump(by_alias=True) == {
        'id': 't3_a',
        'title': 'Hello',
        'author': None,
        'commentCount': 3,
        'score': -1,
        'createdAt': '2026-10-29T10:00:00.000Z',
        'permalink': 'https://www.reddit.com/r/x/comments/a/',
        'subreddit': 'x',
        'previewText': None,
        'flair': 'Question',
    }


def test_collection_response_serializes_nested_models():
    summary = CollectionSummary(
        id=1, term='x', source='cache', collected_at='2026-10-29T10:00:00.000Z', post_count=0
    )
    body = CollectionResponse(collection=summary, posts=[]).model_dump(by_alias=True)

    assert body == {
        'collection': {
            'id': 1,
            'term': 'x',
            'source': 'cache',
            'collectedAt': '2026-10-29T10:00:00.000Z',
            'postCount': 0,
        },
        'posts': [],
    }
