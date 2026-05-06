"""VistA Kernel auto-defined locals — allowlist for M-MOD-024.

The VistA Kernel auto-initialises a known set of process-scoped local
variables at session/routine entry. Static reaching-defs analysis
(M-MOD-024) cannot see Kernel's init because it lives in another
routine and is invoked by Kernel's session-startup machinery, not
by every routine itself. Lint findings on these names are therefore
false positives in any VistA context.

Rules consult :data:`KERNEL_AUTO_DEFINED` when the active config has
``[lint.vista] kernel_locals = "default"`` (or the list is left
empty), and consult the user-supplied list when an override is
provided.

References:
  - VA Kernel Programmer's Guide ch. 7 — "Programmer Environment"
  - ZTRTL globals — Kernel TaskMan task variables
  - DBA SAC §3.3 — universally-set variables
"""

from __future__ import annotations

# Order: stable name first, then the documented family it belongs to.
# Each entry is the bare local name as it appears at use site.
KERNEL_AUTO_DEFINED: tuple[str, ...] = (
    # The universal field separator — Kernel sets to $C(94) at every
    # routine entry. By far the most common false-positive source.
    "U",
    # Device-handling locals (Kernel session)
    "IO",
    "IOM",
    "IOSL",
    "IOST",
    "IOST(0)",
    "IOF",
    "IOXY",
    "IOBS",
    "IOTM",
    "IOTBL",
    "IOSC",
    # Date/time (Kernel + FileMan, set at sign-on)
    "DT",
    "DTIME",
    # User identity (Kernel sign-on) — flow analysis sees bare name
    # (subscript references are caught by the same allowlist when
    # the analyzer tracks the array root)
    "DUZ",
    # Environment / namespace
    "%UCI",
    "%H",
    "%XQDIC",
    "%ZIS",
    "%ZTOS",
    "%ZTSCH",
    "%ZTLOAD",
    # TaskMan task variables
    "ZTQUEUED",
    "ZTSK",
    "ZTREQ",
    "ZTSTOP",
    "ZTIO",
    "ZTDESC",
    "ZTDTH",
    "ZTRTN",
    "ZTSAVE",
    "ZTUCI",
    "ZTVOL",
    # XQ option/menu system
    "XQXFLG",
    "XQY",
    "XQY0",
    "XQT0",
    "XQT1",
    "XQOPTKEY",
    "XQOPT",
    # XM (MailMan)
    "XMC",
    "XMINSTR",
    "XMDUZ",
    "XMSUB",
    "XMTEXT",
    "XMY",
    "XMZ",
)
# ^DIR / ^DIC convention writes back into Y / X / DTOUT / DUOUT —
# those are NOT universal-entry locals (only defined post-call), so
# they intentionally are NOT in this list. Suppressing reads of them
# would mask real "use-before-call" bugs.


def is_kernel_auto_defined(name: str, allowlist: tuple[str, ...] = ()) -> bool:
    """Return True iff ``name`` is treated as auto-defined by Kernel.

    When ``allowlist`` is non-empty, it overrides the default list
    entirely — gives projects total control via
    ``[lint.vista] kernel_locals = ["U", "DT", ...]``.

    The empty tuple (default) means "use the built-in list".
    """
    pool = allowlist if allowlist else KERNEL_AUTO_DEFINED
    return name in pool
