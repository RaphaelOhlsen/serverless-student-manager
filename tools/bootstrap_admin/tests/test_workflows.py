from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_BOOTSTRAP_WORKFLOW = _ROOT / ".github/workflows/bootstrap-first-admin.yml"


def test_bootstrap_workflow_masks_dispatch_pii_before_use() -> None:
    workflow = _BOOTSTRAP_WORKFLOW.read_text(encoding="utf-8")
    step = workflow.split("- name: Bootstrap first Administrator", maxsplit=1)[1]

    assert "BOOTSTRAP_FULL_NAME" not in step
    assert "BOOTSTRAP_EMAIL" not in step
    assert "${{ inputs.full_name }}" not in step
    assert "${{ inputs.email }}" not in step

    assert "mapfile" not in step
    assert "bootstrap_inputs" not in step

    assert "jq -er '.inputs.full_name | strings' \"$GITHUB_EVENT_PATH\"" in step
    assert "jq -er '.inputs.email | strings' \"$GITHUB_EVENT_PATH\"" in step

    full_name_read = step.index("bootstrap_full_name_raw=")
    email_read = step.index("bootstrap_email_raw=")

    full_name_mask = step.index('mask_workflow_value "$bootstrap_full_name_raw"')
    email_mask = step.index('mask_workflow_value "$bootstrap_email_raw"')

    full_name_assignment = step.index('bootstrap_full_name="$bootstrap_full_name_raw"')
    email_assignment = step.index('bootstrap_email="$bootstrap_email_raw"')

    unset_raw = step.index("unset bootstrap_full_name_raw bootstrap_email_raw")
    cli_invocation = step.index("python -m tools.bootstrap_admin")

    assert full_name_read < full_name_mask < full_name_assignment < unset_raw < cli_invocation
    assert email_read < email_mask < email_assignment < unset_raw < cli_invocation

    assert "value=\"${value//'%'/'%25'}\"" in step
    assert "value=\"${value//$'\\r'/'%0D'}\"" in step
    assert "value=\"${value//$'\\n'/'%0A'}\"" in step

    assert '--full-name "$bootstrap_full_name"' in step
    assert '--email "$bootstrap_email"' in step

    assert "set -euo pipefail" in step
    assert "set -x" not in step


def test_resume_workflow_has_no_personal_identity_inputs() -> None:
    workflow = (_ROOT / ".github/workflows/resume-first-admin-invitation.yml").read_text(
        encoding="utf-8"
    )

    assert "full_name:" not in workflow
    assert "email:" not in workflow
    assert "BOOTSTRAP_FULL_NAME" not in workflow
    assert "BOOTSTRAP_EMAIL" not in workflow
