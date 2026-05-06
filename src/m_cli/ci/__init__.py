"""m ci — CI scaffolding.

`m ci init` writes a GitHub Actions workflow that runs the four
project gates (`m fmt --check`, `m lint --error-on=fatal`, `m test`,
`m coverage --format=lcov`) on every push and pull request.

Reuses the template-emitter pattern introduced for `m new`.
"""

from m_cli.ci.cli import ci_command
from m_cli.ci.scaffold import render_workflow

__all__ = ["ci_command", "render_workflow"]
