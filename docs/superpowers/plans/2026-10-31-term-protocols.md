# Term Protocols Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `normalize_term` with a normalizer that runs a swappable chain of steps (a "protocol"), chosen at startup by the `TERM_PROTOCOL` setting, with no change in behaviour.

**Architecture:** A new package `backend/app/terms/` holds the steps, the generic `TermNormalizer`, and the named presets. The composition code (`collector/factory.py`) builds the normalizer from config; `main.py` passes it through `build_app` into `CollectionService`, which uses it where it called `normalize_term`. Collectors, repository, API contract, frontend and database do not change.

**Tech Stack:** Python 3.11+, pydantic v2 (config), pytest with anyio. Run from `backend/`.

**Spec:** `docs/superpowers/specs/2026-10-31-term-protocols-design.md`

## Global Constraints

- Every rejection is `AppError('INVALID_TERM')`; no new error codes or messages.
- `TERM_PROTOCOL` default: `reddit-subreddit`. An unknown value fails `load_config` with a message matching `Invalid configuration: .*TERM_PROTOCOL`.
- The `reddit-subreddit` preset accepts and rejects exactly what `normalize_term` does today, including `reddit.com/r/ubisoft/new` → `ubisoft` and `r/ubisoft/new` → rejected.
- Subreddit name pattern: `[A-Za-z0-9_]{2,21}`, keeping the existing comment about legacy two-letter names such as r/de.
- No database, collector, API-contract or frontend changes. No query kind anywhere.
- Test first for every task; Conventional Commit messages ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Before the last commit: `npm test`, `npm run lint`, `scripts/check-secrets.sh`, `scripts/check-compliance.sh` (from the repo root), all green.

## Review Focus

1. **A protocol with no steps** would return the raw term untrimmed and unvalidated. `TermProtocol` must refuse an empty `steps` tuple at construction (`ValueError`). Test in Task 1.
2. **The preset table is changed at runtime** by accident (it is module-level state). `PRESETS` must be read-only (`MappingProxyType`, as `ERROR_TABLE` is). Test in Task 2.
3. **`TERM_PROTOCOL` set to an empty string** (a blank line in a Docker env file) must fall back to the default, like every other setting. **Wrong case** (`Reddit-Subreddit`) is rejected, not guessed. Tests in Task 3.
4. **A step reordering that changes behaviour** (for example `lowercase` before `require_pattern`, or `strip_r_prefix` before `extract_reddit_link`) must be caught. The preserved-behaviour table in Task 2 includes `R/UBISOFT`, `/r/Ubisoft/` and an `old.reddit.com` link with a query string for this.
5. **The best-effort `last_good` path** must still swallow `INVALID_TERM` from the injected normalizer, rather than turning a failed collection into a 500. Test in Task 4.

---

### Task 1: Steps and the generic normalizer

**Files:**
- Create: `backend/app/terms/__init__.py` (empty), `backend/app/terms/steps.py`, `backend/app/terms/normalizer.py`
- Test: `backend/tests/test_terms.py`

**Interfaces:**
- Produces, in `app/terms/normalizer.py`:
  - `Step = Callable[[str], str]`
  - `@dataclass(frozen=True) class TermProtocol: name: str; steps: tuple[Step, ...]`. `__post_init__` raises `ValueError` if `steps` is empty.
  - `class TermNormalizer: __init__(self, protocol: TermProtocol)`; `normalize(self, raw: str) -> str`.
- Produces, in `app/terms/steps.py`: `trim`, `extract_reddit_link`, `strip_r_prefix`, `strip_trailing_slash`, `lowercase` (each `str -> str`) and `require_pattern(pattern: str) -> Step`.

