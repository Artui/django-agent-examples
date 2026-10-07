"""Every job in upstream-drift.yml that opens an issue also closes it.

The workflow runs only on its schedule, never on a pull request, so a job that
opens an issue and has no way to close it merges green and is found months
later as an issue nobody can tell is current. Both of this repository's jobs
shipped that way. Each now has one step that opens or updates its issue and one
that closes it, chosen by one outcome of the job:

- `backend-resolve-latest` files on failure and closes on a pass.
- `typescript-next-major` writes a `state` of `blocked`, `adoptable` or
  `adopted`. The first two open or update its issue; only `adopted` closes it.

These tests sit beside the backend's because the gallery has no other place for
tests about its own CI, and the backend suite is the one `tests.yml` runs on
every pull request.

The workflow is read as text rather than parsed: the checks are about which
strings a job's block contains, and no YAML parser is declared here. The two
exceptions are the readiness job's report script and the probe's snippet that
reads the registry's answer, which are executed, because which state the job
writes is decided by what they compute and a string match cannot say what a
condition evaluates to.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "upstream-drift.yml"

_READINESS = "typescript-next-major"
_BACKEND = "backend-resolve-latest"

# Each issue reports on main, so only a run on main may file or clear one. A
# dispatch from a branch is then a trial that touches no issue; without this, a
# branch that fixed a job would close its issue before the fix had landed.
_ON_MAIN = "github.ref == 'refs/heads/main'"

# When each job's two issue steps run, as (opens or updates, closes). The two
# must never both run: a run would then comment on the issue twice. The
# readiness job matches its output by exact value in both, so a run that never
# wrote it touches the issue in neither direction.
_STATE = "steps.report.outputs.state"
_WHEN = {
    _BACKEND: ("failure()", "success()"),
    _READINESS: (f"({_STATE} == 'blocked' || {_STATE} == 'adoptable')", f"{_STATE} == 'adopted'"),
}

_OPENS = "issues.create("
_CLOSES = 'state: "closed"'


def _jobs() -> dict[str, str]:
    """Each job's name mapped to the text of its block."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z][a-z0-9-]*):\n", body, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def _steps(job: str) -> list[str]:
    return re.split(r"^      - ", _jobs()[job], flags=re.MULTILINE)[1:]


def _the_step(job: str, marker: str) -> str:
    """The one step in `job` whose text contains `marker`."""
    found = [step for step in _steps(job) if marker in step]
    assert len(found) == 1, f"{len(found)} steps in {job} contain {marker!r}"
    return found[0]


def _condition(step: str) -> str | None:
    match = re.search(r"^        if: (.+)$", step, re.MULTILINE)
    return match.group(1) if match else None


def test_every_job_that_opens_an_issue_closes_it() -> None:
    opening = {name for name, block in _jobs().items() if _OPENS in block}
    # Guards the parse as well: a split that found no jobs would pass the loop.
    assert opening == set(_WHEN)
    for name in opening:
        closing = [step for step in _steps(name) if _CLOSES in step]
        assert len(closing) == 1, f"{name} opens an issue and never closes it"


@pytest.mark.parametrize("job", sorted(_WHEN))
def test_each_issue_step_runs_on_its_own_outcome_and_only_on_main(job: str) -> None:
    opens, closes = _WHEN[job]
    assert _condition(_the_step(job, _CLOSES)) == f"{closes} && {_ON_MAIN}"
    assert _condition(_the_step(job, _OPENS)) == f"{opens} && {_ON_MAIN}"


# Where each close step reads the report its comment carries: the readiness
# job's own report, and the held-back check's report for the backend job, which
# that check writes on a pass as well as on a failure.
_REPORTS = {
    _READINESS: ("REPORT_PATH: ${{ runner.temp }}/report.md", "process.env.REPORT_PATH"),
    _BACKEND: ("REPORT: ${{ steps.held-back.outputs.report }}", "process.env.REPORT"),
}


