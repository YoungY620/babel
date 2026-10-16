#!/usr/bin/env python3
"""Provider credential preflight: one cheap GET /models before any heavy work.

Invalid or missing credentials and unreachable providers abort the convert
cycle immediately instead of failing hours into ASR/TTS.
"""
import sys

import provider

TIMEOUT_SECONDS = 30


def check_provider():
    """Exit non-zero when the provider rejects the credential or is unreachable."""
    try:
        provider.request("models", timeout=TIMEOUT_SECONDS)
    except KeyError:
        print("provider preflight failed: OPENAI_API_KEY is not set; "
              "aborting before heavy work", file=sys.stderr)
        raise SystemExit(1) from None
    except RuntimeError as error:
        print(f"provider preflight failed: {error}; aborting before heavy work",
              file=sys.stderr)
        raise SystemExit(1) from None
    return True


if __name__ == "__main__":
    check_provider()
    print("provider preflight OK")