- [ ] **Step 1: Write the failing tests** in `tests/test_terms.py`:
  - `test_trim_strips_surrounding_whitespace`: `trim('  a b  ') == 'a b'`.
  - `test_extract_reddit_link_takes_the_segment_after_r` (parametrized):
    - `https://www.reddit.com/r/Ubisoft/` → `Ubisoft`
    - `reddit.com/r/ubisoft/new` → `ubisoft`
    - `https://old.reddit.com/r/Ubisoft/new/?sort=new` → `Ubisoft`
    - `www.reddit.com/r/Ubisoft/comments/abc/x/` → `Ubisoft`
  - `test_extract_reddit_link_rejects_a_reddit_link_without_r` (parametrized `reddit.com`, `https://www.reddit.com/user/x`): raises `AppError` with code `INVALID_TERM`.
  - `test_extract_reddit_link_passes_other_text_through` (parametrized `ubisoft`, `r/ubisoft`, `https://reddit.com.evil.com/r/x`, `https://example.com/r/x`): returns its input unchanged.
  - `test_strip_r_prefix` (parametrized): `r/x` → `x`, `/R/x` → `x`, `x` → `x`, `xr/y` → `xr/y`.
  - `test_strip_trailing_slash`: `x/` → `x`, `x` → `x`, `x//` → `x/` (one slash only).
  - `test_require_pattern_matches_the_whole_text`: `require_pattern('[a-z]{2}')('ab') == 'ab'`; `'abc'` and `'a'` raise `INVALID_TERM`.
  - `test_lowercase`: `lowercase('AbC') == 'abc'`.
  - `test_normalizer_runs_the_steps_in_order`: protocol `TermProtocol('test', (trim, str.upper, lambda t: t + '!'))`; `normalize('  ab ') == 'AB!'`. This proves a different chain needs no normalizer change.
  - `test_normalizer_rejects_an_empty_result`: protocol `(trim,)`; `normalize('   ')` raises `INVALID_TERM`.
  - `test_normalizer_lets_step_errors_through`: a step raising `AppError('INVALID_TERM')` propagates the same object (`raised.value is error`).
  - `test_a_protocol_needs_at_least_one_step`: `TermProtocol('x', ())` raises `ValueError`.

- [ ] **Step 2: Run the tests and check they fail**

  Run: `.venv/bin/pytest tests/test_terms.py -q`
  Expected: collection error, `ModuleNotFoundError: No module named 'app.terms'`.

- [ ] **Step 3: Implement `steps.py` and `normalizer.py`**

  Port the regexes from `app/collector/normalize_term.py` unchanged: the `_URL_LIKE` pattern, the `https://` prefixing before `urlparse`, and `^/r/([^/]+)` on the path. `strip_r_prefix` uses `^/?r/` (case-insensitive) once; `strip_trailing_slash` uses `/$` once. `require_pattern` compiles once and uses `fullmatch`. A rejection is `AppError('INVALID_TERM')`. The module docstring says each step is one transformation, `str -> str`, or an `INVALID_TERM` rejection.

- [ ] **Step 4: Run the tests and check they pass**

  Run: `.venv/bin/pytest tests/test_terms.py -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  ```bash
  git add app/terms tests/test_terms.py
  git commit -m "feat(terms): add normalization steps and a generic step-chain normalizer"
  ```

### Task 2: The `reddit-subreddit` preset

**Files:**
- Create: `backend/app/terms/presets.py`
- Test: `backend/tests/test_terms.py` (append)

**Interfaces:**
- Consumes: Task 1's `TermProtocol`, `TermNormalizer` and the steps.
- Produces: `SUBREDDIT_NAME = r'[A-Za-z0-9_]{2,21}'`; `DEFAULT_PRESET = 'reddit-subreddit'`; `PRESETS: Mapping[str, TermProtocol]`, read-only (`MappingProxyType`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_terms.py`), each using `TermNormalizer(PRESETS['reddit-subreddit'])`:
  - `test_reddit_subreddit_accepts`: the 10 accepted cases from `tests/test_collector_helpers.py:18-34`, copied verbatim, plus `('reddit.com/r/ubisoft/new', 'ubisoft')` and `('www.reddit.com/r/Ubisoft/comments/abc/some_post/', 'ubisoft')`.
  - `test_reddit_subreddit_rejects`: the 10 rejected cases from `tests/test_collector_helpers.py:37-55`, copied verbatim, plus `r/ubisoft/new`, `https://reddit.com.evil.com/r/x`, `reddit.com`, `u/someone`, `ubisöft`. Each raises `INVALID_TERM`.
  - `test_the_default_preset_exists`: `DEFAULT_PRESET in PRESETS` and `PRESETS[DEFAULT_PRESET].name == DEFAULT_PRESET`.
  - `test_presets_are_read_only`: `PRESETS['x'] = ...` raises `TypeError`.