@pytest.mark.parametrize("job", sorted(_WHEN))
def test_each_close_comments_with_the_run_and_the_report_then_closes(job: str) -> None:
    closing = _the_step(job, _CLOSES)
    env, variable = _REPORTS[job]
    assert env in closing
    assert f"readFileSync({variable}" in closing
    body = re.search(r"const body = \[\n(.*?)\]\.join", closing, re.DOTALL)
    assert body is not None
    assert "`Run: ${run}`," in body.group(1)
    assert re.search(r"^ +report,$", body.group(1), re.MULTILINE)
    comment = closing.index("issues.createComment(")
    assert "issue_number: match.number, body," in closing[comment:]
    assert comment < closing.index(_CLOSES)
    # Nothing is opened just to be closed: a quiet week with no open issue
    # stays quiet, and the comment is added once because a closed issue is not
    # found again by the open-issue lookup.
    assert _OPENS not in closing
    assert closing.index("if (!match)") < comment
    assert 'state: "open", labels: "upstream-drift"' in closing


@pytest.mark.parametrize("job", sorted(_WHEN))
def test_each_job_names_its_issue_once(job: str) -> None:
    # Both steps find the issue by exact title. Named once at job level, the
    # step that closes it cannot drift from the step that opened it.
    block = _jobs()[job]
    assert len(re.findall(r"^    env:\n      ISSUE_TITLE: ", block, re.MULTILINE)) == 1
    assert 'const title = "' not in block, "the title is restated in a script"
    assert 'issue.title === "' not in block, "the title is restated in a script"
    # A step-level env would shadow the job's title for that step alone.
    assert not re.search(r"^ {8,}ISSUE_TITLE:", block, re.MULTILINE)
    for marker in (_OPENS, _CLOSES):
        assert "process.env.ISSUE_TITLE" in _the_step(job, marker), marker


def test_no_two_jobs_share_an_issue() -> None:
    # Both issues carry the same label, so the title is all that tells them
    # apart; a shared one would have each job close the other's issue.
    titles = []
    for job in _WHEN:
        match = re.search(r"^      ISSUE_TITLE: (.+)$", _jobs()[job], re.MULTILINE)
        assert match is not None, job
        titles.append(match.group(1))
    assert len(set(titles)) == len(titles)


def test_the_probe_writes_the_fields_the_report_reads() -> None:
    # The fifth field is what tells an app that has adopted the next major from
    # one that merely builds under it. A probe and a report disagreeing on the
    # count would make every line unreadable, which keeps the issue open
    # forever without failing anything.
    probe = _the_step(_READINESS, "id: probe")
    assert 'npm view "typescript@$before" version --json' in probe
    assert 'echo "$app|$before|$resolved|$verdict|$majors" >> "$GITHUB_OUTPUT"' in probe
    assert 'line.count("|") == 4' in _the_step(_READINESS, "id: report")


def _run_majors(admitted: str) -> subprocess.CompletedProcess[str]:
    """Run the probe's majors snippet on `admitted`, which is what `npm view` printed.

    The snippet sits in the shell's double quotes, so what node receives is the
    text in the workflow only while it has nothing those quotes interpret.
    """
    step = _the_step(_READINESS, "id: probe")
    # Anchored at both ends of its lines on purpose. Under the runner's default
    # `bash -e`, a bare assignment from a command substitution fails the step
    # when node exits non-zero; an `|| true` or a pipe after the closing quote
    # would swallow that exit, and stops this from matching at all.
    match = re.search(
        r'^ *majors="\$\(ADMITTED="\$admitted" node -p "\n(.*?)\n *"\)"$',
        step,
        re.DOTALL | re.MULTILINE,
    )
    assert match is not None
    snippet = match.group(1)
    for interpreted in ('"', "$", "`", "\\"):
        assert interpreted not in snippet, f"the shell rewrites {interpreted!r} before node runs"
    return subprocess.run(
        ["node", "-p", textwrap.dedent(snippet)],
        env={**os.environ, "ADMITTED": admitted},
        capture_output=True,
        text=True,
        check=False,
    )


