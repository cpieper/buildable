import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_image_copies_project_readme_before_installing_project() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    readme_copy = "COPY backend/README.md ./README.md"
    assert readme_copy in dockerfile
    assert dockerfile.index(readme_copy) < dockerfile.index("RUN uv sync --frozen --no-dev")
    assert "--no-install-project" not in dockerfile


def test_reset_script_rejects_mismatched_passwords_in_bash() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/reset-password.sh")],
        input="first\nsecond\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Passwords do not match." in result.stderr
    assert "docker compose" not in result.stderr
