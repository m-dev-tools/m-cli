"""VistA trusted-external-routines — allowlist for M-XINDX-007.

VistA depends on a known set of FileMan / Kernel / MailMan APIs that
are universally present in any VistA system but typically live
*outside* the source-controlled application packages. The ``%`` -
prefixed routines (``^%DT``, ``^%ZTLOAD``, etc.) live in the system
namespace, not under ``Packages/``. The non-``%`` Kernel APIs
(``^DIR``, ``^DIE``, ``^DD``) are part of FileMan, distributed
separately from any given VistA package.

Rule ``M-XINDX-007`` (call to undefined routine) flags every
reference to one of these as a fatal error because they aren't in
the workspace index. That's right behavior for a generic non-VistA
project but produces tens of thousands of false positives when
linting a VistA package.

Rules consult :data:`TRUSTED_ROUTINES` when the project opts in via
``[lint.vista] trusted_routines = "default"``, or supplies an
explicit list to override.

References:
  - VA Kernel Programmer's Guide
  - FileMan Programmer's Manual ch. 2 — "DIQ DIC DIE DIK DIR" APIs
  - VA SAC §3.4 — supported callable namespaces
"""

from __future__ import annotations

# Routine names WITHOUT the leading "^". Routines are matched by
# uppercase name so the allowlist is case-insensitive at lookup time.
TRUSTED_ROUTINES: tuple[str, ...] = (
    # FileMan core APIs (^%DT family + the DI* canonicals)
    "%DT", "%DTC", "%DTCH", "%RCR",
    "DI", "DIA", "DIB", "DIBT", "DIC", "DIC1", "DICATR",
    "DICATR1", "DICATR2", "DICN", "DICR", "DICRC", "DICRC1",
    "DICRW", "DICUIX", "DICUIX1", "DICUIX2",
    "DIE", "DIE1", "DIE2", "DIEZ", "DIE0", "DIET", "DIEM",
    "DIK", "DIK1", "DIKC", "DIKZ", "DIKZ1",
    "DILF", "DILFD", "DIM", "DIM1", "DIM2",
    "DIP", "DIP1", "DIPDR", "DIPM", "DIQ", "DIQ1", "DIR",
    "DIR0", "DIST", "DIU", "DIU1", "DIU2", "DIWP",
    # Kernel system services
    "%ZIS", "%ZISC", "%ZISH", "%ZISL", "%ZISP", "%ZISS", "%ZISTCP",
    "%ZTBKC", "%ZTLOAD", "%ZTLOAD1", "%ZTLOAD2", "%ZTM", "%ZTMG",
    "%ZTPP", "%ZTSCH", "%ZTUL", "%ZTER", "%ZTERH",
    "%ZOSV", "%ZOSF", "%ZOSV1",
    # XLF / Kernel utility libraries (eXtensible Library Functions)
    "XLFDT", "XLFDT1", "XLFDT2", "XLFSTR", "XLFNAME", "XLFNAME2",
    "XLFNUM", "XLFMTH", "XLFCRC", "XLFSHAN", "XLFCRC1", "XLFHEX",
    "XLFUTL",
    # XU* — Kernel XUS sign-on / security
    "XUS", "XUS1", "XUSCLEAN", "XUSER", "XUSERAU", "XUSPSET",
    "XUSESIG", "XUSRB", "XUSRB1", "XUSRB2",
    # XPD — KIDS package distribution
    "XPDIQ", "XPDUTL", "XPDUTL1", "XPDIQ1", "XPDIA", "XPDIE",
    "XPDIJ", "XPDR", "XPDRSUM", "XPDIE1",
    # XQ — option/menu system
    "XQ12", "XQAL", "XQALERT", "XQALSURO", "XQH", "XQOR",
    "XQOR1", "XQDATE", "XQDIC", "XQOPTKEY",
    # XM — MailMan
    "XMA", "XMA1", "XMA1A", "XMA1B", "XMA2", "XMA21", "XMA3",
    "XMA4", "XMA8", "XMA9", "XMAA", "XMAB", "XMAH", "XMAS",
    "XMC", "XMC1", "XMD", "XMDIQ", "XMG", "XMG1", "XMJBD",
    "XMJBM", "XMJMF", "XMJMG", "XMJMH", "XMJMI", "XMS",
    "XMS1", "XMSE", "XMTRD", "XMV", "XMVUP", "XMX", "XMXAPI",
    "XMXAPIB", "XMXAPIG", "XMXAPIS", "XMXAPIU", "XMY",
    # XB — XBLM / Kernel utilities (the older API)
    "XBLM", "XBNEW", "XBHANDLR", "XBHCLE",
    # FileMan word-processing
    "DIWE", "DIWE1", "DIWE2", "DIWEDT",
    # Statistics / global tools
    "%G", "%GL", "%GS", "%GE", "%GD",
    # Miscellaneous historically-essential
    "%DH", "%DTC1",
)


def is_trusted_routine(routine: str, allowlist: tuple[str, ...] = ()) -> bool:
    """Return True iff ``routine`` is treated as a known external API.

    Comparison is case-insensitive; ``routine`` should NOT carry the
    leading ``^``. When ``allowlist`` is non-empty, it overrides the
    default list entirely.
    """
    pool = allowlist if allowlist else TRUSTED_ROUTINES
    target = routine.upper().lstrip("^")
    return target in {entry.upper().lstrip("^") for entry in pool}