- [ ] **Step 2: Run the tests and check they fail**

  Run: `.venv/bin/pytest tests/test_terms.py -q`
  Expected: `ImportError` for `app.terms.presets`.

- [ ] **Step 3: Implement `presets.py`**

  The steps, in this order: `trim, extract_reddit_link, strip_r_prefix, strip_trailing_slash, require_pattern(SUBREDDIT_NAME), lowercase`. Move the legacy-name comment from `normalize_term.py` onto `SUBREDDIT_NAME`.

- [ ] **Step 4: Run the tests and check they pass**

  Run: `.venv/bin/pytest tests/test_terms.py -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  ```bash
  git add app/terms/presets.py tests/test_terms.py
  git commit -m "feat(terms): add the reddit-subreddit preset reproducing today's rules"
  ```

### Task 3: `TERM_PROTOCOL` setting and the factory

**Files:**
- Modify: `backend/app/config.py` (the `Config` dataclass, `_Env`, `load_config`)
- Modify: `backend/app/collector/factory.py`
- Test: `backend/tests/test_config.py`, `backend/tests/test_collector.py` (next to the existing `create_collector` tests near line 350)

**Interfaces:**
- Consumes: Task 2's `PRESETS`, `DEFAULT_PRESET`; Task 1's `TermNormalizer`.
- Produces: `Config.term_protocol: str`; `create_term_normalizer(config: Config) -> TermNormalizer` in `app/collector/factory.py`.

- [ ] **Step 1: Write the failing tests**
  - In `test_applies_defaults_when_the_environment_is_empty`: add `assert config.term_protocol == 'reddit-subreddit'`.
  - `test_accepts_a_known_term_protocol`: `load_config({'TERM_PROTOCOL': 'reddit-subreddit'}).term_protocol == 'reddit-subreddit'`.
  - `test_an_empty_term_protocol_falls_back_to_the_default`: `load_config({'TERM_PROTOCOL': ''}).term_protocol == 'reddit-subreddit'`.
  - Add `({'TERM_PROTOCOL': 'nope'}, 'TERM_PROTOCOL')` and `({'TERM_PROTOCOL': 'Reddit-Subreddit'}, 'TERM_PROTOCOL')` to the parametrize list of `test_rejects_invalid_values_with_a_message_naming_the_variable`.
  - In `test_collector.py`, `test_create_term_normalizer_uses_the_configured_preset`: `create_term_normalizer(load_config({})).normalize('r/Ubisoft') == 'ubisoft'`.

- [ ] **Step 2: Run the tests and check they fail**

  Run: `.venv/bin/pytest tests/test_config.py tests/test_collector.py -q`
  Expected: `AttributeError: ... 'term_protocol'` and an `ImportError` for `create_term_normalizer`.

- [ ] **Step 3: Implement**
  - `_Env.TERM_PROTOCOL: str = DEFAULT_PRESET`, plus a `field_validator` raising `ValueError(f'must be one of: {", ".join(PRESETS)}')` when the value is not in `PRESETS`. The existing error formatting then names the variable.
  - `Config.term_protocol: str`, set in `load_config`.
  - `create_term_normalizer(config)` returns `TermNormalizer(PRESETS[config.term_protocol])`.

- [ ] **Step 4: Run the tests and check they pass**

  Run: `.venv/bin/pytest tests/test_config.py tests/test_collector.py -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  ```bash
  git add app/config.py app/collector/factory.py tests/test_config.py tests/test_collector.py
  git commit -m "feat(config): select the term protocol with TERM_PROTOCOL"
  ```

### Task 4: Inject the normalizer and remove `normalize_term`

