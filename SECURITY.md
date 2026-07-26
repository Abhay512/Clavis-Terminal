# Security Policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report privately through GitHub:
**[Report a vulnerability](https://github.com/Abhay512/Clavis-Terminal/security/advisories/new)**

Please include what the issue is, how to reproduce it, and what an attacker could do with it.
You will get an acknowledgement within a few days, and credit in the fix unless you would rather
not be named.

## Supported versions

The `main` branch is the supported version. Fixes land there.

## Scope

This project handles broker API credentials and streams live market data, so the things worth
reporting are:

| In scope | Examples |
|:--|:--|
| **Credential exposure** | any path by which `KITE_API_KEY`, `KITE_API_SECRET` or an access token could be written to a log, a tracked file, an HTTP response, a container image layer or an error message |
| **The API surface** | unauthenticated access to data that should not be public, injection through any endpoint, WebSocket resource exhaustion |
| **Storage** | SQL injection into the SQLite store, path traversal through instrument or symbol names |
| **Dependencies** | a known CVE in something we pin, with a plausible path to exploitation here |
| **Container** | anything in the images that leaks host state or ships a secret |

**Out of scope:** the trading logic being unprofitable, threshold values being suboptimal, and
the deliberate omission of the production decision engine. Those are design decisions, documented
in the README.

## Deployment notes for operators

This is a local-first application and the defaults assume that.

- **The API has no authentication and CORS is fully open.** That is deliberate for
  `localhost`, and it is unsafe on a public interface. If you expose port 8000 beyond your own
  machine, put it behind a reverse proxy with TLS and authentication.
- **Credentials live only in `backend/.env`**, which is git-ignored. `auth.py` writes the daily
  access token back to that file and nowhere else. Nothing is ever logged.
- **Never commit `.env`.** CI fails the build if a `.env` file or a credential-shaped literal
  appears anywhere in the tree — but do not rely on that as your only defence.
- **If a key is ever exposed, regenerate it** at [developers.kite.trade](https://developers.kite.trade/)
  before doing anything else. Access tokens expire daily on their own; the API key and secret do
  not.
- **The recorded data is yours.** `backend/data/` holds your session recordings and is
  git-ignored. Nothing in this project uploads it anywhere.