# What `npm view "typescript@<range>" version --json` prints, as npm 11 prints
# it: one version as a bare string, several as a list, and a failure as an
# `error` object on stdout. `json.dumps` with an indent of two writes the same
# bytes npm does. The shell's `$(...)` strips the trailing newline.
def _npm_error(code: str, summary: str, detail: str) -> str:
    return json.dumps({"error": {"code": code, "summary": summary, "detail": detail}}, indent=2)


# npm answers a range admitting nothing with this, and `(none)` (an app with no
# `typescript` at all) the same way.
_NPM_NO_SUCH_VERSION = _npm_error(
    "E404",
    "No match found for version ^99",
    "The requested resource 'typescript@^99' could not be found or you do not have"
    " permission to access it.\n\nNote that you can also install from a\ntarball,"
    " folder, http url, or git url.",
)

# And this with `--registry` pointed at a port nothing listens on.
_NPM_UNREACHABLE = _npm_error(
    "ECONNREFUSED",
    "FetchError: request to http://127.0.0.1:9/typescript failed,"
    " reason: connect ECONNREFUSED 127.0.0.1:9",
    "If you are behind a proxy, please make sure that the 'proxy' config is set"
    " properly.  See: 'npm help config'",
)

_NEEDS_NODE = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="the probe's snippet is JavaScript, and node is not on PATH",
)


@_NEEDS_NODE
@pytest.mark.parametrize(
    ("admitted", "majors"),
    [
        pytest.param(json.dumps("7.0.2"), "7", id="one-version"),
        pytest.param(json.dumps(["6.0.2", "6.0.3"], indent=2), "6", id="one-major"),
        pytest.param(json.dumps(["6.0.2", "6.0.3", "7.0.2"], indent=2), "6 7", id="two-majors"),
        pytest.param(_NPM_NO_SUCH_VERSION, "", id="no-such-version"),
    ],
)
def test_the_probe_reads_the_majors_a_range_admits(admitted: str, majors: str) -> None:
    # `declares` in the report looks the probed major up in this list, so a
    # snippet reading the wrong part of a version, or the JSON as raw text,
    # answers no for every app and the issue never closes.
    completed = _run_majors(admitted)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == f"{majors}\n"


@_NEEDS_NODE
def test_a_registry_that_does_not_answer_fails_the_probe() -> None:
    # Read as no majors, an unreachable registry would say every app that
    # builds had still to bump: `adopted` would read as `adoptable` and open
    # the issue again, and an open issue would get a comment for a change
    # nobody made. Failing here skips the report, and with it both issue steps.
    completed = _run_majors(_NPM_UNREACHABLE)
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "ECONNREFUSED" in completed.stderr


def _run_report(results: str, tmp_path: Path) -> tuple[str, str]:
    """Run the readiness job's report script on `results`; return report and outputs.

    `results` has the shape the probe step writes: one
    `app|declared|probed|verdict|majors` line per app, the verdict being `ok` or
    `blocked` and `majors` the majors the declared range admits.
    """
    step = _the_step(_READINESS, "id: report")
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


def _fingerprint(report: str) -> str:
    match = re.search(r"<!-- typescript-next-major: ([0-9a-f]+) -->", report)
    assert match is not None
    return match.group(1)


# Today's state, as the probe writes it.
_THREE_BLOCKED = """\
react|^7.0.2|7.0.2|ok|7
vue|^5.9.3|7.0.2|blocked|5
svelte|^5.9.3|7.0.2|blocked|5
angular|~6.0.2|7.0.2|blocked|6"""

_ONE_BLOCKED = """\
react|^7.0.2|7.0.2|ok|7
vue|^5.9.3|7.0.2|ok|5
svelte|^5.9.3|7.0.2|ok|5
angular|~6.0.2|7.0.2|blocked|6"""

_THREE_TO_BUMP = """\
react|^7.0.2|7.0.2|ok|7
vue|^5.9.3|7.0.2|ok|5
svelte|^5.9.3|7.0.2|ok|5
angular|~6.0.2|7.0.2|ok|6"""

_ONE_TO_BUMP = """\
react|^7.0.2|7.0.2|ok|7
vue|^7.0.2|7.0.2|ok|7
svelte|>=5.9.3|7.0.2|ok|5 6 7
angular|~6.0.2|7.0.2|ok|6"""

