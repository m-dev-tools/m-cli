"""Exit-code vocabulary per CLI-UX guide §3.7.

Three values, three meanings:

- ``SUCCESS`` (0)         — normal completion.
- ``DOMAIN_FAILURE`` (1)  — the command was invoked correctly but the
  underlying work failed: missing manifest, missing ydb binary,
  no matches, compile error, lint findings above threshold.
- ``USAGE_ERROR`` (2)     — the user invoked the command wrong: unknown
  flag, missing required positional, malformed argument value.
  Reserved for argparse-level errors.

The dispatcher routes argparse failures to exit 2 via ``ArgumentParser.error``
(unchanged). Leaf handlers return one of the constants below explicitly.
"""

from __future__ import annotations

SUCCESS = 0
DOMAIN_FAILURE = 1
USAGE_ERROR = 2
