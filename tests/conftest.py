import sys
from pathlib import Path

import pytest

# Make src/ importable without requiring `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(autouse=True)
def _stub_engine_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub `read_connection` in every runner/coverage/cli module that
    imports it, so tests don't need a vista-meta `conn.env` on disk.

    The four affected modules each do
    ``from m_cli.engine import read_connection`` at module load —
    those are independent name bindings, so patching only
    `m_cli.engine.read_connection` is not enough; each module-level
    binding must be patched in turn.

    Tests in ``test_engine_transports.py`` exercise the engine
    resolver directly via the `m_cli.engine` namespace and are not
    affected by these patches.

    Returns a junk SSHEngine. Callers that go through the SSH command
    builder still get a syntactically valid command list; the canned
    `_default_runner` fakes installed per-test discard it. The four
    target modules:

      - m_cli.test.runner          (run_suite / run_case)
      - m_cli.test.cli             (m test entrypoint)
      - m_cli.coverage.runner      (m coverage runner)
      - m_cli.coverage.cli         (m coverage entrypoint)
    """
    from m_cli.engine import SSHEngine

    stub = SSHEngine(host="ci-stub", ssh_port=22, ssh_user="ci-stub")

    def _stub(*args, **kwargs):
        return stub

    for mod_path in (
        "m_cli.test.runner",
        "m_cli.test.cli",
        "m_cli.coverage.runner",
        "m_cli.coverage.cli",
    ):
        try:
            monkeypatch.setattr(f"{mod_path}.read_connection", _stub)
        except AttributeError:
            # Module doesn't bind `read_connection` (e.g. future
            # refactor moves the import); ignore.
            pass

    # Also stub `seed_for_paths` — it's the SSH/SCP staging entry point
    # called by `m test` and `m coverage` to upload .m files to the
    # remote engine. Tests fake the actual subprocess runner downstream
    # of this; without stubbing, the staging step real-SSHes to the
    # ci-stub host and fails. Returning an empty mapping is safe — it
    # represents "no remote staging happened" and downstream callers
    # (run_suite / run_case) only consult the mapping for path
    # translation, which the per-test `_default_runner` fakes don't
    # exercise.
    def _stub_seed(paths, conn=None):
        return {}

    for mod_path in ("m_cli.test.cli", "m_cli.coverage.cli"):
        try:
            monkeypatch.setattr(f"{mod_path}.seed_for_paths", _stub_seed)
        except AttributeError:
            pass
