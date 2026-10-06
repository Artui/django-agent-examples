"""The TypeScript readiness job closes its issue once no app is blocked.

`typescript-next-major` in `.github/workflows/upstream-drift.yml` asks a
question every week and files the answer in one issue. For as long as an app
is blocked, that issue is the right place for the answer; once none is, an
issue left open is one nobody can tell is current, and the `ignore` entries it
exists to retire stay in `.github/dependabot.yml` with nothing saying they can
go. So the job has two issue steps and one output choosing between them: open
or update the issue while the answer is no, close it once it is yes.

These tests sit beside the backend's because the gallery has no other place
for tests about its own CI, and the backend suite is the one `tests.yml` runs
on every pull request. The drift workflow itself runs only on its schedule, so
a change that broke its close path would merge green and be found months later.

The workflow is read as text rather than parsed: the checks are about which
strings the job's block contains, and no YAML parser is declared here. The one
exception is the report script, which is executed, because whether the issue
closes is decided by what that script computes and a string match cannot say
what a guard evaluates to.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "upstream-drift.yml"

_JOB = "typescript-next-major"

# The issue reports on main, so only a run on main may file or clear it. A
# dispatch from a branch is then a trial that touches no issue; without this, a
# branch that unblocked an app would close the issue before the change landed.
_ON_MAIN = "github.ref == 'refs/heads/main'"

# The step output both issue steps read. Two named values rather than "true or
# anything else", so a run that never wrote the output touches the issue in
# neither direction.
_ADOPTABLE = "steps.report.outputs.adoptable"


def _job() -> str:
    """The text of the readiness job's block."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z][a-z0-9-]*):\n", body, flags=re.MULTILINE)
    block = dict(zip(parts[1::2], parts[2::2], strict=True))[_JOB]
    # Guards the parse: a split that found the wrong block would pass the
    # negative assertions below without reading the job at all.
    assert "issues.create(" in block
    return block


def _steps(block: str) -> list[str]:
    return re.split(r"^      - ", block, flags=re.MULTILINE)[1:]


def _the_step(marker: str) -> str:
    """The one step in the job whose text contains `marker`."""
    found = [step for step in _steps(_job()) if marker in step]
    assert len(found) == 1, f"{len(found)} steps in {_JOB} contain {marker!r}"
    return found[0]


def _condition(step: str) -> str | None:
    match = re.search(r"^        if: (.+)$", step, re.MULTILINE)
    return match.group(1) if match else None


def test_the_job_closes_its_issue() -> None:
    closing = [step for step in _steps(_job()) if 'state: "closed"' in step]
    assert len(closing) == 1, f"{_JOB} opens an issue and never closes it"


def test_the_issue_is_opened_or_updated_only_while_the_answer_is_no() -> None:
    # Otherwise a run with nothing blocked would comment a report on the issue
    # and then comment again as it closed it.
    opening = _the_step("issues.create(")
    assert _condition(opening) == f"{_ADOPTABLE} == 'false' && {_ON_MAIN}"


def test_the_issue_is_closed_only_once_no_app_is_blocked() -> None:
    closing = _the_step('state: "closed"')
    assert _condition(closing) == f"{_ADOPTABLE} == 'true' && {_ON_MAIN}"


def test_the_close_comments_with_the_run_and_the_report_then_closes() -> None:
    closing = _the_step('state: "closed"')
    # The report is what tells the reader the `ignore` entries can go, so the
    # last word on the issue carries it rather than a bare "closing".
    assert "REPORT_PATH: ${{ runner.temp }}/report.md" in closing
    assert "const report = fs.readFileSync(process.env.REPORT_PATH" in closing
    body = re.search(r"const body = \[\n(.*?)\]\.join", closing, re.DOTALL)
    assert body is not None
    assert "`Run: ${run}`," in body.group(1)
    assert re.search(r"^ +report,$", body.group(1), re.MULTILINE)
    comment = closing.index("issues.createComment(")
    assert "issue_number: match.number, body," in closing[comment:]
    assert comment < closing.index('state: "closed"')
    # Nothing is opened just to be closed: a quiet week with no open issue
    # stays quiet, and the comment is added once because a closed issue is not
    # found again by the open-issue lookup.
    assert "issues.create(" not in closing
    assert closing.index("if (!match)") < comment
    assert 'state: "open", labels: "upstream-drift"' in closing


