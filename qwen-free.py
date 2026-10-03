#!/usr/bin/env python3
"""Discover, probe, and persist usable free OpenAI-compatible models."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import pathlib
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Any

import qwen_omega as qo
from free_model_catalog import (
    load_litellm_config,
    retain_validated_routes,
    write_litellm_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keep only free models that pass a real chat-completion probe."
    )
    parser.add_argument("--settings", default="/mnt/qwen-gen-data/settings.json")
    parser.add_argument("--env-root", default=str(pathlib.Path(__file__).resolve().parent))
    parser.add_argument("--timeout", type=int, default=12, help="Probe timeout in seconds")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--max-models", type=int, help="Probe at most this many candidates")
    parser.add_argument(
        "--litellm-base-url",
        default="http://litellm:4000/v1",
        help="Runtime LiteLLM URL written to settings",
    )
    parser.add_argument(
        "--litellm-model",
        default="qwen2.5-coder",
        help="Local model alias exposed by the LiteLLM stack",
    )
    parser.add_argument(
        "--ollama-base-url",
        default="http://host.docker.internal:11434/v1",
        help="Runtime Ollama URL written to settings",
    )
    parser.add_argument(
        "--probe-litellm-url",
        default="http://127.0.0.1:4000/v1",
        help="Host-reachable LiteLLM URL used for probes",
    )
    parser.add_argument(
        "--probe-ollama-url",
        default="http://127.0.0.1:11434/v1",
        help="Host-reachable Ollama URL used for probes",
    )
    parser.add_argument(
        "--litellm-config",
        help="Also prune this LiteLLM config to the models that pass the probe",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _candidate_settings(env_root: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    env = qo.read_env_files(env_root)
    env["LITELLM_BASE_URL"] = args.litellm_base_url
    env["OLLAMA_BASE_URL"] = args.ollama_base_url
    env.setdefault("LITELLM_API_KEY", env.get("LITELLM_MASTER_KEY", "sk-local-dev"))

    # command_providers already owns the free-model catalog and metadata rules.
    # Use a nonexistent temporary settings path so paid/user entries are not retained.
    with tempfile.TemporaryDirectory(prefix="qwen-free-") as temp_dir:
        candidate_path = pathlib.Path(temp_dir) / "candidates.json"
        command = [
            sys.executable,
            str(pathlib.Path(__file__).resolve().with_name("qwen_omega.py")),
            "providers",
            "add",
            "all",
            "--free",
            "--auto-fallback",
            "--env-root",
            str(env_root),
            "--settings",
            str(candidate_path),
            "--timeout",
            str(args.timeout),
            "--dry-run",
        ]
        child_env = os.environ.copy()
        child_env.update(env)
        result = subprocess.run(
            command,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=max(60, args.timeout * 40),
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "free-model discovery failed")
        discovered = json.loads(result.stdout)
        models = discovered.setdefault("modelProviders", {}).setdefault("openai", [])
        if not any(
            isinstance(item, dict) and str(item.get("id") or "") == args.litellm_model
            for item in models
        ):
            models.append(
                qo.to_model_configs(
                    [{"id": args.litellm_model}],
                    args.litellm_base_url,
                    "LITELLM_API_KEY",
                    120000,
                    3,
                    None,
                )[0]
            )
        return discovered


def _runtime_probe_url(
    base_url: str, args: argparse.Namespace, *, in_container: bool = False
) -> str:
    normalized = base_url.rstrip("/")
    if in_container:
        return normalized
    replacements = {
        args.litellm_base_url.rstrip("/"): args.probe_litellm_url.rstrip("/"),
        args.ollama_base_url.rstrip("/"): args.probe_ollama_url.rstrip("/"),
        "http://litellm:4000/v1": args.probe_litellm_url.rstrip("/"),
        "http://host.docker.internal:11434/v1": args.probe_ollama_url.rstrip("/"),
    }
    return replacements.get(normalized, normalized)


def _probe(
    item: dict[str, Any],
    env: dict[str, str],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], bool, str]:
    model_id = str(item.get("id") or "").strip()
    base_url = _runtime_probe_url(str(item.get("baseUrl") or ""), args)
    env_key = str(item.get("envKey") or "").strip()
    api_key = env.get(env_key, "")
    if env_key == "LITELLM_API_KEY" and not api_key:
        api_key = env.get("LITELLM_MASTER_KEY", "sk-local-dev")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "qwen-free-probe/1",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with exactly OK."}],
        "max_tokens": 2,
        "temperature": 0,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=max(5, args.timeout), context=context) as response:
            body = json.loads(response.read())
        choices = body.get("choices") if isinstance(body, dict) else None
        content = ""
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                content = str(message.get("content") or "").strip()
            if not content:
                content = str(choices[0].get("text") or "").strip()
        if content:
            return item, True, "ok"
        return item, False, "empty-response"
    except urllib.error.HTTPError as exc:
        return item, False, f"http-{exc.code}"
    except (TimeoutError, urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        return item, False, type(exc).__name__.lower()


def _model_priority(item: dict[str, Any], args: argparse.Namespace) -> tuple[int, str, str]:
    base_url = str(item.get("baseUrl") or "").rstrip("/")
    if base_url == args.litellm_base_url.rstrip("/"):
        rank = 0
    elif base_url == args.ollama_base_url.rstrip("/"):
        rank = 1
    else:
        rank = 2
    return rank, base_url, str(item.get("id") or "").lower()


def main() -> int:
    args = parse_args()
    settings_path = pathlib.Path(args.settings).expanduser()
    env_root = pathlib.Path(args.env_root).expanduser()
    env = qo.read_env_files(env_root)
    env["LITELLM_BASE_URL"] = args.litellm_base_url
    env["OLLAMA_BASE_URL"] = args.ollama_base_url
    env.setdefault("LITELLM_API_KEY", env.get("LITELLM_MASTER_KEY", "sk-local-dev"))

    discovered = _candidate_settings(env_root, args)
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for models in discovered.get("modelProviders", {}).values():
        if not isinstance(models, list):
            continue
        for item in models:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            base_url = str(item.get("baseUrl") or "").strip()
            env_key = str(item.get("envKey") or "").strip()
            key = (model_id, base_url, env_key)
            if model_id and base_url and key not in seen:
                seen.add(key)
                candidates.append(dict(item))
    candidates.sort(key=lambda item: _model_priority(item, args))
    if args.max_models:
        candidates = candidates[: max(1, args.max_models)]

    print(f"Free candidates: {len(candidates)}")
    alive: list[dict[str, Any]] = []
    failures: dict[str, int] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_probe, item, env, args) for item in candidates]
        for future in concurrent.futures.as_completed(futures):
            item, ok, reason = future.result()
            model_id = str(item.get("id") or "")
            if ok:
                alive.append(item)
                print(f"  alive: {model_id}")
            else:
                failures[reason] = failures.get(reason, 0) + 1

    unique_alive: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in sorted(alive, key=lambda candidate: _model_priority(candidate, args)):
        model_id = str(item.get("id") or "").strip()
        if model_id and model_id not in seen_ids:
            seen_ids.add(model_id)
            unique_alive.append(item)
    print(f"Alive free models: {len(unique_alive)}")
    if failures:
        print("Probe failures: " + ", ".join(f"{key}={value}" for key, value in sorted(failures.items())))
    if not unique_alive:
        print("ERROR: no free model passed the chat probe", file=sys.stderr)
        return 1

    settings = qo.load_json(settings_path)
    # Free-model filtering must not fail only because an older persisted chat
    # contains an empty transcript field. Normalize that user data before the
    # final schema validation; valid transcripts and messages are preserved.
    qo.normalize_conversations(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings["general"]["autoFallback"] = True
    settings.setdefault("model", {})
    settings["modelProviders"] = {"openai": unique_alive}
    settings["security"] = settings.get("security") if isinstance(settings.get("security"), dict) else {}
    settings["security"].setdefault("auth", {})
    settings["security"]["auth"]["selectedType"] = "openai"
    settings["model"]["name"] = str(unique_alive[0]["id"])
    errors = qo.validate_settings(settings)
    if errors:
        print("ERROR: filtered settings failed validation:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps(settings, indent=2, ensure_ascii=False))
        return 0

    litellm_config_path = pathlib.Path(args.litellm_config).expanduser() if args.litellm_config else None
    filtered_litellm = None
    if litellm_config_path:
        current_litellm = load_litellm_config(litellm_config_path)
        filtered_litellm = retain_validated_routes(
            current_litellm,
            [str(item.get("id") or "") for item in unique_alive],
        )
        if not filtered_litellm.get("model_list"):
            print(
                "ERROR: no LiteLLM route matched a probed model",
                file=sys.stderr,
            )
            return 1

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    saved_backup = qo.backup(settings_path) if settings_path.exists() else None
    qo.atomic_write_json(settings_path, settings)
    print(f"Updated Qwen settings: {settings_path}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    if litellm_config_path and filtered_litellm is not None:
        config_backup = qo.backup(litellm_config_path) if litellm_config_path.exists() else None
        write_litellm_config(litellm_config_path, filtered_litellm)
        print(
            f"Updated LiteLLM config: {litellm_config_path} "
            f"({len(filtered_litellm['model_list'])} validated routes)"
        )
        if config_backup:
            print(f"LiteLLM backup: {config_backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
