"""Daily Kite Connect login flow; writes the access token to .env."""
from __future__ import annotations

import logging
import sys

from kiteconnect import KiteConnect

import config

log = logging.getLogger("auth")


def _is_network_error(e: Exception) -> bool:
    """True when the exception looks like a transport failure, not a bad token."""
    try:
        import requests
        if isinstance(e, (requests.exceptions.ConnectionError,
                          requests.exceptions.Timeout)):
            return True
    except Exception:
        pass
    name = type(e).__name__.lower()
    if any(s in name for s in ("timeout", "connection", "network")):
        return True
    msg = str(e).lower()
    return any(s in msg for s in ("timed out", "timeout", "connection",
                                  "unreachable", "max retries", "handshake",
                                  "temporarily unavailable", "read timed out"))


def get_kite(interactive: bool = True) -> KiteConnect:
    """Return an authenticated KiteConnect client.

    Tries the saved access token first; if invalid and ``interactive``,
    walks through the request_token exchange and persists the new token.
    """
    env = config.load_env()
    api_key = env.get("KITE_API_KEY", "")
    api_secret = env.get("KITE_API_SECRET", "")
    if not api_key or not api_secret:
        raise RuntimeError(
            f"KITE_API_KEY / KITE_API_SECRET missing in {config.ENV_FILE}"
        )

    kite = KiteConnect(api_key=api_key)

    access_token = env.get("KITE_ACCESS_TOKEN", "")
    if access_token:
        kite.set_access_token(access_token)
        try:
            profile = kite.profile()
            log.info("Token valid - logged in as %s", profile["user_name"])
            return kite
        except Exception as e:
            if not interactive and _is_network_error(e):
                raise ConnectionError(
                    f"Kite unreachable during token check (token may still be "
                    f"valid): {e}") from e
            log.info("Saved access token is expired/invalid.")

    if not interactive:
        raise RuntimeError(
            "Access token invalid and interactive login disabled. "
            "Run `python auth.py` first."
        )

    print("\n--- Kite daily login ---")
    print("1. Open this URL in your browser and log in:")
    print(f"   {kite.login_url()}")
    print("2. After login you land on your redirect URL. Copy the")
    print("   `request_token` query parameter from that URL.\n")
    request_token = input("Paste request_token here: ").strip()
    if not request_token:
        print("No request_token given, aborting.")
        sys.exit(1)

    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]
    kite.set_access_token(access_token)
    config.save_env_value("KITE_ACCESS_TOKEN", access_token)

    profile = kite.profile()
    print(f"\nLogin OK - welcome {profile['user_name']}.")
    print(f"Access token saved to {config.ENV_FILE}")
    return kite


if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL, format="%(levelname)s %(message)s")
    get_kite(interactive=True)
