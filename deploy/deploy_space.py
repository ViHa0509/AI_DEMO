"""Deploy the app to a Hugging Face Space (Docker SDK). Used by .github/workflows/ci-cd.yml.

Environment:
  HF_TOKEN            Hugging Face token with write access (required)
  HF_SPACE            "owner/space-name" (default: <token owner>/ai-learning-assistant)
  SPACE_PRIVATE       "true" to create the Space as private (only for a new Space)
  ALLOW_PUBLIC        "true" to allow deploying without APP_PASSWORD (not recommended)
  GIT_SHA             commit being deployed (for the Space commit message)

  Copied to the Space as secrets:   OPENAI_API_KEY (as API_KEY), APP_PASSWORD, APP_SECRET,
                                    TAVILY_API_KEY, VIRUSTOTAL_API_KEY, PGVECTOR_CONN
  Copied to the Space as variables: AI_MODEL_PATH, AI_MODEL_API, RATE_LIMIT_PER_MINUTE

Usage:
  python deploy/deploy_space.py            # deploy
  python deploy/deploy_space.py --dry-run  # only list the files that would be uploaded
"""
import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPACE_NAME = "ai-learning-assistant"

# Everything the Docker image needs, and nothing else
INCLUDE = ["Dockerfile", ".dockerignore", "requirements.txt", "main.py", "app", "web", "vectordb/data"]

SECRETS = {  # Space secret name -> environment variable
    "API_KEY": "OPENAI_API_KEY",
    "APP_PASSWORD": "APP_PASSWORD",
    "APP_SECRET": "APP_SECRET",
    "TAVILY_API_KEY": "TAVILY_API_KEY",
    "VIRUSTOTAL_API_KEY": "VIRUSTOTAL_API_KEY",
    "PGVECTOR_CONN": "PGVECTOR_CONN",
}
VARIABLES = ["AI_MODEL_PATH", "AI_MODEL_API", "RATE_LIMIT_PER_MINUTE"]

SPACE_README = """---
title: AI Learning Assistant
emoji: 🎓
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
short_description: LangGraph multi-agent assistant for IT learning paths
---

# AI Learning Assistant

Deployed automatically from GitHub by `deploy/deploy_space.py`. Do not edit files here:
changes are overwritten on the next deployment.
"""


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _truthy(name: str) -> bool:
    return _env(name).lower() in {"1", "true", "yes"}


def stage_files(target: Path) -> list[str]:
    for item in INCLUDE:
        src = ROOT / item
        if src.is_dir():
            shutil.copytree(src, target / item, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif src.exists():
            (target / item).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target / item)
        else:
            sys.exit(f"Missing file to deploy: {item}")
    (target / "README.md").write_text(SPACE_README, encoding="utf-8")
    return sorted(str(p.relative_to(target)).replace("\\", "/") for p in target.rglob("*") if p.is_file())


def app_url(space: str) -> str:
    owner, name = space.split("/", 1)
    return f"https://{owner}-{name}".lower().replace("_", "-").replace(".", "-") + ".hf.space"


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy to a Hugging Face Space")
    parser.add_argument("--dry-run", action="store_true", help="list files without uploading")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        files = stage_files(Path(tmp))
        if args.dry_run:
            print("\n".join(files))
            print(f"\n{len(files)} files would be uploaded")
            return

        token = _env("HF_TOKEN")
        if not token:
            # Keeps CI green until deployment is configured
            print("::warning::HF_TOKEN is not set; skipping deployment. See docs/DEPLOYMENT.md")
            return
        if not _env("APP_PASSWORD") and not _truthy("SPACE_PRIVATE") and not _truthy("ALLOW_PUBLIC"):
            sys.exit(
                "::error::APP_PASSWORD is not set. A public Space without a password lets anyone use "
                "your OpenAI quota. Set APP_PASSWORD (or SPACE_PRIVATE / ALLOW_PUBLIC=true)."
            )

        from huggingface_hub import HfApi

        api = HfApi(token=token)
        space = _env("HF_SPACE") or f"{api.whoami()['name']}/{DEFAULT_SPACE_NAME}"
        api.create_repo(space, repo_type="space", space_sdk="docker", private=_truthy("SPACE_PRIVATE"), exist_ok=True)

        for secret, env_name in SECRETS.items():
            if value := _env(env_name):
                api.add_space_secret(space, secret, value)
                print(f"secret   {secret} updated")
        for variable in VARIABLES:
            if value := _env(variable):
                api.add_space_variable(space, variable, value)
                print(f"variable {variable}={value}")

        sha = _env("GIT_SHA")[:7] or "local"
        api.upload_folder(
            folder_path=tmp,
            repo_id=space,
            repo_type="space",
            commit_message=f"Deploy {sha} from GitHub",
            delete_patterns=["*"],  # remove files that are no longer part of the app
        )

    print(f"\nDeployed {len(files)} files to https://huggingface.co/spaces/{space}")
    print(f"App URL (live once the Space finishes building): {app_url(space)}")
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### 🚀 Deployed `{sha}`\n\n- Space: https://huggingface.co/spaces/{space}\n- App: {app_url(space)}\n")


if __name__ == "__main__":
    main()
