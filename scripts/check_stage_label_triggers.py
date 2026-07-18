#!/usr/bin/env python3
"""Validate isolation between Stage 2 label-triggered collectors.

The project intentionally uses a tiny workflow reader instead of a package
dependency. It extracts only the workflow fields needed for the trigger
contract: pull_request types, collect-job conditions, workflow_run sources,
artifact names, and fixed request stage identifiers.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"


@dataclass(frozen=True)
class StageSpec:
    name: str
    label: str
    request_stage: str
    collector_path: Path
    collector_workflow: str
    trusted_path: Path
    trusted_workflow: str
    artifact_prefix: str


@dataclass(frozen=True)
class CheckResult:
    label: str
    passed: bool
    detail: str = ""


STAGES = {
    "stage2a": StageSpec(
        name="Stage 2A",
        label="ai-fix-proposal",
        request_stage="FIX_PROPOSAL_REQUEST",
        collector_path=WORKFLOW_DIR / "fix-proposal-collect.yml",
        collector_workflow="Fix Proposal Request Collect",
        trusted_path=WORKFLOW_DIR / "fix-proposal.yml",
        trusted_workflow="Fix Proposal Generator",
        artifact_prefix="fix-proposal-request-",
    ),
    "stage2b": StageSpec(
        name="Stage 2B",
        label="ai-fix-approved",
        request_stage="FIX_APPROVAL_REQUEST",
        collector_path=WORKFLOW_DIR / "fix-approval-collect.yml",
        collector_workflow="Fix Approval Request Collect",
        trusted_path=WORKFLOW_DIR / "fix-approval.yml",
        trusted_workflow="Fix Approval Recorder",
        artifact_prefix="fix-approval-request-",
    ),
    "stage2c": StageSpec(
        name="Stage 2C-A",
        label="ai-fix-validate",
        request_stage="SANDBOX_VALIDATION_REQUEST",
        collector_path=WORKFLOW_DIR / "fix-sandbox-collect.yml",
        collector_workflow="Sandbox Validation Request Collector",
        trusted_path=WORKFLOW_DIR / "fix-sandbox.yml",
        trusted_workflow="Sandbox Preflight Validator",
        artifact_prefix="sandbox-validation-request-",
    ),
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def add(results: list[CheckResult], label: str, passed: bool, detail: str = "") -> None:
    results.append(CheckResult(label, passed, detail))


def leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def block_after_key(text: str, key: str, indent: int) -> str:
    lines = text.splitlines()
    marker = " " * indent + f"{key}:"
    for index, line in enumerate(lines):
        if line == marker or line.startswith(marker + " "):
            block: list[str] = []
            for candidate in lines[index + 1 :]:
                if candidate.strip() and leading_spaces(candidate) <= indent:
                    break
                block.append(candidate)
            return "\n".join(block)
    return ""


def list_values_under_key(text: str, key: str, indent: int) -> list[str]:
    block = block_after_key(text, key, indent)
    values: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            values.append(stripped[2:].strip("'\""))
    return values


def job_block(text: str, job_name: str) -> str:
    jobs = block_after_key(text, "jobs", 0)
    return block_after_key(jobs, job_name, 2)


def multiline_value(text: str, key: str, indent: int) -> str:
    lines = text.splitlines()
    marker = " " * indent + f"{key}:"
    for index, line in enumerate(lines):
        if not (line == marker or line.startswith(marker + " ")):
            continue
        after = line.split(":", 1)[1].strip()
        if after and after not in {">", ">-", "|", "|-"}:
            return after.strip("'\"")
        collected: list[str] = []
        for candidate in lines[index + 1 :]:
            if candidate.strip() and leading_spaces(candidate) <= indent:
                break
            stripped = candidate.strip()
            if stripped:
                collected.append(stripped)
        return " ".join(collected)
    return ""


def pull_request_types(workflow_text: str) -> list[str]:
    on_block = block_after_key(workflow_text, "on", 0)
    pull_request = block_after_key(on_block, "pull_request", 2)
    return list_values_under_key(pull_request, "types", 4)


def workflow_run_sources(workflow_text: str) -> list[str]:
    on_block = block_after_key(workflow_text, "on", 0)
    workflow_run = block_after_key(on_block, "workflow_run", 2)
    return list_values_under_key(workflow_run, "workflows", 4)


def collect_if(workflow_text: str) -> str:
    return multiline_value(job_block(workflow_text, "collect"), "if", 4)


def trusted_job_if(workflow_text: str, job_name: str) -> str:
    return multiline_value(job_block(workflow_text, job_name), "if", 4)


def collector_processes_event(
    spec: StageSpec,
    *,
    event_name: str,
    action: str,
    label: str | None,
) -> bool:
    text = read_text(spec.collector_path)
    types = pull_request_types(text)
    condition = collect_if(text)
    return (
        event_name == "pull_request"
        and action in types
        and action == "labeled"
        and label == spec.label
        and "github.event.action == 'labeled'" in condition
        and f"github.event.label.name == '{spec.label}'" in condition
    )


def collector_artifact_names(workflow_text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"(?m)^\s+name:\s+([a-z0-9-]+\$\{\{ github\.run_id \}\})\s*$", workflow_text)
    }


def check_collector(spec: StageSpec) -> list[CheckResult]:
    text = read_text(spec.collector_path)
    condition = collect_if(text)
    types = pull_request_types(text)
    collect = job_block(text, "collect")
    results: list[CheckResult] = []
    add(results, f"{spec.name} collector workflow name is fixed", f"name: {spec.collector_workflow}" in text)
    add(results, f"{spec.name} collector only declares labeled trigger", types == ["labeled"], repr(types))
    add(results, f"{spec.name} collector requires labeled action", "github.event.action == 'labeled'" in condition)
    add(results, f"{spec.name} collector requires only {spec.label}", f"github.event.label.name == '{spec.label}'" in condition)
    for other in sorted({stage.label for stage in STAGES.values()} - {spec.label}):
        add(results, f"{spec.name} collector does not accept {other}", other not in condition)
    add(results, f"{spec.name} collector rejects forks", "head.repo.full_name == github.repository" in condition)
    add(results, f"{spec.name} collector pins repository", EXPECTED_REPOSITORY in condition)
    add(results, f"{spec.name} collector has read-only contents permission", "contents: read" in collect and ": write" not in collect)
    add(results, f"{spec.name} collector has no Codex or secret use", "OPENAI_API_KEY" not in collect and "openai/codex-action" not in collect and "secrets." not in collect)
    add(results, f"{spec.name} collector records request stage env", f"REQUEST_STAGE: {spec.request_stage}" in collect)
    add(results, f"{spec.name} collector writes request_stage", '"request_stage": os.environ["REQUEST_STAGE"]' in collect)
    add(results, f"{spec.name} collector records event action", '"event_action": event["action"]' in collect)
    add(results, f"{spec.name} collector records pull_request event name", '"event_name": "pull_request"' in collect)
    add(results, f"{spec.name} collector records event label", '"event_label"' in collect)
    artifact_names = collector_artifact_names(text)
    expected_artifact = f"{spec.artifact_prefix}${{{{ github.run_id }}}}"
    add(results, f"{spec.name} collector artifact prefix is stage-specific", expected_artifact in artifact_names, repr(artifact_names))
    return results


def check_trusted_workflow(spec: StageSpec) -> list[CheckResult]:
    text = read_text(spec.trusted_path)
    watched = workflow_run_sources(text)
    primary_job = {
        "stage2a": "generate",
        "stage2b": "record",
        "stage2c": "preflight",
    }[next(key for key, value in STAGES.items() if value == spec)]
    condition = trusted_job_if(text, primary_job)
    results: list[CheckResult] = []
    add(results, f"{spec.name} trusted workflow name is fixed", f"name: {spec.trusted_workflow}" in text)
    add(results, f"{spec.name} trusted workflow watches only its collector", watched == [spec.collector_workflow], repr(watched))
    add(results, f"{spec.name} trusted workflow requires collector success", "github.event.workflow_run.conclusion == 'success'" in condition)
    add(results, f"{spec.name} trusted workflow checks exact collector name", f"github.event.workflow_run.name == '{spec.collector_workflow}'" in condition)
    add(results, f"{spec.name} trusted workflow checks event type", "github.event.workflow_run.event == 'pull_request'" in condition)
    add(results, f"{spec.name} trusted workflow checks repository identity", EXPECTED_REPOSITORY in condition)
    add(results, f"{spec.name} trusted workflow artifact name matches collector", f"ARTIFACT_NAME: {spec.artifact_prefix}${{{{ github.event.workflow_run.id }}}}" in text)
    return results


def check_runtime_stage_validation() -> list[CheckResult]:
    scripts = {
        "Stage 2A": (
            REPO_ROOT / "scripts" / "fix_proposal_generator.py",
            "REQUEST_STAGE = \"FIX_PROPOSAL_REQUEST\"",
            "fix proposal request came from an unexpected stage",
        ),
        "Stage 2B": (
            REPO_ROOT / "scripts" / "approval_record.py",
            "REQUEST_STAGE = \"FIX_APPROVAL_REQUEST\"",
            "approval request came from an unexpected stage",
        ),
        "Stage 2C-A": (
            REPO_ROOT / "scripts" / "sandbox_validation.py",
            "REQUEST_STAGE = \"SANDBOX_VALIDATION_REQUEST\"",
            "sandbox request came from an unexpected stage",
        ),
    }
    results: list[CheckResult] = []
    for label, (path, constant, message) in scripts.items():
        text = read_text(path)
        add(results, f"{label} runtime has request stage constant", constant in text)
        add(results, f"{label} runtime rejects unexpected stage", message in text)
        add(results, f"{label} runtime validates pull_request event", "pull_request" in text and "event_name" in text)
        add(results, f"{label} runtime validates labeled action", "event_action" in text and "labeled" in text)
    return results


def check_forbidden_stage2c_b_runtime() -> list[CheckResult]:
    sandbox_text = read_text(STAGES["stage2c"].trusted_path) + "\n" + read_text(REPO_ROOT / "scripts" / "sandbox_validation.py")
    lowered = sandbox_text.lower()
    results: list[CheckResult] = []
    for token in (
        "actions/checkout",
        "git apply",
        "git checkout",
        "git push",
        "git merge",
        "tests executed: yes",
        "contents: write",
        "openai_api_key",
        "openai/codex-action",
    ):
        add(results, f"Stage 2C-A has no {token}", token not in lowered)
    all_workflow_text = "\n".join(read_text(path) for path in WORKFLOW_DIR.glob("*.yml"))
    add(results, "no workflow requests contents write", "contents: write" not in all_workflow_text)
    add(results, "no workflow uses pull_request_target", "pull_request_target" not in all_workflow_text)
    return results


def event_matrix() -> dict[str, list[tuple[str, str, str | None, bool]]]:
    return {
        key: [
            ("pull_request", "labeled", spec.label, True),
            ("pull_request", "labeled", "ai-fix-proposal", spec.label == "ai-fix-proposal"),
            ("pull_request", "labeled", "ai-fix-approved", spec.label == "ai-fix-approved"),
            ("pull_request", "labeled", "ai-fix-validate", spec.label == "ai-fix-validate"),
            ("pull_request", "labeled", "other-label", False),
            ("pull_request", "unlabeled", spec.label, False),
            ("pull_request", "synchronize", None, False),
            ("pull_request", "reopened", None, False),
            ("pull_request", "edited", None, False),
        ]
        for key, spec in STAGES.items()
    }


def check_event_matrix() -> list[CheckResult]:
    results: list[CheckResult] = []
    for key, cases in event_matrix().items():
        spec = STAGES[key]
        for event_name, action, label, expected in cases:
            observed = collector_processes_event(
                spec,
                event_name=event_name,
                action=action,
                label=label,
            )
            add(
                results,
                f"{spec.name} event {action}/{label or '-'} => {expected}",
                observed is expected,
                f"observed={observed}",
            )
    return results


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    for spec in STAGES.values():
        add(results, f"{spec.collector_path.relative_to(REPO_ROOT)} exists", spec.collector_path.exists())
        add(results, f"{spec.trusted_path.relative_to(REPO_ROOT)} exists", spec.trusted_path.exists())
        results.extend(check_collector(spec))
        results.extend(check_trusted_workflow(spec))
    results.extend(check_runtime_stage_validation())
    results.extend(check_forbidden_stage2c_b_runtime())
    results.extend(check_event_matrix())
    return results


def main() -> int:
    results = run_checks()
    failed = [result for result in results if not result.passed]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = f" - {result.detail}" if result.detail else ""
        print(f"{status}: {result.label}{detail}")
    if failed:
        print(f"{len(failed)} stage label trigger checks failed.", file=sys.stderr)
        return 1
    print(f"{len(results)} stage label trigger checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
