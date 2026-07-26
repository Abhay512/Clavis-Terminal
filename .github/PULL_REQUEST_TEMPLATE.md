## What this changes

<!-- One or two sentences. What is different after this merges? -->

Closes #

## Why

<!-- The problem being solved. If there is an issue, the discussion can live there. -->

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Performance
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Tooling / CI / Docker

## How it was verified

<!-- Tick what you actually ran. -->

**Backend**
- [ ] `ruff check .` is clean
- [ ] `python -m compileall -q .` passes
- [ ] `python -m tests.test_oneway` passes
- [ ] Added or updated tests

**Dashboard**
- [ ] `npx tsc --noEmit` is clean
- [ ] `npm run build` succeeds
- [ ] Checked in a browser (screenshots below for visual changes)

**Other**
- [ ] Not applicable to this change

## Does this change what appears on a board?

- [ ] **No** — infrastructure, interface, docs or tooling only
- [ ] **Yes** — and I have filled in the section below

<details>
<summary>Required when a board's output changes</summary>

**Which recorded session did you replay?**

**What changed in the output — including what got worse?**

<!-- A change that only ever improves things usually has not been tested hard enough. -->

**Can the reason a signal fires still be read off the board at the moment it fires?**

</details>

## Screenshots

<!-- Before/after for anything visual. Delete this section otherwise. -->

## Checklist

- [ ] I read [CONTRIBUTING.md](../blob/main/CONTRIBUTING.md)
- [ ] No credentials, keys, tokens or recorded market data are in this diff
- [ ] No new runtime dependency, or I explained why it is needed above
- [ ] Commits are focused and conventionally prefixed