_ALL_ADOPTED = """\
react|^7.0.2|7.0.2|ok|7
vue|^7.0.2|7.0.2|ok|7
svelte|>=5.9.3|7.0.2|ok|5 6 7
angular|~7.0.2|7.0.2|ok|7"""

# A declared range with an `||` in it splits into more fields than a row has, so
# the line is dropped from the table. Every app that was read has adopted, and
# the issue must still stay open: an app nobody could read has not adopted.
_ONE_UNREADABLE = """\
react|^7.0.2|7.0.2|ok|7
vue|^7.0.2|7.0.2|ok|7
svelte|^7.0.2|7.0.2|ok|7
angular|~6.0.2 || ~7.0.2|7.0.2|ok|6 7"""

# A verdict other than `ok` is not a build that passed. The probe writes only
# `ok` or `blocked` today, so these two hold the report to an allow-list of
# `ok`: read against `blocked` instead, each would say every app had adopted.
_EMPTY_VERDICT = """\
react|^7.0.2|7.0.2|ok|7
vue|^7.0.2|7.0.2|ok|7
svelte|^7.0.2|7.0.2|ok|7
angular|~7.0.2|7.0.2||7"""

_UNKNOWN_VERDICT = """\
react|^7.0.2|7.0.2|ok|7
vue|^7.0.2|7.0.2|ok|7
svelte|^7.0.2|7.0.2|ok|7
angular|~7.0.2|7.0.2|timeout|7"""

_ADOPTABLE_HEADLINE = "**Every app builds under the next major**, and these do not declare"
_ADOPTED_HEADLINE = "**Every app declares the next major and builds under it.**"


@pytest.mark.parametrize(
    ("results", "state", "to_bump"),
    [
        pytest.param(_THREE_BLOCKED, "blocked", [], id="three-blocked"),
        pytest.param(_ONE_BLOCKED, "blocked", [], id="one-blocked"),
        pytest.param(_THREE_TO_BUMP, "adoptable", ["vue", "svelte", "angular"], id="three-to-bump"),
        pytest.param(_ONE_TO_BUMP, "adoptable", ["angular"], id="one-to-bump"),
        pytest.param(_ALL_ADOPTED, "adopted", [], id="all-adopted"),
        pytest.param("", "blocked", [], id="nothing-probed"),
        pytest.param(_ONE_UNREADABLE, "blocked", [], id="unreadable-line"),
        pytest.param(_EMPTY_VERDICT, "blocked", [], id="empty-verdict"),
        pytest.param(_UNKNOWN_VERDICT, "blocked", [], id="unknown-verdict"),
    ],
)
def test_the_report_states_how_far_adoption_has_got(
    results: str, state: str, to_bump: list[str], tmp_path: Path
) -> None:
    report, outputs = _run_report(results, tmp_path)
    assert outputs == f"state={state}\n"
    # The prose says what the state is, so the comment a step posts and the
    # condition that chose the step cannot disagree.
    assert (_ADOPTABLE_HEADLINE in report) is (state == "adoptable")
    assert (_ADOPTED_HEADLINE in report) is (state == "adopted")
    # The apps still to bump are named with the Dependabot entry to delete, and
    # an app that has adopted is not.
    for app in ("react", "vue", "svelte", "angular"):
        assert (f'the entry under `directory: "/{app}"`' in report) is (app in to_bump), app


def test_an_app_bumping_moves_the_fingerprint(tmp_path: Path) -> None:
    # Both are `adoptable` and every verdict is `ok` in both, so a fingerprint
    # of the verdicts alone would call them the same report. The open step runs
    # on each, rewrites the body silently and comments only when the
    # fingerprint moves, so two apps bumping would be announced to nobody
    # watching the issue. `adoptable` to `adopted` needs no such help: the
    # close step runs then instead, and it comments whatever the fingerprint.
    three, _ = _run_report(_THREE_TO_BUMP, tmp_path)
    one, _ = _run_report(_ONE_TO_BUMP, tmp_path)
    assert _fingerprint(three) != _fingerprint(one)
