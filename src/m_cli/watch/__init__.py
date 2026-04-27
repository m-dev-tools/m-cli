"""m watch — re-run M test suites on file changes.

Tier 1, Step 5 of the M ecosystem gap-remediation plan
(see docs/m-tooling-tier1.md in the m-tools repo).

Polls watched paths at a fixed interval and re-runs affected suites
when ``.m`` files change. Affinity rule: source ``foo.m`` maps to suite
``FOOTST.m`` (uppercased name + ``TST``); when no match is found, every
discovered suite is re-run. Suite-file edits re-run only that suite.

The polling design keeps the dependency footprint small — no inotify or
``watchdog`` — at the cost of up to ``--interval`` seconds of latency.
"""

from m_cli.watch.affinity import resolve_affinity
from m_cli.watch.cli import watch_command
from m_cli.watch.poller import Poller

__all__ = ["watch_command", "Poller", "resolve_affinity"]