**Files:**
- Modify: `backend/app/services/collection_service.py` (constructor; lines 39, 57, 66)
- Modify: `backend/app/api.py` (`build_app` signature, the `CollectionService(...)` call)
- Modify: `backend/app/main.py` (`create_app_from_env`)
- Modify: `backend/tests/helpers.py` (add `make_normalizer()`), `backend/tests/test_service.py` (fixture), `backend/tests/test_api.py` (the `env` fixture and `static_client`)
- Delete: `backend/app/collector/normalize_term.py`; the `normalize_term` section of `backend/tests/test_collector_helpers.py` (lines 12 and 15-55)

**Interfaces:**
- Consumes: Task 1's `TermNormalizer`; Task 3's `create_term_normalizer(config)`.
- Produces:
  - `CollectionService.__init__(..., normalizer: TermNormalizer, ...)` (keyword-only, like the others);
  - `build_app(*, repository, collector, normalizer: TermNormalizer, clock, config, static_dir=None)`;
  - `tests.helpers.make_normalizer() -> TermNormalizer`, the default preset.

- [ ] **Step 1: Write the failing tests**
  - Add `make_normalizer()` to `tests/helpers.py`, and pass `normalizer=make_normalizer()` in the `test_service.py` fixture and in both `build_app` calls in `test_api.py`.
  - `test_service.py`, new test `test_uses_the_injected_normalizer`: a normalizer from `TermProtocol('test', (trim, lambda t: 'fixed'))`; `await service.collect('anything', force=False)`; assert `collector.calls == [('fixed', 25)]`.
  - `test_service.py`, new test `test_last_good_returns_none_for_an_invalid_term`: `service.last_good('bad name!') is None`.

- [ ] **Step 2: Run the tests and check they fail**

  Run: `.venv/bin/pytest tests/test_service.py tests/test_api.py -q`
  Expected: `TypeError: ... unexpected keyword argument 'normalizer'`.

- [ ] **Step 3: Implement**
  - The service stores the normalizer and calls `self._normalizer.normalize(term)` at the three call sites; it drops the `normalize_term` import.
  - `build_app` passes `normalizer` through.
  - `main.create_app_from_env` builds it with `create_term_normalizer(config)`.
  - Delete `app/collector/normalize_term.py` and the old test section; the same cases now live in `test_terms.py`.

- [ ] **Step 4: Run the full suite and checks**

  Run, from the repo root:

  ```bash
  npm test
  npm run lint
  scripts/check-secrets.sh
  scripts/check-compliance.sh
  grep -rn normalize_term backend/app backend/tests
  ```

  Expected: every test passes, lint is clean, both checks print OK, and the grep finds nothing.

- [ ] **Step 5: Commit**

  ```bash
  git add -A backend
  git commit -m "refactor(service): inject the term normalizer; remove normalize_term"
  ```

### Task 5: Documentation

**Files:**
- Modify: `README.md` (configuration table; the project-layout block gets `app/terms/`), `.env.example`, `DESIGN.md` (Decisions; Known limitations), `docs/HANDOFF.md` ("Where things stand"; "Decisions")

- [ ] **Step 1: Write the documentation**
  - README configuration table: a row `TERM_PROTOCOL` | `reddit-subreddit` | "Rules for turning the search term into a subreddit name; only `reddit-subreddit` exists".
  - `.env.example`: `TERM_PROTOCOL=reddit-subreddit`, with a one-line comment.
  - DESIGN.md decision: "term rules are a chain of steps (a protocol), chosen at startup".
  - DESIGN.md known limitation, copied from the spec's "Known limitation" section: switching the protocol on the same `DB_PATH` can serve another protocol's cached run.
  - HANDOFF.md: the new package and the fact that the command layer is next.

- [ ] **Step 2: Check**

  Run: `scripts/check-secrets.sh` (from the repo root).
  Expected: OK.

- [ ] **Step 3: Commit**

  ```bash
  git add README.md .env.example DESIGN.md docs/HANDOFF.md
  git commit -m "docs: document TERM_PROTOCOL and the term-protocol design"
  ```