def test_the_job_names_its_issue_once() -> None:
    # Both steps find the issue by exact title. Named once at job level, the
    # step that closes it cannot drift from the step that opened it.
    block = _job()
    assert len(re.findall(r"^    env:\n      ISSUE_TITLE: ", block, re.MULTILINE)) == 1
    assert 'const title = "' not in block, "the title is restated in a script"
    assert 'issue.title === "' not in block, "the title is restated in a script"
    # A step-level env would shadow the job's title for that step alone.
    assert not re.search(r"^ {8,}ISSUE_TITLE:", block, re.MULTILINE)
    for marker in ("issues.create(", 'state: "closed"'):
        assert "process.env.ISSUE_TITLE" in _the_step(marker), marker


def _run_report(results: str, tmp_path: Path) -> tuple[str, str]:
    """Run the job's report script on `results`; return its report and outputs.

    `results` has the shape the probe step writes: one `app|declared|probed|verdict`
    line per app, the verdict being `ok` or `blocked`.
    """
    step = _the_step("name: Write the report")
    match = re.search(r"<<'PY'[^\n]*\n(.*?)\n *PY\n", step, re.DOTALL)
    assert match is not None
    outputs = tmp_path / "github-output"
    outputs.touch()
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(match.group(1))],
        env={**os.environ, "RESULTS": results, "GITHUB_OUTPUT": str(outputs)},
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout, outputs.read_text(encoding="utf-8")


_THREE_BLOCKED = """\
react|^7.0.2|7.0.2|ok
vue|^5.9.3|7.0.2|blocked
svelte|^5.9.3|7.0.2|blocked
angular|~6.0.2|7.0.2|blocked"""

_ONE_BLOCKED = """\
react|^7.0.2|7.0.2|ok
vue|^7.0.2|7.0.2|ok
svelte|^5.9.3|7.0.2|ok
angular|~6.0.2|7.0.2|blocked"""

_NONE_BLOCKED = """\
react|^7.0.2|7.0.2|ok
vue|^7.0.2|7.0.2|ok
svelte|^5.9.3|7.0.2|ok
angular|~6.0.2|7.0.2|ok"""

# A declared range with an `||` in it splits into more fields than a row has, so
# the line is dropped from the table. Every app that was read builds, and the
# issue must still stay open: an app nobody could read is not an app that builds.
_ONE_UNREADABLE = """\
react|^7.0.2|7.0.2|ok
vue|^7.0.2|7.0.2|ok
svelte|^5.9.3|7.0.2|ok
angular|~6.0.2 || ^7|7.0.2|ok"""


@pytest.mark.parametrize(
    ("results", "adoptable"),
    [
        pytest.param(_THREE_BLOCKED, False, id="three-blocked"),
        pytest.param(_ONE_BLOCKED, False, id="one-blocked"),
        pytest.param(_NONE_BLOCKED, True, id="none-blocked"),
        pytest.param("", False, id="nothing-probed"),
        pytest.param(_ONE_UNREADABLE, False, id="unreadable-line"),
    ],
)
def test_the_report_says_whether_any_app_is_blocked(
    results: str, adoptable: bool, tmp_path: Path
) -> None:
    report, outputs = _run_report(results, tmp_path)
    assert outputs == f"adoptable={'true' if adoptable else 'false'}\n"
    # The prose says every app builds exactly when the issue is closed with it,
    # so the closing comment and the condition that posted it cannot disagree.
    assert ("**Every app builds under the next major.**" in report) is adoptable
