# Term protocols: a swappable normalizer

Date: 2026-10-31. Status: approved in conversation, awaiting review of this spec.

## Goal

The rules that turn a user's term into a normalized query can be swapped without changing
the normalizer. Which rule set is active is decided where the app is composed, from
configuration, so whoever runs the app (Docker or similar) picks it at deploy time. Only
today's rules are implemented, as the single protocol `reddit-subreddit`; adding a protocol
later means writing new steps and one new preset, nothing else.

Behaviour for users does not change: the same inputs are accepted, rejected inputs get the
same `INVALID_TERM` error (HTTP 400, "Enter a subreddit name like r/ubisoft."), and the
frontend and database are untouched.

## Decisions

| Question | Decision |
|---|---|
| What is a protocol? | All layers together: the input formats accepted, the target's naming rule, and the kind of query the result is. |
| Structure | A protocol is an ordered chain of small step functions (option C); the normalizer runs whatever chain it is given. |
| Who selects it | The composition code (`collector/factory.py`), from the `TERM_PROTOCOL` setting. Not detected per request. |
| What config can choose | A named preset only. Chains are defined in code, so every selectable chain is tested. |
| Protocols implemented | `reddit-subreddit` only (today's rules). |
| Is the kind stored? | No. The database stores posts in the existing structure only. |
| Where does the kind live? | On the protocol only. It is a startup constant, used once to check the collector can serve it; the normalized result is a plain string. |

## Components

New package `backend/app/terms/`:

### `normalizer.py`

```python
Step = Callable[[str], str]   # returns the transformed text or raises AppError('INVALID_TERM')

@dataclass(frozen=True)
class TermProtocol:
    name: str
    kind: str     # what a normalized term refers to, e.g. 'subreddit'
    steps: tuple[Step, ...]

class TermNormalizer:
    def __init__(self, protocol: TermProtocol) -> None: ...
    @property
    def kind(self) -> str: ...
    def normalize(self, raw: str) -> str: ...
```

`normalize` passes the raw term through each step in order, raises `INVALID_TERM` if the
result is empty, and returns the text. It contains nothing specific to Reddit and never
catches errors from steps.

The kind is declared on the protocol, not set by a step, so every protocol has one. It is
fixed for the life of the process, so results do not carry it; it is read once, at startup,
for the collector check.

### `steps.py`

Each step does one thing. Parameterized rules are factories that return a step.

| Step | Behaviour |
|---|---|
| `trim` | Strips surrounding whitespace |
| `extract_reddit_link` | If the text is a link on `reddit.com` or a subdomain (with or without `http(s)://`), returns the first path segment after `/r/`, or raises `INVALID_TERM` when there is none. Other text passes through unchanged. The host must end at `reddit.com` (`reddit.com.evil.com` is not a link) |
| `strip_r_prefix` | Removes one leading `r/` or `/r/`, any case |
| `strip_trailing_slash` | Removes one trailing `/` |
| `require_pattern(regex)` | Raises `INVALID_TERM` unless the whole text matches |
| `lowercase` | Lowercases |

### `presets.py`

```python
SUBREDDIT_NAME = r'[A-Za-z0-9_]{2,21}'   # comment on legacy 2-letter names kept

PRESETS = {
    'reddit-subreddit': TermProtocol(
        name='reddit-subreddit',
        kind='subreddit',
        steps=(trim, extract_reddit_link, strip_r_prefix, strip_trailing_slash,
               require_pattern(SUBREDDIT_NAME), lowercase),
    ),
}
DEFAULT_PRESET = 'reddit-subreddit'
```

This chain reproduces `normalize_term` exactly, including the existing asymmetry: in a link
the path after the name is ignored (`reddit.com/r/ubisoft/new` → `ubisoft`), while for a bare
term it makes the term invalid (`r/ubisoft/new` is rejected). Fixing that asymmetry is a
separate change.

## Wiring

- **`config.py`**: a new `TERM_PROTOCOL` setting, default `reddit-subreddit`, exposed as
  `Config.term_protocol`. A name not in `PRESETS` fails `load_config` with
  `Invalid configuration: TERM_PROTOCOL: ...`, so the app does not start.
- **Collectors** declare which kinds they serve: a `supported_kinds: frozenset[str]` attribute
  on the `Collector` protocol. `RedditCollector`, `FixtureCollector` and the tests' `FakeCollector`
  declare `{'subreddit'}`.
- **`collector/factory.py`** (the composition point) gains
  `create_term_normalizer(config, collector) -> TermNormalizer`. It looks up the preset and
  raises `ConfigError` if `collector.supported_kinds` does not contain the preset's kind,
  so a mismatched deployment fails at startup, not on the first search.
- **`main.py`** builds the normalizer and passes it to `build_app`.
- **`api.py`**: `build_app` takes a `normalizer` argument and hands it to
  `CollectionService`. The 1 KB body limit and 200-character limit stay in the API layer,
  because they apply whatever the protocol.
- **`services/collection_service.py`** receives the normalizer as a constructor argument and
  stops importing `normalize_term`. In `collect`, `last_good` and `get_posts` it calls
  `normalizer.normalize(term)` where it called `normalize_term(term)`, so the repository and
  collector interfaces are unchanged.
- **`collector/normalize_term.py`** is deleted. Its tests move to the new package.

## Error handling

Every rejection is `AppError('INVALID_TERM')`, raised by a step or by the normalizer's empty
check; no new error codes or messages. Configuration problems (unknown preset, kind not
served by the collector) are `ConfigError`, reported at startup in the existing format.

## Testing (written before the code)

- **Steps**: each step on its own, including links without `/r/`, a host that only starts with
  `reddit.com`, and text that should pass through unchanged.
- **Normalizer**: with a protocol defined inside the test (for example: trim, uppercase,
  kind `test`), proving a different chain works without changing the normalizer; the
  empty-result check; errors from steps pass through.
- **Behaviour preserved**: the existing 10 accepted and 10 rejected cases from
  `test_collector_helpers.py`, plus `reddit.com/r/ubisoft/new` → `ubisoft` and
  `r/ubisoft/new` → rejected, run against the `reddit-subreddit` preset.
- **Config**: default value, an explicit valid value, an unknown value rejected.
- **Factory**: builds the preset's normalizer; refuses a collector without the preset's kind.
- **Service and API**: existing tests pass with the injected normalizer; no behaviour
  change in `test_api.py` or `test_service.py`.
- Full suite, lint, compliance and secret checks green before committing.

## Documentation

- README configuration table and `.env.example`: `TERM_PROTOCOL`.
- DESIGN.md: the decision (protocol chain chosen at composition time) and the known limitation
  below.
- docs/HANDOFF.md: the change and the new package.

## Known limitation

The database keys stored runs by the normalized term only. If the protocol of a deployment
is switched while keeping the same database file, a run stored under the old protocol for
the same term can be served from the cache (within `COLLECTION_TTL_SECONDS`) or as the
restored feed. Use a separate `DB_PATH` per protocol, as fixture mode already does. With one
protocol this cannot happen.

## Out of scope

- Any second protocol, search, or change to the collector's requests.
- Per-request protocol selection, and configuring a chain step by step.
- A `kind` column or any other database change.
- Showing protocol-specific hint text in the UI.
