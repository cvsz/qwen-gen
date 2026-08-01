#!/usr/bin/env python3
"""Qwen Omega ProMeta configuration generator and validator.

Generates Qwen Code settings using the current v4 modelProviders schema:
  modelProviders.<protocol> = [ModelConfig, ...]

No API key values are written to settings.json. Credentials are referenced by envKey.
"""

from __future__ import annotations

import argparse
import datetime as dt
import contextlib
import base64
import http.server
from html import escape as html_escape
from html.parser import HTMLParser
import json
import os
import pathlib
import mimetypes
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable, NoReturn

VERSION = "1.3.1"
DEFAULT_TIMEOUT = 30
DEFAULT_SETTINGS = pathlib.Path.home() / ".qwen" / "settings.json"
DEFAULT_ENV = pathlib.Path.home() / ".qwen" / ".env"
ROOT_ADMIN_EMAILS = (
    "cvsitem@gmail.com",
    "seaza@msn.com",
    "sea@zeaz.dev",
)


@dataclass(frozen=True)
class ProviderPreset:
    name: str
    protocol: str
    base_url: str
    env_key: str


class RequestError(RuntimeError):
    pass


PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        "OpenAI", "openai", "https://api.openai.com/v1", "OPENAI_API_KEY"
    ),
    "openrouter": ProviderPreset(
        "OpenRouter", "openai", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"
    ),
    "nvidia": ProviderPreset(
        "NVIDIA NIM", "openai", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"
    ),
    "groq": ProviderPreset(
        "Groq", "openai", "https://api.groq.com/openai/v1", "GROQ_API_KEY"
    ),
    "together": ProviderPreset(
        "Together AI", "openai", "https://api.together.xyz/v1", "TOGETHER_API_KEY"
    ),
    "fireworks": ProviderPreset(
        "Fireworks AI",
        "openai",
        "https://api.fireworks.ai/inference/v1",
        "FIREWORKS_API_KEY",
    ),
    "deepinfra": ProviderPreset(
        "DeepInfra",
        "openai",
        "https://api.deepinfra.com/v1/openai",
        "DEEPINFRA_API_KEY",
    ),
    "cerebras": ProviderPreset(
        "Cerebras", "openai", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"
    ),
    "mistral": ProviderPreset(
        "Mistral", "openai", "https://api.mistral.ai/v1", "MISTRAL_API_KEY"
    ),
    "dashscope": ProviderPreset(
        "Alibaba DashScope",
        "openai",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "DASHSCOPE_API_KEY",
    ),
    "ollama": ProviderPreset(
        "Ollama", "openai", "http://127.0.0.1:11434/v1", "OLLAMA_API_KEY"
    ),
    "litellm": ProviderPreset(
        "LiteLLM", "openai", "http://127.0.0.1:4000/v1", "LITELLM_API_KEY"
    ),
    "siliconflow": ProviderPreset(
        "SiliconFlow", "openai", "https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY"
    ),
    "featherless": ProviderPreset(
        "Featherless", "openai", "https://api.featherless.ai/v1", "FEATHERLESS_API_KEY"
    ),
    "novita": ProviderPreset(
        "Novita AI", "openai", "https://api.novita.ai/v3/openai", "NOVITA_API_KEY"
    ),
    "hyperbolic": ProviderPreset(
        "Hyperbolic", "openai", "https://api.hyperbolic.xyz/v1", "HYPERBOLIC_API_KEY"
    ),
    "anyscale": ProviderPreset(
        "Anyscale Endpoints",
        "openai",
        "https://api.endpoints.anyscale.com/v1",
        "ANYSCALE_API_KEY",
    ),
    "friendli": ProviderPreset(
        "FriendliAI", "openai", "https://inference.friendli.ai/v1", "FRIENDLI_TOKEN"
    ),
    "sambanova": ProviderPreset(
        "SambaNova", "openai", "https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY"
    ),
    "deepseek": ProviderPreset(
        "DeepSeek", "openai", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"
    ),
    "ai21": ProviderPreset(
        "AI21 Studio", "openai", "https://api.ai21.com/studio/v1", "AI21_API_KEY"
    ),
    "perplexity": ProviderPreset(
        "Perplexity", "openai", "https://api.perplexity.ai", "PERPLEXITY_API_KEY"
    ),
    "cloudflare": ProviderPreset(
        "Cloudflare Workers AI",
        "openai",
        "https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1",
        "CLOUDFLARE_API_KEY",
    ),
    "vllm": ProviderPreset(
        "vLLM", "openai", "http://127.0.0.1:8000/v1", "VLLM_API_KEY"
    ),
    "lmstudio": ProviderPreset(
        "LM Studio", "openai", "http://127.0.0.1:1234/v1", "LMSTUDIO_API_KEY"
    ),
    "nextchat": ProviderPreset(
        "NextChat", "openai", "http://127.0.0.1:3000/api/openai/v1", "NEXTCHAT_API_KEY"
    ),
    "open_webui": ProviderPreset(
        "Open WebUI", "openai", "http://127.0.0.1:8080/v1", "OPEN_WEBUI_API_KEY"
    ),
    "tgi": ProviderPreset(
        "Text Generation Inference", "openai", "http://127.0.0.1:8080/v1", "TGI_API_KEY"
    ),
    "sagemaker": ProviderPreset(
        "AWS SageMaker",
        "openai",
        "https://runtime.sagemaker.us-east-1.amazonaws.com",
        "AWS_ACCESS_KEY_ID",
    ),
    "bedrock": ProviderPreset(
        "AWS Bedrock Gateway",
        "openai",
        "http://127.0.0.1:8000/v1",
        "AWS_BEDROCK_API_KEY",
    ),
    "azure-openai": ProviderPreset(
        "Azure OpenAI",
        "openai",
        "https://{resource}.openai.azure.com/openai/deployments/{deployment}",
        "AZURE_OPENAI_API_KEY",
    ),
    "github": ProviderPreset(
        "GitHub Models",
        "openai",
        "https://models.inference.ai.azure.com",
        "GITHUB_TOKEN",
    ),
    "xai": ProviderPreset("xAI (Grok)", "openai", "https://api.x.ai/v1", "XAI_API_KEY"),
    "cohere": ProviderPreset(
        "Cohere", "openai", "https://api.cohere.com/v2", "COHERE_API_KEY"
    ),
    "yi": ProviderPreset(
        "01.AI (Lingyi Wan物)", "openai", "https://api.lingyiwanwu.com/v1", "YI_API_KEY"
    ),
    "zhipu": ProviderPreset(
        "Zhipu AI (GLM)",
        "openai",
        "https://open.bigmodel.cn/api/paas/v4",
        "ZHIPU_API_KEY",
    ),
    "moonshot": ProviderPreset(
        "Moonshot AI (Kimi)", "openai", "https://api.moonshot.cn/v1", "MOONSHOT_API_KEY"
    ),
    "baichuan": ProviderPreset(
        "Baichuan AI", "openai", "https://api.baichuan-ai.com/v1", "BAICHUAN_API_KEY"
    ),
    "minimax": ProviderPreset(
        "MiniMax", "openai", "https://api.minimax.chat/v1", "MINIMAX_API_KEY"
    ),
    "stepfun": ProviderPreset(
        "StepFun (阶跃星辰)", "openai", "https://api.stepfun.com/v1", "STEPFUN_API_KEY"
    ),
    "hunyuan": ProviderPreset(
        "Tencent Hunyuan",
        "openai",
        "https://api.hunyuan.tencentyun.com/v1",
        "HUNYUAN_API_KEY",
    ),
}

# ── Qwen Coder model catalog (backend → ordered list of recommended model IDs) ──
CODER_CATALOG: dict[str, list[str]] = {
    "ollama": [
        "qwen2.5-coder:32b-instruct-q4_K_M",
        "qwen2.5-coder:14b-instruct-q4_K_M",
        "qwen2.5-coder:7b-instruct-q4_K_M",
        "qwen2.5-coder:3b-instruct-q4_K_M",
        "qwen2.5-coder:1.5b-instruct-q4_K_M",
        "qwen3-coder:latest",
    ],
    "dashscope": [
        "qwen-coder-plus",
        "qwen-coder-turbo",
        "qwen2.5-coder-32b-instruct",
        "qwen2.5-coder-14b-instruct",
        "qwen2.5-coder-7b-instruct",
    ],
    "openrouter": [
        "qwen/qwen3-coder:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
    ],
    "siliconflow": [
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "Qwen/Qwen2.5-Coder-7B-Instruct",
    ],
    "litellm": [
        "qwen3-coder",
        "qwen2.5-coder-32b-instruct",
        "qwen2.5-coder-7b-instruct",
    ],
    "lmstudio": [
        "qwen2.5-coder-7b-instruct",
        "qwen2.5-coder-14b-instruct",
        "qwen2.5-coder-32b-instruct",
    ],
    "nextchat": [
        "qwen3-coder",
        "qwen2.5-coder-32b-instruct",
        "qwen2.5-coder-7b-instruct",
    ],
    "open_webui": [
        "qwen2.5-coder:7b-instruct-q4_K_M",
        "qwen2.5-coder:32b-instruct-q4_K_M",
        "qwen3-coder:latest",
    ],
}


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def die(message: str, code: int = 1) -> NoReturn:
    eprint(f"ERROR: {message}")
    raise SystemExit(code)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}")
    if not isinstance(value, dict):
        die(f"Top-level value in {path} must be a JSON object")
    return value


def atomic_write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def backup(path: pathlib.Path) -> pathlib.Path | None:
    if not path.exists():
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = path.with_name(f"{path.name}.backup.{stamp}")
    shutil.copy2(path, destination)
    os.chmod(destination, 0o600)
    return destination


SNAPSHOT_FORMAT = "qwen-omega.snapshot.v1"


def build_snapshot_bundle(settings: dict[str, Any], source_path: pathlib.Path) -> dict[str, Any]:
    return {
        "format": SNAPSHOT_FORMAT,
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": str(source_path),
        "settings": settings,
    }


def load_snapshot_settings(path: pathlib.Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload.get("settings"), dict):
        settings = payload["settings"]
        meta = {k: v for k, v in payload.items() if k != "settings"}
        return settings, meta
    return payload, {}


def path_mtime(path: pathlib.Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def snapshot_sync_cycle(
    settings_path: pathlib.Path,
    snapshot_path: pathlib.Path,
    *,
    mode: str = "mirror",
    dry_run: bool = False,
) -> str:
    settings_mtime = path_mtime(settings_path)
    snapshot_mtime = path_mtime(snapshot_path)

    if mode == "push" or (mode == "mirror" and settings_mtime >= snapshot_mtime):
        settings = load_json(settings_path)
        errors = validate_settings(settings)
        if errors:
            die("cannot export invalid settings:\n- " + "\n- ".join(errors))
        bundle = build_snapshot_bundle(settings, settings_path)
        if dry_run:
            json.dump(bundle, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return "push"
        snapshot_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return "push"

    settings, _meta = load_snapshot_settings(snapshot_path)
    if not isinstance(settings, dict):
        die("snapshot must contain a settings object")
    errors = validate_settings(settings)
    if errors:
        die("cannot import invalid settings:\n- " + "\n- ".join(errors))
    if dry_run:
        json.dump(
            {
                "format": SNAPSHOT_FORMAT,
                "settings": settings,
            },
            sys.stdout,
            indent=2,
            ensure_ascii=False,
        )
        print()
        return "pull"
    atomic_write_json(settings_path, settings)
    return "pull"


def normalize_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if not re.match(r"^https?://", url):
        die("base URL must start with http:// or https://")
    return url


def models_url(base_url: str) -> str:
    base = normalize_url(base_url)
    return f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"


def request_json(url: str, api_key: str, timeout: int, insecure: bool = False) -> Any:
    headers = {"Accept": "application/json", "User-Agent": f"qwen-omega/{VERSION}"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    context = (
        ssl._create_unverified_context() if insecure else ssl.create_default_context()
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:1000]
        raise RequestError(f"HTTP {exc.code} from {url}: {body}")
    except urllib.error.URLError as exc:
        raise RequestError(f"Cannot reach {url}: {exc.reason}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RequestError(f"Endpoint returned non-JSON data: {url}")


def safe_request_json(
    url: str, api_key: str, timeout: int, insecure: bool = False
) -> Any | None:
    headers = {"Accept": "application/json", "User-Agent": f"qwen-omega/{VERSION}"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    context = (
        ssl._create_unverified_context() if insecure else ssl.create_default_context()
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        with contextlib.suppress(Exception):
            exc.read()
            exc.close()
        return None
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def extract_model_objects(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        candidates = payload.get("data", payload.get("models", []))
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []
    result: list[dict[str, Any]] = []
    for item in candidates:
        if isinstance(item, str):
            result.append({"id": item})
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name")
            if isinstance(model_id, str) and model_id.strip():
                copied = dict(item)
                copied["id"] = model_id.strip()
                result.append(copied)
    return result


def decimal_zero(value: Any) -> bool:
    if value is None:
        return False
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


KNOWN_FREE_MODELS: list[str] = [
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "qwen/qwen3-coder:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "deepseek/deepseek-r1:free",
    "deepseek/deepseek-chat:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "google/gemma-2-9b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "openrouter/free",
]

LOCAL_FREE_CATALOG_PROVIDERS = {
    "ollama",
    "litellm",
    "lmstudio",
    "nextchat",
    "open_webui",
}

FREE_MODEL_HINT_ENV = {
    "nextchat": "NEXTCHAT_FREE_MODEL",
    "open_webui": "OPEN_WEBUI_FREE_MODEL",
    "openrouter": "OPENROUTER_FREE_MODEL",
    "gemini": "GEMINI_FREE_MODEL",
    "groq": "GROQ_FREE_MODEL",
}

BASE_URL_HINT_ENV = {
    "nextchat": "NEXTCHAT_BASE_URL",
    "open_webui": "OPEN_WEBUI_BASE_URL",
    "openrouter": "OPENROUTER_BASE_URL",
    "groq": "GROQ_BASE_URL",
    "mistral": "MISTRAL_BASE_URL",
    "fireworks": "FIREWORKS_BASE_URL",
    "dashscope": "DASHSCOPE_BASE_URL",
    "deepseek": "DEEPSEEK_BASE_URL",
    "ollama": "OLLAMA_BASE_URL",
    "litellm": "LITELLM_BASE_URL",
    "lmstudio": "LM_STUDIO_BASE_URL",
}


def explicitly_free(item: dict[str, Any]) -> bool:
    model_id = str(item.get("id", "")).lower().strip()
    if (
        model_id == "openrouter/free"
        or model_id.endswith(":free")
        or "/free" in model_id
    ):
        return True
    if item.get("is_free") is True or item.get("free") is True:
        return True
    pricing = item.get("pricing")
    if isinstance(pricing, dict):
        charge_fields = [
            pricing.get("prompt"),
            pricing.get("completion"),
            pricing.get("request"),
            pricing.get("image"),
            pricing.get("input"),
            pricing.get("output"),
        ]
        present = [v for v in charge_fields if v is not None]
        if bool(present) and all(decimal_zero(v) for v in present):
            return True
    return False


def unique_models(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda x: str(x.get("id", "")).lower()):
        model_id = str(item.get("id", "")).strip()
        if model_id and model_id not in seen:
            seen.add(model_id)
            output.append(item)
    return output


def display_name(model_id: str) -> str:
    return model_id.replace("/", " / ").replace("-", " ").replace("_", " ").strip()


def to_model_configs(
    items: list[dict[str, Any]],
    base_url: str,
    env_key: str,
    timeout_ms: int,
    max_retries: int,
    context_window: int | None,
) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for item in unique_models(items):
        raw_id = item.get("id")
        if raw_id is None:
            continue
        model_id = str(raw_id).strip()
        if not model_id:
            continue
        generation: dict[str, Any] = {
            "timeout": timeout_ms,
            "maxRetries": max_retries,
        }
        if context_window:
            generation["contextWindowSize"] = context_window
        config: dict[str, Any] = {
            "id": model_id,
            "name": display_name(model_id),
            "baseUrl": normalize_url(base_url),
            "envKey": env_key,
            "generationConfig": generation,
        }
        configs.append(config)
    return configs


def read_env_files(root: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not root.exists():
        return values
    paths: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for pattern in (".env*", "*.env"):
        for path in root.rglob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                paths.append(path)
    for path in sorted(paths, key=lambda p: (".example" in p.name, str(p))):
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not re.match(r"^[A-Z_][A-Z0-9_]*$", key):
                    continue
                value = value.strip()
                if (
                    len(value) >= 2
                    and value[0] == value[-1]
                    and value[0] in {"'", '"'}
                ):
                    value = value[1:-1]
                if value or key not in values:
                    values[key] = value
        except OSError:
            continue
    for key, value in os.environ.items():
        if value:
            values[key] = value
    return values


def provider_enabled(provider_key: str, preset: ProviderPreset, env: dict[str, str]) -> bool:
    if provider_key in LOCAL_FREE_CATALOG_PROVIDERS:
        return True
    if env.get(preset.env_key, "").strip():
        return True
    hint_key = FREE_MODEL_HINT_ENV.get(provider_key)
    return bool(hint_key and env.get(hint_key, "").strip())


def build_free_model_items(
    provider_key: str,
    preset: ProviderPreset,
    env: dict[str, str],
    timeout: int,
    insecure: bool,
    auto_fallback: bool,
) -> list[dict[str, Any]]:
    base_url = normalize_url(
        env.get(BASE_URL_HINT_ENV.get(provider_key, ""), preset.base_url)
    )
    api_key = env.get(preset.env_key, "").strip()

    if provider_key in LOCAL_FREE_CATALOG_PROVIDERS and provider_key in CODER_CATALOG:
        return [{"id": model_id} for model_id in CODER_CATALOG[provider_key]]

    if provider_key == "openrouter" and api_key:
        payload = safe_request_json(models_url(base_url), api_key, timeout, insecure)
        if payload is not None:
            discovered = [
                item for item in extract_model_objects(payload) if explicitly_free(item)
            ]
            if discovered:
                return discovered

    if api_key:
        payload = safe_request_json(models_url(base_url), api_key, timeout, insecure)
        if payload is not None:
            discovered = [
                item for item in extract_model_objects(payload) if explicitly_free(item)
            ]
            if discovered:
                return discovered

    hint_key = FREE_MODEL_HINT_ENV.get(provider_key)
    hint = env.get(hint_key, "").strip() if hint_key else ""
    if hint:
        return [{"id": hint}]

    if provider_key == "openrouter":
        return [{"id": model_id} for model_id in KNOWN_FREE_MODELS]

    if auto_fallback and provider_key in CODER_CATALOG:
        return [{"id": model_id} for model_id in CODER_CATALOG[provider_key]]

    return []


def is_placeholder_provider_entry(item: dict[str, Any]) -> bool:
    model_id = str(item.get("id", "")).strip()
    description = str(item.get("description", "")).strip()
    return model_id.endswith("-provider") and description.startswith("Provider preset for ")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "template"


def normalize_prompt_templates(settings: dict[str, Any]) -> list[dict[str, Any]]:
    templates = settings.get("promptTemplates")
    if templates is None:
        settings["promptTemplates"] = []
        return []
    if isinstance(templates, list):
        normalized: list[dict[str, Any]] = []
        for item in templates:
            if not isinstance(item, dict):
                continue
            template_id = item.get("id")
            content = item.get("content")
            if not isinstance(template_id, str) or not template_id.strip():
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            normalized.append(
                {
                    "id": template_id.strip(),
                    "name": str(item.get("name") or template_id).strip(),
                    "content": content,
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                }
            )
        settings["promptTemplates"] = normalized
        return normalized
    if isinstance(templates, dict):
        normalized = []
        for key, value in templates.items():
            if isinstance(value, str):
                normalized.append(
                    {"id": str(key).strip(), "name": str(key).strip(), "content": value}
                )
            elif isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("content"), str) and item["content"].strip():
                    normalized.append(item)
        settings["promptTemplates"] = normalized
        return normalized
    settings["promptTemplates"] = []
    return []


def normalize_skills(settings: dict[str, Any]) -> list[dict[str, Any]]:
    skills = settings.get("skills")
    if skills is None:
        settings["skills"] = []
        return []
    if isinstance(skills, list):
        normalized: list[dict[str, Any]] = []
        for item in skills:
            if not isinstance(item, dict):
                continue
            skill_id = item.get("id")
            name = item.get("name")
            content = item.get("content", item.get("instructions"))
            if not isinstance(skill_id, str) or not skill_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = skill_id.strip()
            if not isinstance(content, str) or not content.strip():
                continue
            normalized_item: dict[str, Any] = {
                "id": skill_id.strip(),
                "name": str(name).strip(),
                "content": content,
            }
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized_item["description"] = str(item["description"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized_item["tags"] = tags
            if item.get("pinned") is not None:
                normalized_item["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings["skills"] = normalized
        return normalized
    if isinstance(skills, dict):
        normalized = []
        for key, value in skills.items():
            if isinstance(value, str):
                normalized.append(
                    {"id": str(key).strip(), "name": str(key).strip(), "content": value}
                )
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("content"), str) and item["content"].strip():
                    normalized.append(item)
                elif isinstance(item.get("instructions"), str) and item["instructions"].strip():
                    item["content"] = item.pop("instructions")
                    normalized.append(item)
        settings["skills"] = normalized
        return normalized
    settings["skills"] = []
    return []


def normalize_plugins(settings: dict[str, Any]) -> list[dict[str, Any]]:
    plugins = settings.get("plugins")
    if plugins is None:
        settings["plugins"] = []
        return []
    if isinstance(plugins, list):
        normalized: list[dict[str, Any]] = []
        for item in plugins:
            if not isinstance(item, dict):
                continue
            plugin_id = item.get("id")
            name = item.get("name")
            content = item.get("content", item.get("instructions"))
            if not isinstance(plugin_id, str) or not plugin_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = plugin_id.strip()
            if not isinstance(content, str) or not content.strip():
                continue
            normalized_item: dict[str, Any] = {
                "id": plugin_id.strip(),
                "name": str(name).strip(),
                "content": content,
            }
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized_item["description"] = str(item["description"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized_item["tags"] = tags
            for key in ("tools", "knowledge", "skills", "events"):
                values = item.get(key)
                if isinstance(values, list):
                    cleaned = [str(entry).strip() for entry in values if str(entry).strip()]
                    if cleaned:
                        normalized_item[key] = cleaned
            if isinstance(item.get("url"), str) and str(item.get("url")).strip():
                normalized_item["url"] = str(item["url"]).strip()
            if item.get("enabled") is not None:
                normalized_item["enabled"] = bool(item["enabled"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings["plugins"] = normalized
        return normalized
    if isinstance(plugins, dict):
        normalized = []
        for key, value in plugins.items():
            if isinstance(value, str):
                normalized.append(
                    {"id": str(key).strip(), "name": str(key).strip(), "content": value}
                )
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("content"), str) and item["content"].strip():
                    normalized.append(item)
                elif isinstance(item.get("instructions"), str) and item["instructions"].strip():
                    item["content"] = item.pop("instructions")
                    normalized.append(item)
        settings["plugins"] = normalized
        return normalized
    settings["plugins"] = []
    return []


def normalize_pipelines(settings: dict[str, Any]) -> list[dict[str, Any]]:
    pipelines = settings.get("pipelines")
    if pipelines is None:
        settings["pipelines"] = []
        return []
    if isinstance(pipelines, list):
        normalized: list[dict[str, Any]] = []
        for item in pipelines:
            if not isinstance(item, dict):
                continue
            pipeline_id = item.get("id")
            name = item.get("name")
            content = item.get("content", item.get("instructions"))
            if not isinstance(pipeline_id, str) or not pipeline_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = pipeline_id.strip()
            if not isinstance(content, str) or not content.strip():
                continue
            normalized_item: dict[str, Any] = {
                "id": pipeline_id.strip(),
                "name": str(name).strip(),
                "content": content,
            }
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized_item["description"] = str(item["description"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized_item["tags"] = tags
            for key in ("tools", "knowledge", "skills", "events"):
                values = item.get(key)
                if isinstance(values, list):
                    cleaned = [str(entry).strip() for entry in values if str(entry).strip()]
                    if cleaned:
                        normalized_item[key] = cleaned
            if isinstance(item.get("url"), str) and str(item["url"]).strip():
                normalized_item["url"] = str(item["url"]).strip()
            if item.get("enabled") is not None:
                normalized_item["enabled"] = bool(item["enabled"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings["pipelines"] = normalized
        return normalized
    if isinstance(pipelines, dict):
        normalized = []
        for key, value in pipelines.items():
            if isinstance(value, str):
                normalized.append(
                    {"id": str(key).strip(), "name": str(key).strip(), "content": value}
                )
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("content"), str) and item["content"].strip():
                    normalized.append(item)
                elif isinstance(item.get("instructions"), str) and item["instructions"].strip():
                    item["content"] = item.pop("instructions")
                    normalized.append(item)
        settings["pipelines"] = normalized
        return normalized
    settings["pipelines"] = []
    return []


def normalize_tool_servers(settings: dict[str, Any]) -> list[dict[str, Any]]:
    servers = settings.get("toolServers")
    if servers is None:
        settings["toolServers"] = []
        return []
    if isinstance(servers, list):
        normalized: list[dict[str, Any]] = []
        for item in servers:
            if not isinstance(item, dict):
                continue
            server_id = item.get("id")
            name = item.get("name")
            if not isinstance(server_id, str) or not server_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = server_id.strip()
            normalized.append(
                {
                    "id": server_id.strip(),
                    "name": str(name).strip(),
                    **(
                        {"type": str(item["type"]).strip()}
                        if isinstance(item.get("type"), str) and str(item.get("type")).strip()
                        else {}
                    ),
                    **(
                        {
                            "endpoint": str(item["endpoint"]).strip()
                        }
                        if isinstance(item.get("endpoint"), str)
                        and str(item.get("endpoint")).strip()
                        else (
                            {
                                "endpoint": str(item["url"]).strip()
                            }
                            if isinstance(item.get("url"), str)
                            and str(item.get("url")).strip()
                            else {}
                        )
                    ),
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"auth": item["auth"]}
                        if item.get("auth") is not None
                        else {}
                    ),
                    **(
                        {"enabled": bool(item["enabled"])}
                        if item.get("enabled") is not None
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                }
            )
        settings["toolServers"] = normalized
        return normalized
    if isinstance(servers, dict):
        normalized = []
        for key, value in servers.items():
            if isinstance(value, str):
                normalized.append({"id": str(key).strip(), "name": str(key).strip(), "endpoint": value})
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("endpoint"), str) and item["endpoint"].strip():
                    normalized.append(item)
                elif isinstance(item.get("url"), str) and item["url"].strip():
                    item["endpoint"] = item.pop("url")
                    normalized.append(item)
        settings["toolServers"] = normalized
        return normalized
    settings["toolServers"] = []
    return []


def normalize_knowledge_bases(settings: dict[str, Any]) -> list[dict[str, Any]]:
    bases = settings.get("knowledgeBases")
    if bases is None:
        settings["knowledgeBases"] = []
        return []
    if isinstance(bases, list):
        normalized: list[dict[str, Any]] = []
        for item in bases:
            if not isinstance(item, dict):
                continue
            base_id = item.get("id")
            name = item.get("name")
            if not isinstance(base_id, str) or not base_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = base_id.strip()
            normalized.append(
                {
                    "id": base_id.strip(),
                    "name": str(name).strip(),
                    **(
                        {"sourceDir": str(item["sourceDir"]).strip()}
                        if isinstance(item.get("sourceDir"), str)
                        and str(item.get("sourceDir")).strip()
                        else {}
                    ),
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                    **(
                        {"enabled": bool(item["enabled"])}
                        if item.get("enabled") is not None
                        else {}
                    ),
                    **(
                        {"sources": item["sources"]}
                        if item.get("sources") is not None
                        else {}
                    ),
                }
            )
        settings["knowledgeBases"] = normalized
        return normalized
    if isinstance(bases, dict):
        normalized = []
        for key, value in bases.items():
            if isinstance(value, str):
                normalized.append({"id": str(key).strip(), "name": str(key).strip(), "sourceDir": value})
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("sourceDir"), str) and item["sourceDir"].strip():
                    normalized.append(item)
        settings["knowledgeBases"] = normalized
        return normalized
    settings["knowledgeBases"] = []
    return []


def normalize_knowledge_indexes(settings: dict[str, Any]) -> list[dict[str, Any]]:
    indexes = settings.get("knowledgeIndexes")
    if indexes is None:
        settings["knowledgeIndexes"] = []
        return []
    if isinstance(indexes, list):
        normalized: list[dict[str, Any]] = []
        for item in indexes:
            if not isinstance(item, dict):
                continue
            index_id = item.get("id")
            base_id = item.get("baseId")
            if not isinstance(index_id, str) or not index_id.strip():
                continue
            if not isinstance(base_id, str) or not base_id.strip():
                continue
            normalized.append(
                {
                    "id": index_id.strip(),
                    "baseId": base_id.strip(),
                    **(
                        {"path": str(item["path"]).strip()}
                        if isinstance(item.get("path"), str) and str(item.get("path")).strip()
                        else {}
                    ),
                    **(
                        {"sourceDir": str(item["sourceDir"]).strip()}
                        if isinstance(item.get("sourceDir"), str)
                        and str(item.get("sourceDir")).strip()
                        else {}
                    ),
                    **(
                        {"chunkSize": int(item["chunkSize"])}
                        if item.get("chunkSize") is not None
                        else {}
                    ),
                    **(
                        {"overlap": int(item["overlap"])}
                        if item.get("overlap") is not None
                        else {}
                    ),
                    **(
                        {"documents": item["documents"]}
                        if item.get("documents") is not None
                        else {}
                    ),
                }
            )
        settings["knowledgeIndexes"] = normalized
        return normalized
    settings["knowledgeIndexes"] = []
    return []


def split_text_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    if chunk_size <= 0:
        chunk_size = 2000
    if overlap < 0:
        overlap = 0
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 5)
    chunks: list[str] = []
    start = 0
    length = len(clean)
    while start < length:
        end = min(length, start + chunk_size)
        chunks.append(clean[start:end].strip())
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def scan_knowledge_documents(source_dir: pathlib.Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    if not source_dir.exists():
        die(f"knowledge source directory not found: {source_dir}")
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".md", ".markdown", ".txt", ".json", ".html", ".htm", ".csv"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if not content.strip():
            continue
        documents.append(
            {
                "id": slugify(path.relative_to(source_dir).as_posix()),
                "path": str(path),
                "relativePath": str(path.relative_to(source_dir)),
                "title": path.stem,
                "kind": suffix.lstrip("."),
                "size": path.stat().st_size,
                "chunks": [],
                "content": content,
            }
        )
    return documents


def build_knowledge_index(
    base_id: str,
    source_dir: pathlib.Path,
    chunk_size: int,
    overlap: int,
) -> dict[str, Any]:
    documents = scan_knowledge_documents(source_dir)
    return build_knowledge_index_from_documents(
        base_id, str(source_dir), documents, chunk_size, overlap
    )


def build_knowledge_index_from_documents(
    base_id: str,
    source_label: str,
    documents: list[dict[str, Any]],
    chunk_size: int,
    overlap: int,
) -> dict[str, Any]:
    indexed_documents: list[dict[str, Any]] = []
    total_chunks = 0
    for doc in documents:
        chunks = split_text_chunks(str(doc.get("content", "")), chunk_size, overlap)
        doc_id = str(doc.get("id") or slugify(str(doc.get("title") or "document")))
        doc_path = str(doc.get("path") or doc.get("source") or "")
        relative_path = str(doc.get("relativePath") or doc.get("name") or doc.get("title") or doc_id)
        title = str(doc.get("title") or doc.get("name") or doc_id)
        kind = str(doc.get("kind") or "").strip()
        size = doc.get("size")
        if not isinstance(size, int):
            try:
                size = int(size) if size is not None else 0
            except (TypeError, ValueError):
                size = 0
        chunk_items = [
            {
                "id": f"{doc_id}-{idx + 1}",
                "index": idx + 1,
                "text": chunk,
            }
            for idx, chunk in enumerate(chunks)
        ]
        total_chunks += len(chunk_items)
        indexed_documents.append(
            {
                "id": doc_id,
                "path": doc_path,
                "relativePath": relative_path,
                "title": title,
                "kind": kind,
                "size": size,
                "chunkCount": len(chunk_items),
                "chunks": chunk_items,
            }
        )
    return {
        "id": slugify(f"{base_id}-index"),
        "baseId": base_id,
        "sourceDir": source_label,
        "chunkSize": chunk_size,
        "overlap": overlap,
        "documentCount": len(indexed_documents),
        "chunkCount": total_chunks,
        "documents": indexed_documents,
    }


class _WebTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title: str = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_title and not self.title:
            self.title = text
        self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts).strip()


class _WebSearchResultExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._in_anchor = False
        self._current_href = ""
        self._current_text: list[str] = []
        self._current_title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = ""
        for key, value in attrs:
            if key.lower() == "href" and value:
                href = value
                break
        if href:
            self._in_anchor = True
            self._current_href = href
            self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._in_anchor:
            return
        text = " ".join(part for part in self._current_text if part).strip()
        title = self._current_title or text or self._current_href
        if self._current_href:
            self.results.append(
                {
                    "title": title,
                    "url": self._current_href,
                    "snippet": text,
                }
            )
        self._in_anchor = False
        self._current_href = ""
        self._current_text = []
        self._current_title = ""

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            text = data.strip()
            if text:
                self._current_text.append(text)


WEB_SEARCH_PROVIDERS: dict[str, dict[str, str]] = {
    "duckduckgo": {
        "name": "DuckDuckGo HTML",
        "description": "Free HTML search endpoint with result pages that can be scraped.",
        "engine_url": "https://html.duckduckgo.com/html/?q={query}",
        "env_key": "",
    },
    "brave": {
        "name": "Brave Search",
        "description": "Classic web search API returning search results as JSON.",
        "engine_url": "https://api.search.brave.com/res/v1/web/search?q={query}&count={count}",
        "env_key": "BRAVE_SEARCH_API_KEY",
    },
    "external": {
        "name": "External Search API",
        "description": "Custom self-hosted search endpoint compatible with Open WebUI's external provider.",
        "engine_url": "",
        "env_key": "",
    },
}


def _resolve_web_search_provider(
    provider: str | None,
    engine_url: str | None,
) -> tuple[str, str, str]:
    if provider:
        info = WEB_SEARCH_PROVIDERS.get(provider)
        if info is None:
            die(f"unsupported web search provider: {provider}")
        resolved = engine_url or info.get("engine_url", "")
        if not resolved:
            die(f"provider '{provider}' requires --engine-url")
        return provider, resolved, info.get("env_key", "")
    if engine_url:
        return "duckduckgo", engine_url, ""
    return "duckduckgo", WEB_SEARCH_PROVIDERS["duckduckgo"]["engine_url"], ""


def _normalize_web_search_results(payload: Any, limit: int) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            candidates = payload["results"]
        elif isinstance(payload.get("web"), dict) and isinstance(payload["web"].get("results"), list):
            candidates = payload["web"]["results"]
        elif isinstance(payload.get("data"), list):
            candidates = payload["data"]
        else:
            candidates = []
    else:
        candidates = []

    for item in candidates:
        if not isinstance(item, dict):
            continue
        url_value = str(item.get("url") or item.get("link") or item.get("href") or "").strip()
        title = str(item.get("title") or item.get("name") or url_value or "").strip()
        snippet = str(item.get("snippet") or item.get("description") or item.get("content") or "").strip()
        if not url_value:
            continue
        items.append({"title": title, "url": url_value, "snippet": snippet})
        if len(items) >= limit:
            break
    return items


def fetch_web_document(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
            "User-Agent": f"qwen-omega/{VERSION}",
        },
        method="GET",
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
    text = raw.decode("utf-8", "replace")
    kind = "html" if "html" in content_type.lower() or "<html" in text.lower() else "text"
    title = ""
    body = text
    if kind == "html":
        extractor = _WebTextExtractor()
        extractor.feed(text)
        extractor.close()
        title = extractor.title or ""
        body = extractor.text() or text
    if not title:
        title = str(url).rstrip("/").rsplit("/", 1)[-1] or url
    return {
        "id": slugify(title or url),
        "name": title,
        "content": body.strip(),
        "path": url,
        "kind": kind,
        "description": f"Fetched from {url}",
        "size": len(raw),
    }


def fetch_web_search_results(
    query: str,
    *,
    provider: str = "duckduckgo",
    engine_url: str = "https://html.duckduckgo.com/html/?q={query}",
    api_key: str = "",
    method: str = "GET",
    timeout: int = DEFAULT_TIMEOUT,
    limit: int = 10,
) -> list[dict[str, str]]:
    resolved_method = method.upper()
    if provider == "external":
        body = json.dumps({"query": query, "count": limit}).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"qwen-omega/{VERSION}",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(engine_url, data=body, headers=headers, method="POST")
        context = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
            raw = response.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return _normalize_web_search_results(payload, limit)

    if provider == "brave":
        url = engine_url.format(
            query=urllib.parse.quote_plus(query),
            q=urllib.parse.quote_plus(query),
            count=limit,
        )
        headers = {
            "Accept": "application/json",
            "User-Agent": f"qwen-omega/{VERSION}",
        }
        if api_key:
            headers["X-Subscription-Token"] = api_key
        req = urllib.request.Request(url, headers=headers, method="GET")
        context = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
            raw = response.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return _normalize_web_search_results(payload, limit)

    url = engine_url.format(
        query=urllib.parse.quote_plus(query),
        q=urllib.parse.quote_plus(query),
        count=limit,
    )
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
            "User-Agent": f"qwen-omega/{VERSION}",
        },
        method=resolved_method if resolved_method in {"GET", "POST"} else "GET",
    )
    context = ssl.create_default_context()
    if resolved_method == "POST":
        req.data = json.dumps({"query": query, "count": limit}).encode("utf-8")
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
    if "json" in content_type.lower() or raw[:1] in {b"{", b"["}:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return _normalize_web_search_results(payload, limit)
    text = raw.decode("utf-8", "replace")
    extractor = _WebSearchResultExtractor()
    extractor.feed(text)
    extractor.close()
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in extractor.results:
        url_value = item.get("url", "").strip()
        if not url_value or url_value in seen:
            continue
        seen.add(url_value)
        results.append(
            {
                "title": item.get("title", "").strip(),
                "url": url_value,
                "snippet": item.get("snippet", "").strip(),
            }
        )
        if len(results) >= limit:
            break
    return results


def fetch_web_search_results_chain(
    query: str,
    providers: list[str],
    *,
    engine_url: str | None = None,
    api_key: str = "",
    timeout: int = DEFAULT_TIMEOUT,
    limit: int = 10,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    ordered_providers = [provider for provider in providers if provider]
    if not ordered_providers:
        ordered_providers = ["duckduckgo"]
    for index, provider in enumerate(ordered_providers):
        resolved_engine_url = engine_url if index == 0 else None
        try:
            resolved_provider, resolved_engine_url, resolved_env_key = _resolve_web_search_provider(
                provider,
                resolved_engine_url,
            )
            resolved_api_key = api_key or (
                os.environ.get(resolved_env_key, "") if resolved_env_key else ""
            )
            results = fetch_web_search_results(
                query,
                provider=resolved_provider,
                engine_url=resolved_engine_url,
                api_key=resolved_api_key,
                timeout=timeout,
                limit=limit,
            )
        except Exception as exc:
            eprint(f"WARNING: web search provider {provider} failed: {exc}")
            continue
        for item in results:
            url_value = str(item.get("url", "")).strip()
            if not url_value or url_value in seen_urls:
                continue
            merged.append(item)
            seen_urls.add(url_value)
            if len(merged) >= limit:
                return merged
    return merged


def _save_web_search_results_to_settings(
    settings: dict[str, Any],
    query: str,
    results: list[dict[str, str]],
    *,
    base_id: str | None = None,
    knowledge_name: str | None = None,
    description: str | None = None,
    save_limit: int = 5,
    chunk_size: int = 2000,
    overlap: int = 200,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    selected_urls = [str(item.get("url", "")).strip() for item in results[:save_limit] if str(item.get("url", "")).strip()]
    if not selected_urls:
        die("no web pages could be selected for knowledge saving")

    documents: list[dict[str, Any]] = []
    for url in selected_urls:
        try:
            documents.append(fetch_web_document(url, timeout))
        except (urllib.error.URLError, TimeoutError, ValueError, UnicodeError) as exc:
            eprint(f"WARNING: unable to fetch {url}: {exc}")
    if not documents:
        die("no web pages could be fetched for knowledge saving")

    resolved_base_id = base_id or slugify(query)
    index = build_knowledge_index_from_documents(
        resolved_base_id,
        ", ".join(selected_urls),
        documents,
        chunk_size,
        overlap,
    )

    indexes = settings.setdefault("knowledgeIndexes", [])
    if not isinstance(indexes, list):
        die("knowledgeIndexes must be an array")
    indexes[:] = [item for item in indexes if str(item.get("baseId")) != resolved_base_id]
    indexes.append(index)
    indexes.sort(key=lambda x: str(x.get("id", "")).lower())

    bases = settings.setdefault("knowledgeBases", [])
    if not isinstance(bases, list):
        die("knowledgeBases must be an array")
    bases[:] = [b for b in bases if str(b.get("id")) != resolved_base_id]
    bases.append(
        {
            "id": resolved_base_id,
            "name": knowledge_name or documents[0].get("name") or resolved_base_id,
            "sourceDir": ", ".join(selected_urls),
            "description": description or f"Saved web search results for {query}",
            "enabled": True,
            "sources": selected_urls,
        }
    )
    bases.sort(key=lambda x: str(x.get("id", "")).lower())
    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))
    return {
        "knowledgeIndex": index,
        "knowledgeBases": bases,
        "knowledgeIndexes": indexes,
        "selectedUrls": selected_urls,
    }


def _normalize_index_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if "documents" in payload:
            return [payload]
        payload = payload.get("knowledgeIndexes", payload.get("indexes", payload.get("items", [])))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _load_knowledge_indexes_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        indexes: list[dict[str, Any]] = []
        manifest = source / "manifest.json"
        if manifest.exists():
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            if payload:
                indexes.extend(_normalize_index_payload(payload))
        for path in sorted(source.glob("*.json")):
            if path.name == "manifest.json":
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            indexes.extend(_normalize_index_payload(payload))
        return indexes
    payload = json.loads(source.read_text(encoding="utf-8"))
    return _normalize_index_payload(payload)


def _load_knowledge_indexes_from_settings(settings: dict[str, Any]) -> list[dict[str, Any]]:
    indexes = settings.get("knowledgeIndexes", [])
    if isinstance(indexes, list):
        return [item for item in indexes if isinstance(item, dict)]
    return []


def _is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _refresh_knowledge_base_documents(
    base: dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[str, list[dict[str, Any]]]:
    sources = base.get("sources")
    cleaned_sources: list[str] = []
    if isinstance(sources, list):
        cleaned_sources = [str(source).strip() for source in sources if str(source).strip()]

    if cleaned_sources and all(_is_http_url(source) for source in cleaned_sources):
        documents: list[dict[str, Any]] = []
        for url in cleaned_sources:
            documents.append(fetch_web_document(url, timeout))
        return ", ".join(cleaned_sources), documents

    source_dir = base.get("sourceDir")
    if isinstance(source_dir, str) and source_dir.strip():
        source_path = pathlib.Path(source_dir).expanduser()
        if source_path.exists() and source_path.is_dir():
            return str(source_path), scan_knowledge_documents(source_path)

    if cleaned_sources:
        if len(cleaned_sources) == 1:
            source_path = pathlib.Path(cleaned_sources[0]).expanduser()
            if source_path.exists() and source_path.is_dir():
                return str(source_path), scan_knowledge_documents(source_path)
        raise ValueError("knowledge base source is not available for refresh")

    raise ValueError("knowledge base source is not available for refresh")


def _refresh_knowledge_base_entry(
    base: dict[str, Any],
    base_id: str,
    chunk_size: int,
    overlap: int,
    timeout: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    source_label, documents = _refresh_knowledge_base_documents(base, timeout)
    index = build_knowledge_index_from_documents(
        base_id,
        source_label,
        documents,
        chunk_size,
        overlap,
    )
    refreshed_base = dict(base)
    refreshed_base["id"] = base_id
    refreshed_base.setdefault("name", base_id)
    refreshed_base["sourceDir"] = source_label
    refreshed_base["enabled"] = bool(base.get("enabled", True))
    if isinstance(base.get("sources"), list):
        refreshed_sources = [
            str(source).strip() for source in base.get("sources", []) if str(source).strip()
        ]
        refreshed_base["sources"] = refreshed_sources or [source_label]
    else:
        refreshed_base["sources"] = [source_label]
    return source_label, index, refreshed_base


def _search_knowledge_indexes(
    indexes: list[dict[str, Any]], query: str, base_id: str | None = None
) -> list[dict[str, Any]]:
    term = query.strip().lower()
    if not term:
        return []
    terms = [part for part in re.split(r"\s+", term) if part]
    matches: list[dict[str, Any]] = []
    for index in indexes:
        if base_id and str(index.get("baseId")) != base_id:
            continue
        documents = index.get("documents", [])
        if not isinstance(documents, list):
            continue
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            doc_text_parts = [
                str(doc.get("title", "")),
                str(doc.get("relativePath", "")),
                str(doc.get("path", "")),
            ]
            chunks = doc.get("chunks", [])
            if isinstance(chunks, list):
                doc_text_parts.extend(
                    str(chunk.get("text", "")) for chunk in chunks if isinstance(chunk, dict)
                )
            haystack = "\n".join(doc_text_parts).lower()
            if not haystack:
                continue
            score = sum(haystack.count(term_item) for term_item in terms)
            if score <= 0:
                continue
            snippet = ""
            if isinstance(chunks, list):
                for chunk in chunks:
                    if not isinstance(chunk, dict):
                        continue
                    text = str(chunk.get("text", "")).strip()
                    if not text:
                        continue
                    text_lower = text.lower()
                    if any(term_item in text_lower for term_item in terms):
                        snippet = text
                        break
            if not snippet:
                snippet = str(doc.get("relativePath") or doc.get("title") or doc.get("id") or "")
            matches.append(
                {
                    "indexId": str(index.get("id") or ""),
                    "baseId": str(index.get("baseId") or ""),
                    "documentId": str(doc.get("id") or ""),
                    "title": str(doc.get("title") or doc.get("id") or ""),
                    "relativePath": str(doc.get("relativePath") or ""),
                    "chunkCount": doc.get("chunkCount"),
                    "score": score,
                    "snippet": snippet,
                }
            )
    matches.sort(key=lambda item: (-int(item.get("score", 0)), item["title"].lower(), item["documentId"]))
    return matches


def normalize_notes(settings: dict[str, Any]) -> list[dict[str, Any]]:
    notes = settings.get("notes")
    if notes is None:
        settings["notes"] = []
        return []
    if isinstance(notes, list):
        normalized: list[dict[str, Any]] = []
        for item in notes:
            if not isinstance(item, dict):
                continue
            note_id = item.get("id")
            title = item.get("title")
            body = item.get("body", item.get("content"))
            if not isinstance(note_id, str) or not note_id.strip():
                continue
            if not isinstance(title, str) or not title.strip():
                title = note_id.strip()
            if not isinstance(body, str) or not body.strip():
                continue
            normalized.append(
                {
                    "id": note_id.strip(),
                    "title": str(title).strip(),
                    "body": body,
                    **(
                        {"files": [str(entry).strip() for entry in item.get("files", item.get("attachments", [])) if str(entry).strip()]}
                        if isinstance(item.get("files", item.get("attachments")), list)
                        else {}
                    ),
                    **(
                        {"images": [str(entry).strip() for entry in item.get("images", []) if str(entry).strip()]}
                        if isinstance(item.get("images"), list)
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                    **(
                        {"pinned": bool(item["pinned"])}
                        if item.get("pinned") is not None
                        else {}
                    ),
                    **(
                        {"archived": bool(item["archived"])}
                        if item.get("archived") is not None
                        else {}
                    ),
                }
            )
        settings["notes"] = normalized
        return normalized
    if isinstance(notes, dict):
        normalized = []
        for key, value in notes.items():
            if isinstance(value, str):
                normalized.append({"id": str(key).strip(), "title": str(key).strip(), "body": value})
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("title", str(key).strip())
                if isinstance(item.get("body"), str) and item["body"].strip():
                    if isinstance(item.get("files", item.get("attachments")), list):
                        item["files"] = [
                            str(entry).strip()
                            for entry in item.get("files", item.get("attachments", []))
                            if str(entry).strip()
                        ]
                    if isinstance(item.get("images"), list):
                        item["images"] = [str(entry).strip() for entry in item.get("images", []) if str(entry).strip()]
                    normalized.append(item)
                elif isinstance(item.get("content"), str) and item["content"].strip():
                    item["body"] = item.pop("content")
                    if isinstance(item.get("files", item.get("attachments")), list):
                        item["files"] = [
                            str(entry).strip()
                            for entry in item.get("files", item.get("attachments", []))
                            if str(entry).strip()
                        ]
                    if isinstance(item.get("images"), list):
                        item["images"] = [str(entry).strip() for entry in item.get("images", []) if str(entry).strip()]
                    normalized.append(item)
        settings["notes"] = normalized
        return normalized
    settings["notes"] = []
    return []


def normalize_artifacts(settings: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = settings.get("artifacts")
    if artifacts is None:
        settings["artifacts"] = []
        return []
    if isinstance(artifacts, list):
        normalized: list[dict[str, Any]] = []
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            artifact_id = item.get("id")
            title = item.get("title")
            content = item.get("content")
            if not isinstance(artifact_id, str) or not artifact_id.strip():
                continue
            if not isinstance(title, str) or not title.strip():
                title = artifact_id.strip()
            if not isinstance(content, str) or not content.strip():
                continue
            normalized.append(
                {
                    "id": artifact_id.strip(),
                    "title": str(title).strip(),
                    "content": content,
                    **(
                        {"kind": str(item["kind"]).strip()}
                        if isinstance(item.get("kind"), str) and str(item.get("kind")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                }
            )
        settings["artifacts"] = normalized
        return normalized
    if isinstance(artifacts, dict):
        normalized = []
        for key, value in artifacts.items():
            if isinstance(value, str):
                normalized.append({"id": str(key).strip(), "title": str(key).strip(), "content": value})
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("title", str(key).strip())
                if isinstance(item.get("content"), str) and item["content"].strip():
                    normalized.append(item)
        settings["artifacts"] = normalized
        return normalized
    settings["artifacts"] = []
    return []


def normalize_conversations(settings: dict[str, Any]) -> list[dict[str, Any]]:
    conversations = settings.get("conversations")
    if conversations is None:
        settings["conversations"] = []
        return []
    if isinstance(conversations, list):
        normalized: list[dict[str, Any]] = []
        for item in conversations:
            if not isinstance(item, dict):
                continue
            convo_id = item.get("id")
            title = item.get("title")
            transcript = item.get("transcript", item.get("content"))
            messages = item.get("messages")
            if not isinstance(convo_id, str) or not convo_id.strip():
                continue
            if not isinstance(title, str) or not title.strip():
                title = convo_id.strip()
            if not isinstance(transcript, str) or not transcript.strip():
                transcript = ""
            normalized_item: dict[str, Any] = {
                "id": convo_id.strip(),
                "title": str(title).strip(),
                "transcript": transcript,
            }
            system_prompt = item.get("systemPrompt", item.get("instructions", item.get("prompt")))
            if isinstance(system_prompt, str) and system_prompt.strip():
                normalized_item["systemPrompt"] = system_prompt.strip()
            knowledge = item.get("knowledge")
            if isinstance(knowledge, list):
                values = [str(entry).strip() for entry in knowledge if str(entry).strip()]
                if values:
                    normalized_item["knowledge"] = values
            attachments = item.get("files", item.get("attachments"))
            if isinstance(attachments, list):
                values = [str(entry).strip() for entry in attachments if str(entry).strip()]
                if values:
                    normalized_item["files"] = values
            image_attachments = item.get("images")
            if isinstance(image_attachments, list):
                values = [str(entry).strip() for entry in image_attachments if str(entry).strip()]
                if values:
                    normalized_item["images"] = values
            if isinstance(messages, list):
                normalized_messages: list[dict[str, Any]] = []
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role")
                    content = msg.get("content")
                    if not isinstance(role, str) or not role.strip():
                        continue
                    if not isinstance(content, str) or not content.strip():
                        continue
                    normalized_messages.append(
                        {
                            "role": role.strip(),
                            "content": content,
                        }
                    )
                if normalized_messages:
                    normalized_item["messages"] = normalized_messages
            usage = item.get("usage")
            if isinstance(usage, dict) and usage:
                normalized_item["usage"] = dict(usage)
            if isinstance(item.get("tags"), list):
                normalized_item["tags"] = [
                    str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()
                ]
            compare_models = item.get("compareModels")
            if isinstance(compare_models, list):
                values = [str(entry).strip() for entry in compare_models if str(entry).strip()]
                if values:
                    normalized_item["compareModels"] = values
            folder_id = item.get("folderId", item.get("folder"))
            if isinstance(folder_id, str) and folder_id.strip():
                normalized_item["folderId"] = folder_id.strip()
            if item.get("pinned") is not None:
                normalized_item["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings["conversations"] = normalized
        return normalized
    if isinstance(conversations, dict):
        normalized = []
        for key, value in conversations.items():
            if isinstance(value, str):
                normalized.append({"id": str(key).strip(), "title": str(key).strip(), "transcript": value})
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("title", str(key).strip())
                if isinstance(item.get("transcript"), str) and item["transcript"].strip():
                    normalized.append(item)
                elif isinstance(item.get("content"), str) and item["content"].strip():
                    item["transcript"] = item.pop("content")
                    normalized.append(item)
        settings["conversations"] = normalized
        return normalized
    settings["conversations"] = []
    return []


def normalize_channels(settings: dict[str, Any]) -> list[dict[str, Any]]:
    channels = settings.get("channels")
    if channels is None:
        settings["channels"] = []
        return []
    if isinstance(channels, list):
        normalized: list[dict[str, Any]] = []
        for item in channels:
            if not isinstance(item, dict):
                continue
            channel_id = item.get("id")
            title = item.get("title", item.get("name"))
            transcript = item.get("transcript", item.get("content"))
            messages = item.get("messages")
            if not isinstance(channel_id, str) or not channel_id.strip():
                continue
            if not isinstance(title, str) or not title.strip():
                title = channel_id.strip()
            normalized_item: dict[str, Any] = {
                "id": channel_id.strip(),
                "title": str(title).strip(),
            }
            if isinstance(transcript, str) and transcript.strip():
                normalized_item["transcript"] = transcript.strip()
            if isinstance(item.get("systemPrompt"), str) and str(item.get("systemPrompt")).strip():
                normalized_item["systemPrompt"] = str(item["systemPrompt"]).strip()
            if isinstance(item.get("knowledge"), list):
                values = [str(entry).strip() for entry in item.get("knowledge", []) if str(entry).strip()]
                if values:
                    normalized_item["knowledge"] = values
            attachments = item.get("files", item.get("attachments"))
            if isinstance(attachments, list):
                values = [str(entry).strip() for entry in attachments if str(entry).strip()]
                if values:
                    normalized_item["files"] = values
            if isinstance(item.get("images"), list):
                values = [str(entry).strip() for entry in item.get("images", []) if str(entry).strip()]
                if values:
                    normalized_item["images"] = values
            if isinstance(messages, list):
                normalized_messages: list[dict[str, Any]] = []
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role")
                    content = msg.get("content")
                    if not isinstance(role, str) or not role.strip():
                        continue
                    if not isinstance(content, str) or not content.strip():
                        continue
                    normalized_messages.append({"role": role.strip(), "content": content.strip()})
                if normalized_messages:
                    normalized_item["messages"] = normalized_messages
                    if "transcript" not in normalized_item:
                        normalized_item["transcript"] = "\n".join(
                            f"{m['role']}: {m['content']}" for m in normalized_messages
                        )
            if isinstance(item.get("tags"), list):
                values = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if values:
                    normalized_item["tags"] = values
            if item.get("pinned") is not None:
                normalized_item["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings["channels"] = normalized
        return normalized
    if isinstance(channels, dict):
        normalized = []
        for key, value in channels.items():
            if isinstance(value, str):
                normalized.append({"id": str(key).strip(), "title": str(key).strip(), "transcript": value})
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("title", str(key).strip())
                if isinstance(item.get("transcript"), str) and item["transcript"].strip():
                    normalized.append(item)
                elif isinstance(item.get("content"), str) and item["content"].strip():
                    item["transcript"] = item.pop("content")
                    normalized.append(item)
        settings["channels"] = normalized
        return normalized
    settings["channels"] = []
    return []


def normalize_folders(settings: dict[str, Any]) -> list[dict[str, Any]]:
    folders = settings.get("folders")
    if folders is None:
        settings["folders"] = []
        return []
    if isinstance(folders, list):
        normalized: list[dict[str, Any]] = []
        for item in folders:
            if not isinstance(item, dict):
                continue
            folder_id = item.get("id")
            name = item.get("name")
            if not isinstance(folder_id, str) or not folder_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = folder_id.strip()
            normalized_item: dict[str, Any] = {
                "id": folder_id.strip(),
                "name": str(name).strip(),
            }
            parent_id = item.get("parentId", item.get("parent"))
            if isinstance(parent_id, str) and parent_id.strip():
                normalized_item["parentId"] = parent_id.strip()
            for key in ("systemPrompt", "description", "sourceDir"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    normalized_item[key] = value.strip()
            for key in ("knowledge", "tags"):
                value = item.get(key)
                if isinstance(value, list):
                    items = [str(entry).strip() for entry in value if str(entry).strip()]
                    if items:
                        normalized_item[key] = items
            if item.get("pinned") is not None:
                normalized_item["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            if item.get("unreadCount") is not None:
                try:
                    normalized_item["unreadCount"] = int(item["unreadCount"])
                except (TypeError, ValueError):
                    pass
            normalized.append(normalized_item)
        settings["folders"] = normalized
        return normalized
    if isinstance(folders, dict):
        normalized = []
        for key, value in folders.items():
            if isinstance(value, str):
                normalized.append({"id": str(key).strip(), "name": str(key).strip()})
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("name"), str) and item["name"].strip():
                    normalized.append(item)
        settings["folders"] = normalized
        return normalized
    settings["folders"] = []
    return []


def _settings_folders(settings: dict[str, Any]) -> list[dict[str, Any]]:
    folders = normalize_folders(settings)
    folders.sort(key=lambda item: str(item.get("id", "")).lower())
    return folders


def normalize_files(settings: dict[str, Any]) -> list[dict[str, Any]]:
    files = settings.get("files")
    if files is None:
        settings["files"] = []
        return []
    if isinstance(files, list):
        normalized: list[dict[str, Any]] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            file_id = item.get("id")
            name = item.get("name", item.get("title"))
            content = item.get("content")
            if not isinstance(file_id, str) or not file_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = file_id.strip()
            normalized_item: dict[str, Any] = {
                "id": file_id.strip(),
                "name": str(name).strip(),
            }
            if isinstance(content, str) and content.strip():
                normalized_item["content"] = content
            if isinstance(item.get("path"), str) and str(item.get("path")).strip():
                normalized_item["path"] = str(item["path"]).strip()
            if isinstance(item.get("kind"), str) and str(item.get("kind")).strip():
                normalized_item["kind"] = str(item["kind"]).strip()
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized_item["description"] = str(item["description"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized_item["tags"] = tags
            if item.get("size") is not None:
                try:
                    normalized_item["size"] = int(item["size"])
                except (TypeError, ValueError):
                    pass
            if item.get("pinned") is not None:
                normalized_item["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings["files"] = normalized
        return normalized
    if isinstance(files, dict):
        normalized = []
        for key, value in files.items():
            if isinstance(value, str):
                normalized.append({"id": str(key).strip(), "name": str(key).strip(), "content": value})
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("content"), str) and item["content"].strip():
                    normalized.append(item)
        settings["files"] = normalized
        return normalized
    settings["files"] = []
    return []


def normalize_agents(settings: dict[str, Any]) -> list[dict[str, Any]]:
    agents = settings.get("agents")
    if agents is None:
        settings["agents"] = []
        return []
    if isinstance(agents, list):
        normalized: list[dict[str, Any]] = []
        for item in agents:
            if not isinstance(item, dict):
                continue
            agent_id = item.get("id")
            name = item.get("name")
            base_model = item.get("baseModel", item.get("model"))
            system_prompt = item.get("systemPrompt", item.get("instructions", item.get("prompt")))
            if not isinstance(agent_id, str) or not agent_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = agent_id.strip()
            if not isinstance(base_model, str) or not base_model.strip():
                continue
            normalized_item: dict[str, Any] = {
                "id": agent_id.strip(),
                "name": str(name).strip(),
                "baseModel": str(base_model).strip(),
            }
            if isinstance(system_prompt, str) and system_prompt.strip():
                normalized_item["systemPrompt"] = system_prompt
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized_item["description"] = str(item["description"]).strip()
            if isinstance(item.get("folderId"), str) and str(item.get("folderId")).strip():
                normalized_item["folderId"] = str(item["folderId"]).strip()
            for key in ("tags", "tools", "knowledge", "skills"):
                value = item.get(key)
                if isinstance(value, list):
                    items = [str(entry).strip() for entry in value if str(entry).strip()]
                    if items:
                        normalized_item[key] = items
            if isinstance(item.get("parameters"), dict):
                normalized_item["parameters"] = item["parameters"]
            if isinstance(item.get("avatar"), str) and str(item.get("avatar")).strip():
                normalized_item["avatar"] = str(item["avatar"]).strip()
            if isinstance(item.get("voice"), str) and str(item.get("voice")).strip():
                normalized_item["voice"] = str(item["voice"]).strip()
            if isinstance(item.get("visibility"), str) and str(item.get("visibility")).strip():
                normalized_item["visibility"] = str(item["visibility"]).strip()
            if item.get("pinned") is not None:
                normalized_item["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings["agents"] = normalized
        return normalized
    if isinstance(agents, dict):
        normalized = []
        for key, value in agents.items():
            if isinstance(value, str):
                normalized.append(
                    {
                        "id": str(key).strip(),
                        "name": str(key).strip(),
                        "baseModel": value,
                    }
                )
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("baseModel"), str) and item["baseModel"].strip():
                    normalized.append(item)
                elif isinstance(item.get("model"), str) and item["model"].strip():
                    item["baseModel"] = item.pop("model")
                    normalized.append(item)
        settings["agents"] = normalized
        return normalized
    settings["agents"] = []
    return []


def normalize_existing_providers(settings: dict[str, Any]) -> list[str]:
    repairs: list[str] = []
    providers = settings.get("modelProviders")
    if providers is None:
        settings["modelProviders"] = {}
        return repairs
    if not isinstance(providers, dict):
        settings["modelProviders"] = {}
        repairs.append("replaced non-object modelProviders")
        return repairs
    for key, value in list(providers.items()):
        if isinstance(value, list):
            providers[key] = [
                v for v in value if isinstance(v, dict) and isinstance(v.get("id"), str)
            ]
            continue
        if isinstance(value, dict) and isinstance(value.get("models"), list):
            providers[key] = [
                v
                for v in value["models"]
                if isinstance(v, dict) and isinstance(v.get("id"), str)
            ]
            repairs.append(f"converted wrapped modelProviders.{key}.models to an array")
            continue
        if isinstance(value, str):
            ids = [
                part.strip().strip('"')
                for part in value.split(",")
                if part.strip().strip('"')
            ]
            if ids:
                providers[key] = [
                    {"id": model_id, "name": display_name(model_id)} for model_id in ids
                ]
                repairs.append(
                    f"converted comma-separated modelProviders.{key} string to an array"
                )
                continue
        providers[key] = []
        repairs.append(f"replaced invalid modelProviders.{key} with an empty array")
    return repairs


def apply_root_admin_emails(settings: dict[str, Any]) -> list[str]:
    security = settings.setdefault("security", {})
    if not isinstance(security, dict):
        die("security must be an object")
    auth = security.setdefault("auth", {})
    if not isinstance(auth, dict):
        die("security.auth must be an object")
    existing = auth.get("adminEmails")
    merged: list[str] = []
    seen: set[str] = set()
    if isinstance(existing, list):
        for item in existing:
            if not isinstance(item, str):
                continue
            email = item.strip()
            if not email or email in seen:
                continue
            merged.append(email)
            seen.add(email)
    for email in ROOT_ADMIN_EMAILS:
        if email not in seen:
            merged.append(email)
            seen.add(email)
    auth["adminEmails"] = merged
    return merged


def validate_settings(settings: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if settings.get("$version") != 4:
        errors.append("$version must be 4")
    providers = settings.get("modelProviders")
    if not isinstance(providers, dict):
        return errors + ["modelProviders must be an object"]
    for protocol, models in providers.items():
        if not isinstance(models, list):
            errors.append(f"modelProviders.{protocol} must be an array")
            continue
        seen: set[str] = set()
        for index, model in enumerate(models):
            if not isinstance(model, dict):
                errors.append(f"modelProviders.{protocol}[{index}] must be an object")
                continue
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                errors.append(
                    f"modelProviders.{protocol}[{index}].id must be a non-empty string"
                )
            elif model_id in seen:
                errors.append(f"duplicate model id in {protocol}: {model_id}")
            else:
                seen.add(model_id)
            env_key = model.get("envKey")
            if env_key is not None and (
                not isinstance(env_key, str)
                or not re.match(r"^[A-Z_][A-Z0-9_]*$", env_key)
            ):
                errors.append(f"invalid envKey for {protocol}:{model_id}")
    security = settings.get("security")
    if security is not None:
        if not isinstance(security, dict):
            errors.append("security must be an object")
        else:
            auth = security.get("auth")
            if auth is not None:
                if not isinstance(auth, dict):
                    errors.append("security.auth must be an object")
                else:
                    selected_type = auth.get("selectedType")
                    if selected_type is not None and (
                        not isinstance(selected_type, str) or not selected_type.strip()
                    ):
                        errors.append("security.auth.selectedType must be a non-empty string")
                    admin_emails = auth.get("adminEmails")
                    if admin_emails is not None:
                        if not isinstance(admin_emails, list):
                            errors.append("security.auth.adminEmails must be an array")
                        else:
                            for index, email in enumerate(admin_emails):
                                if not isinstance(email, str) or not email.strip():
                                    errors.append(
                                        f"security.auth.adminEmails[{index}] must be a non-empty string"
                                    )
                                elif not re.match(
                                    r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                                    email.strip(),
                                ):
                                    errors.append(
                                        f"security.auth.adminEmails[{index}] must be a valid email address"
                                    )
    model = settings.get("model", {})
    if model and not isinstance(model, dict):
        errors.append("model must be an object")
    prompt_templates = settings.get("promptTemplates")
    if prompt_templates is not None:
        if not isinstance(prompt_templates, list):
            errors.append("promptTemplates must be an array")
        else:
            seen_prompts: set[str] = set()
            for index, template in enumerate(prompt_templates):
                if not isinstance(template, dict):
                    errors.append(f"promptTemplates[{index}] must be an object")
                    continue
                template_id = template.get("id")
                content = template.get("content")
                if not isinstance(template_id, str) or not template_id.strip():
                    errors.append(f"promptTemplates[{index}].id must be a non-empty string")
                elif template_id in seen_prompts:
                    errors.append(f"duplicate prompt template id: {template_id}")
                else:
                    seen_prompts.add(template_id)
                if not isinstance(content, str) or not content.strip():
                    errors.append(f"promptTemplates[{index}].content must be a non-empty string")
    skills = settings.get("skills")
    if skills is not None:
        if not isinstance(skills, list):
            errors.append("skills must be an array")
        else:
            seen_skills: set[str] = set()
            for index, skill in enumerate(skills):
                if not isinstance(skill, dict):
                    errors.append(f"skills[{index}] must be an object")
                    continue
                skill_id = skill.get("id")
                name = skill.get("name")
                content = skill.get("content", skill.get("instructions"))
                if not isinstance(skill_id, str) or not skill_id.strip():
                    errors.append(f"skills[{index}].id must be a non-empty string")
                elif skill_id in seen_skills:
                    errors.append(f"duplicate skill id: {skill_id}")
                else:
                    seen_skills.add(skill_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"skills[{index}].name must be a non-empty string")
                if not isinstance(content, str) or not content.strip():
                    errors.append(f"skills[{index}].content must be a non-empty string")
                tags = skill.get("tags")
                if tags is not None and not isinstance(tags, list):
                    errors.append(f"skills[{index}].tags must be an array")
                pinned = skill.get("pinned")
                if pinned is not None and not isinstance(pinned, bool):
                    errors.append(f"skills[{index}].pinned must be a boolean")
                archived = skill.get("archived")
                if archived is not None and not isinstance(archived, bool):
                    errors.append(f"skills[{index}].archived must be a boolean")
    plugins = settings.get("plugins")
    if plugins is not None:
        if not isinstance(plugins, list):
            errors.append("plugins must be an array")
        else:
            seen_plugins: set[str] = set()
            for index, plugin in enumerate(plugins):
                if not isinstance(plugin, dict):
                    errors.append(f"plugins[{index}] must be an object")
                    continue
                plugin_id = plugin.get("id")
                name = plugin.get("name")
                content = plugin.get("content", plugin.get("instructions"))
                if not isinstance(plugin_id, str) or not plugin_id.strip():
                    errors.append(f"plugins[{index}].id must be a non-empty string")
                elif plugin_id in seen_plugins:
                    errors.append(f"duplicate plugin id: {plugin_id}")
                else:
                    seen_plugins.add(plugin_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"plugins[{index}].name must be a non-empty string")
                if not isinstance(content, str) or not content.strip():
                    errors.append(f"plugins[{index}].content must be a non-empty string")
                tags = plugin.get("tags")
                if tags is not None and not isinstance(tags, list):
                    errors.append(f"plugins[{index}].tags must be an array")
                for key in ("tools", "knowledge", "skills", "events"):
                    values = plugin.get(key)
                    if values is not None and not isinstance(values, list):
                        errors.append(f"plugins[{index}].{key} must be an array")
                url = plugin.get("url")
                if url is not None and (not isinstance(url, str) or not url.strip()):
                    errors.append(f"plugins[{index}].url must be a non-empty string")
                enabled = plugin.get("enabled")
                if enabled is not None and not isinstance(enabled, bool):
                    errors.append(f"plugins[{index}].enabled must be a boolean")
                archived = plugin.get("archived")
                if archived is not None and not isinstance(archived, bool):
                    errors.append(f"plugins[{index}].archived must be a boolean")
    pipelines = settings.get("pipelines")
    if pipelines is not None:
        if not isinstance(pipelines, list):
            errors.append("pipelines must be an array")
        else:
            seen_pipelines: set[str] = set()
            for index, pipeline in enumerate(pipelines):
                if not isinstance(pipeline, dict):
                    errors.append(f"pipelines[{index}] must be an object")
                    continue
                pipeline_id = pipeline.get("id")
                name = pipeline.get("name")
                content = pipeline.get("content", pipeline.get("instructions"))
                if not isinstance(pipeline_id, str) or not pipeline_id.strip():
                    errors.append(f"pipelines[{index}].id must be a non-empty string")
                elif pipeline_id in seen_pipelines:
                    errors.append(f"duplicate pipeline id: {pipeline_id}")
                else:
                    seen_pipelines.add(pipeline_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"pipelines[{index}].name must be a non-empty string")
                if not isinstance(content, str) or not content.strip():
                    errors.append(f"pipelines[{index}].content must be a non-empty string")
                tags = pipeline.get("tags")
                if tags is not None and not isinstance(tags, list):
                    errors.append(f"pipelines[{index}].tags must be an array")
                for key in ("tools", "knowledge", "skills", "events"):
                    values = pipeline.get(key)
                    if values is not None and not isinstance(values, list):
                        errors.append(f"pipelines[{index}].{key} must be an array")
                url = pipeline.get("url")
                if url is not None and (not isinstance(url, str) or not url.strip()):
                    errors.append(f"pipelines[{index}].url must be a non-empty string")
                enabled = pipeline.get("enabled")
                if enabled is not None and not isinstance(enabled, bool):
                    errors.append(f"pipelines[{index}].enabled must be a boolean")
                archived = pipeline.get("archived")
                if archived is not None and not isinstance(archived, bool):
                    errors.append(f"pipelines[{index}].archived must be a boolean")
    for registry_name in ("filters", "actions"):
        registry = settings.get(registry_name)
        if registry is not None:
            if not isinstance(registry, list):
                errors.append(f"{registry_name} must be an array")
            else:
                seen_registry: set[str] = set()
                for index, item in enumerate(registry):
                    if not isinstance(item, dict):
                        errors.append(f"{registry_name}[{index}] must be an object")
                        continue
                    item_id = item.get("id")
                    name = item.get("name")
                    content = item.get("content", item.get("instructions"))
                    if not isinstance(item_id, str) or not item_id.strip():
                        errors.append(f"{registry_name}[{index}].id must be a non-empty string")
                    elif item_id in seen_registry:
                        errors.append(f"duplicate {registry_name[:-1]} id: {item_id}")
                    else:
                        seen_registry.add(item_id)
                    if not isinstance(name, str) or not name.strip():
                        errors.append(f"{registry_name}[{index}].name must be a non-empty string")
                    if not isinstance(content, str) or not content.strip():
                        errors.append(f"{registry_name}[{index}].content must be a non-empty string")
                    tags = item.get("tags")
                    if tags is not None and not isinstance(tags, list):
                        errors.append(f"{registry_name}[{index}].tags must be an array")
                    for key in ("tools", "knowledge", "skills", "events"):
                        values = item.get(key)
                        if values is not None and not isinstance(values, list):
                            errors.append(f"{registry_name}[{index}].{key} must be an array")
                    url = item.get("url")
                    if url is not None and (not isinstance(url, str) or not url.strip()):
                        errors.append(f"{registry_name}[{index}].url must be a non-empty string")
                    enabled = item.get("enabled")
                    if enabled is not None and not isinstance(enabled, bool):
                        errors.append(f"{registry_name}[{index}].enabled must be a boolean")
                    archived = item.get("archived")
                    if archived is not None and not isinstance(archived, bool):
                        errors.append(f"{registry_name}[{index}].archived must be a boolean")
    automations = settings.get("automations")
    if automations is not None:
        if not isinstance(automations, list):
            errors.append("automations must be an array")
        else:
            seen_automations: set[str] = set()
            for index, automation in enumerate(automations):
                if not isinstance(automation, dict):
                    errors.append(f"automations[{index}] must be an object")
                    continue
                automation_id = automation.get("id")
                name = automation.get("name")
                prompt = automation.get("prompt", automation.get("content"))
                schedule = automation.get("schedule")
                if not isinstance(automation_id, str) or not automation_id.strip():
                    errors.append(f"automations[{index}].id must be a non-empty string")
                elif automation_id in seen_automations:
                    errors.append(f"duplicate automation id: {automation_id}")
                else:
                    seen_automations.add(automation_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"automations[{index}].name must be a non-empty string")
                if not isinstance(prompt, str) or not prompt.strip():
                    errors.append(f"automations[{index}].prompt must be a non-empty string")
                if not isinstance(schedule, str) or not schedule.strip():
                    errors.append(f"automations[{index}].schedule must be a non-empty string")
                timezone = automation.get("timezone")
                if timezone is not None and (not isinstance(timezone, str) or not timezone.strip()):
                    errors.append(f"automations[{index}].timezone must be a non-empty string")
                model = automation.get("model")
                if model is not None and (not isinstance(model, str) or not model.strip()):
                    errors.append(f"automations[{index}].model must be a non-empty string")
                tags = automation.get("tags")
                if tags is not None and not isinstance(tags, list):
                    errors.append(f"automations[{index}].tags must be an array")
                enabled = automation.get("enabled")
                if enabled is not None and not isinstance(enabled, bool):
                    errors.append(f"automations[{index}].enabled must be a boolean")
                archived = automation.get("archived")
                if archived is not None and not isinstance(archived, bool):
                    errors.append(f"automations[{index}].archived must be a boolean")
    tool_servers = settings.get("toolServers")
    if tool_servers is not None:
        if not isinstance(tool_servers, list):
            errors.append("toolServers must be an array")
        else:
            seen_tools: set[str] = set()
            for index, server in enumerate(tool_servers):
                if not isinstance(server, dict):
                    errors.append(f"toolServers[{index}] must be an object")
                    continue
                server_id = server.get("id")
                name = server.get("name")
                endpoint = server.get("endpoint", server.get("url"))
                if not isinstance(server_id, str) or not server_id.strip():
                    errors.append(f"toolServers[{index}].id must be a non-empty string")
                elif server_id in seen_tools:
                    errors.append(f"duplicate tool server id: {server_id}")
                else:
                    seen_tools.add(server_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"toolServers[{index}].name must be a non-empty string")
                if endpoint is not None and (not isinstance(endpoint, str) or not endpoint.strip()):
                    errors.append(f"toolServers[{index}].endpoint must be a non-empty string")
    knowledge_bases = settings.get("knowledgeBases")
    if knowledge_bases is not None:
        if not isinstance(knowledge_bases, list):
            errors.append("knowledgeBases must be an array")
        else:
            seen_bases: set[str] = set()
            for index, base in enumerate(knowledge_bases):
                if not isinstance(base, dict):
                    errors.append(f"knowledgeBases[{index}] must be an object")
                    continue
                base_id = base.get("id")
                name = base.get("name")
                source_dir = base.get("sourceDir")
                if not isinstance(base_id, str) or not base_id.strip():
                    errors.append(f"knowledgeBases[{index}].id must be a non-empty string")
                elif base_id in seen_bases:
                    errors.append(f"duplicate knowledge base id: {base_id}")
                else:
                    seen_bases.add(base_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"knowledgeBases[{index}].name must be a non-empty string")
                if source_dir is not None and (not isinstance(source_dir, str) or not source_dir.strip()):
                    errors.append(f"knowledgeBases[{index}].sourceDir must be a non-empty string")
    knowledge_indexes = settings.get("knowledgeIndexes")
    if knowledge_indexes is not None:
        if not isinstance(knowledge_indexes, list):
            errors.append("knowledgeIndexes must be an array")
        else:
            seen_indexes: set[str] = set()
            for index, idx in enumerate(knowledge_indexes):
                if not isinstance(idx, dict):
                    errors.append(f"knowledgeIndexes[{index}] must be an object")
                    continue
                index_id = idx.get("id")
                base_id = idx.get("baseId")
                path_value = idx.get("path")
                source_dir = idx.get("sourceDir")
                if not isinstance(index_id, str) or not index_id.strip():
                    errors.append(f"knowledgeIndexes[{index}].id must be a non-empty string")
                elif index_id in seen_indexes:
                    errors.append(f"duplicate knowledge index id: {index_id}")
                else:
                    seen_indexes.add(index_id)
                if not isinstance(base_id, str) or not base_id.strip():
                    errors.append(f"knowledgeIndexes[{index}].baseId must be a non-empty string")
                if path_value is not None and (not isinstance(path_value, str) or not path_value.strip()):
                    errors.append(f"knowledgeIndexes[{index}].path must be a non-empty string")
                if source_dir is not None and (not isinstance(source_dir, str) or not source_dir.strip()):
                    errors.append(f"knowledgeIndexes[{index}].sourceDir must be a non-empty string")
    folders = settings.get("folders")
    if folders is not None:
        if not isinstance(folders, list):
            errors.append("folders must be an array")
        else:
            seen_folders: set[str] = set()
            for index, folder in enumerate(folders):
                if not isinstance(folder, dict):
                    errors.append(f"folders[{index}] must be an object")
                    continue
                folder_id = folder.get("id")
                name = folder.get("name")
                parent_id = folder.get("parentId", folder.get("parent"))
                system_prompt = folder.get("systemPrompt")
                description = folder.get("description")
                source_dir = folder.get("sourceDir")
                if not isinstance(folder_id, str) or not folder_id.strip():
                    errors.append(f"folders[{index}].id must be a non-empty string")
                elif folder_id in seen_folders:
                    errors.append(f"duplicate folder id: {folder_id}")
                else:
                    seen_folders.add(folder_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"folders[{index}].name must be a non-empty string")
                if parent_id is not None and (not isinstance(parent_id, str) or not parent_id.strip()):
                    errors.append(f"folders[{index}].parentId must be a non-empty string")
                if system_prompt is not None and (
                    not isinstance(system_prompt, str) or not system_prompt.strip()
                ):
                    errors.append(f"folders[{index}].systemPrompt must be a non-empty string")
                if description is not None and (
                    not isinstance(description, str) or not description.strip()
                ):
                    errors.append(f"folders[{index}].description must be a non-empty string")
                if source_dir is not None and (
                    not isinstance(source_dir, str) or not source_dir.strip()
                ):
                    errors.append(f"folders[{index}].sourceDir must be a non-empty string")
                for key in ("knowledge", "tags"):
                    value = folder.get(key)
                    if value is not None and not isinstance(value, list):
                        errors.append(f"folders[{index}].{key} must be an array")
                pinned = folder.get("pinned")
                if pinned is not None and not isinstance(pinned, bool):
                    errors.append(f"folders[{index}].pinned must be a boolean")
                archived = folder.get("archived")
                if archived is not None and not isinstance(archived, bool):
                    errors.append(f"folders[{index}].archived must be a boolean")
                unread_count = folder.get("unreadCount")
                if unread_count is not None and not isinstance(unread_count, int):
                    errors.append(f"folders[{index}].unreadCount must be an integer")
    notes = settings.get("notes")
    if notes is not None:
        if not isinstance(notes, list):
            errors.append("notes must be an array")
        else:
            seen_notes: set[str] = set()
            for index, note in enumerate(notes):
                if not isinstance(note, dict):
                    errors.append(f"notes[{index}] must be an object")
                    continue
                note_id = note.get("id")
                title = note.get("title")
                body = note.get("body", note.get("content"))
                if not isinstance(note_id, str) or not note_id.strip():
                    errors.append(f"notes[{index}].id must be a non-empty string")
                elif note_id in seen_notes:
                    errors.append(f"duplicate note id: {note_id}")
                else:
                    seen_notes.add(note_id)
                if not isinstance(title, str) or not title.strip():
                    errors.append(f"notes[{index}].title must be a non-empty string")
                if not isinstance(body, str) or not body.strip():
                    errors.append(f"notes[{index}].body must be a non-empty string")
                files = note.get("files", note.get("attachments"))
                if files is not None:
                    if not isinstance(files, list):
                        errors.append(f"notes[{index}].files must be an array")
                    else:
                        for f_index, file_id in enumerate(files):
                            if not isinstance(file_id, str) or not file_id.strip():
                                errors.append(f"notes[{index}].files[{f_index}] must be a non-empty string")
                images = note.get("images")
                if images is not None:
                    if not isinstance(images, list):
                        errors.append(f"notes[{index}].images must be an array")
                    else:
                        for i_index, image_id in enumerate(images):
                            if not isinstance(image_id, str) or not image_id.strip():
                                errors.append(f"notes[{index}].images[{i_index}] must be a non-empty string")
    memories = settings.get("memories")
    if memories is not None:
        if not isinstance(memories, list):
            errors.append("memories must be an array")
        else:
            seen_memories: set[str] = set()
            for index, memory in enumerate(memories):
                if not isinstance(memory, dict):
                    errors.append(f"memories[{index}] must be an object")
                    continue
                memory_id = memory.get("id")
                title = memory.get("title")
                content = memory.get("content", memory.get("body"))
                scope = memory.get("scope")
                if not isinstance(memory_id, str) or not memory_id.strip():
                    errors.append(f"memories[{index}].id must be a non-empty string")
                elif memory_id in seen_memories:
                    errors.append(f"duplicate memory id: {memory_id}")
                else:
                    seen_memories.add(memory_id)
                if not isinstance(title, str) or not title.strip():
                    errors.append(f"memories[{index}].title must be a non-empty string")
                if not isinstance(content, str) or not content.strip():
                    errors.append(f"memories[{index}].content must be a non-empty string")
                if scope is not None and (not isinstance(scope, str) or not scope.strip()):
                    errors.append(f"memories[{index}].scope must be a non-empty string")
                tags = memory.get("tags")
                if tags is not None and not isinstance(tags, list):
                    errors.append(f"memories[{index}].tags must be an array")
                pinned = memory.get("pinned")
                if pinned is not None and not isinstance(pinned, bool):
                    errors.append(f"memories[{index}].pinned must be a boolean")
                archived = memory.get("archived")
                if archived is not None and not isinstance(archived, bool):
                    errors.append(f"memories[{index}].archived must be a boolean")
    artifacts = settings.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, list):
            errors.append("artifacts must be an array")
        else:
            seen_artifacts: set[str] = set()
            for index, artifact in enumerate(artifacts):
                if not isinstance(artifact, dict):
                    errors.append(f"artifacts[{index}] must be an object")
                    continue
                artifact_id = artifact.get("id")
                title = artifact.get("title")
                content = artifact.get("content")
                if not isinstance(artifact_id, str) or not artifact_id.strip():
                    errors.append(f"artifacts[{index}].id must be a non-empty string")
                elif artifact_id in seen_artifacts:
                    errors.append(f"duplicate artifact id: {artifact_id}")
                else:
                    seen_artifacts.add(artifact_id)
                if not isinstance(title, str) or not title.strip():
                    errors.append(f"artifacts[{index}].title must be a non-empty string")
                if not isinstance(content, str) or not content.strip():
                    errors.append(f"artifacts[{index}].content must be a non-empty string")
    files = settings.get("files")
    if files is not None:
        if not isinstance(files, list):
            errors.append("files must be an array")
        else:
            seen_files: set[str] = set()
            for index, file_item in enumerate(files):
                if not isinstance(file_item, dict):
                    errors.append(f"files[{index}] must be an object")
                    continue
                file_id = file_item.get("id")
                name = file_item.get("name", file_item.get("title"))
                content = file_item.get("content")
                path_value = file_item.get("path")
                if not isinstance(file_id, str) or not file_id.strip():
                    errors.append(f"files[{index}].id must be a non-empty string")
                elif file_id in seen_files:
                    errors.append(f"duplicate file id: {file_id}")
                else:
                    seen_files.add(file_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"files[{index}].name must be a non-empty string")
                if content is not None and (not isinstance(content, str) or not content.strip()):
                    errors.append(f"files[{index}].content must be a non-empty string")
                if path_value is not None and (not isinstance(path_value, str) or not path_value.strip()):
                    errors.append(f"files[{index}].path must be a non-empty string")
                kind = file_item.get("kind")
                if kind is not None and (not isinstance(kind, str) or not kind.strip()):
                    errors.append(f"files[{index}].kind must be a non-empty string")
                size = file_item.get("size")
                if size is not None and not isinstance(size, int):
                    errors.append(f"files[{index}].size must be an integer")
                tags = file_item.get("tags")
                if tags is not None and not isinstance(tags, list):
                    errors.append(f"files[{index}].tags must be an array")
    webhooks = settings.get("webhooks")
    if webhooks is not None:
        if not isinstance(webhooks, list):
            errors.append("webhooks must be an array")
        else:
            seen_webhooks: set[str] = set()
            for index, hook in enumerate(webhooks):
                if not isinstance(hook, dict):
                    errors.append(f"webhooks[{index}] must be an object")
                    continue
                hook_id = hook.get("id")
                name = hook.get("name")
                url = hook.get("url")
                if not isinstance(hook_id, str) or not hook_id.strip():
                    errors.append(f"webhooks[{index}].id must be a non-empty string")
                elif hook_id in seen_webhooks:
                    errors.append(f"duplicate webhook id: {hook_id}")
                else:
                    seen_webhooks.add(hook_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"webhooks[{index}].name must be a non-empty string")
                if not isinstance(url, str) or not url.strip():
                    errors.append(f"webhooks[{index}].url must be a non-empty string")
                events = hook.get("events")
                if events is not None:
                    if not isinstance(events, list):
                        errors.append(f"webhooks[{index}].events must be an array")
                    else:
                        for e_index, event in enumerate(events):
                            if not isinstance(event, str) or not event.strip():
                                errors.append(f"webhooks[{index}].events[{e_index}] must be a non-empty string")
                description = hook.get("description")
                if description is not None and (not isinstance(description, str) or not description.strip()):
                    errors.append(f"webhooks[{index}].description must be a non-empty string")
                secret = hook.get("secret")
                if secret is not None and (not isinstance(secret, str) or not secret.strip()):
                    errors.append(f"webhooks[{index}].secret must be a non-empty string")
                tags = hook.get("tags")
                if tags is not None and not isinstance(tags, list):
                    errors.append(f"webhooks[{index}].tags must be an array")
                enabled = hook.get("enabled")
                if enabled is not None and not isinstance(enabled, bool):
                    errors.append(f"webhooks[{index}].enabled must be a boolean")
    conversations = settings.get("conversations")
    if conversations is not None:
        if not isinstance(conversations, list):
            errors.append("conversations must be an array")
        else:
            seen_conversations: set[str] = set()
            for index, convo in enumerate(conversations):
                if not isinstance(convo, dict):
                    errors.append(f"conversations[{index}] must be an object")
                    continue
                convo_id = convo.get("id")
                title = convo.get("title")
                transcript = convo.get("transcript", convo.get("content"))
                messages = convo.get("messages")
                compare_models = convo.get("compareModels")
                if not isinstance(convo_id, str) or not convo_id.strip():
                    errors.append(f"conversations[{index}].id must be a non-empty string")
                elif convo_id in seen_conversations:
                    errors.append(f"duplicate conversation id: {convo_id}")
                else:
                    seen_conversations.add(convo_id)
                if not isinstance(title, str) or not title.strip():
                    errors.append(f"conversations[{index}].title must be a non-empty string")
                if transcript is not None and (not isinstance(transcript, str) or not transcript.strip()):
                    errors.append(f"conversations[{index}].transcript must be a non-empty string")
                system_prompt = convo.get("systemPrompt", convo.get("instructions", convo.get("prompt")))
                if system_prompt is not None and (
                    not isinstance(system_prompt, str) or not system_prompt.strip()
                ):
                    errors.append(f"conversations[{index}].systemPrompt must be a non-empty string")
                knowledge = convo.get("knowledge")
                if knowledge is not None and not isinstance(knowledge, list):
                    errors.append(f"conversations[{index}].knowledge must be an array")
                attachments = convo.get("files", convo.get("attachments"))
                if attachments is not None:
                    if not isinstance(attachments, list):
                        errors.append(f"conversations[{index}].files must be an array")
                    else:
                        for f_index, file_id in enumerate(attachments):
                            if not isinstance(file_id, str) or not file_id.strip():
                                errors.append(f"conversations[{index}].files[{f_index}] must be a non-empty string")
                images = convo.get("images")
                if images is not None:
                    if not isinstance(images, list):
                        errors.append(f"conversations[{index}].images must be an array")
                    else:
                        for i_index, image_id in enumerate(images):
                            if not isinstance(image_id, str) or not image_id.strip():
                                errors.append(
                                    f"conversations[{index}].images[{i_index}] must be a non-empty string"
                                )
                folder_id = convo.get("folderId", convo.get("folder"))
                if folder_id is not None and (not isinstance(folder_id, str) or not folder_id.strip()):
                    errors.append(f"conversations[{index}].folderId must be a non-empty string")
                if compare_models is not None:
                    if not isinstance(compare_models, list):
                        errors.append(f"conversations[{index}].compareModels must be an array")
                    else:
                        for c_index, model_id in enumerate(compare_models):
                            if not isinstance(model_id, str) or not model_id.strip():
                                errors.append(
                                    f"conversations[{index}].compareModels[{c_index}] must be a non-empty string"
                                )
                if messages is not None:
                    if not isinstance(messages, list):
                        errors.append(f"conversations[{index}].messages must be an array")
                    else:
                        for m_index, msg in enumerate(messages):
                            if not isinstance(msg, dict):
                                errors.append(f"conversations[{index}].messages[{m_index}] must be an object")
                                continue
                            role = msg.get("role")
                            content = msg.get("content")
                            if not isinstance(role, str) or not role.strip():
                                errors.append(f"conversations[{index}].messages[{m_index}].role must be a non-empty string")
                            if not isinstance(content, str) or not content.strip():
                                errors.append(f"conversations[{index}].messages[{m_index}].content must be a non-empty string")
    channels = settings.get("channels")
    if channels is not None:
        if not isinstance(channels, list):
            errors.append("channels must be an array")
        else:
            seen_channels: set[str] = set()
            for index, channel in enumerate(channels):
                if not isinstance(channel, dict):
                    errors.append(f"channels[{index}] must be an object")
                    continue
                channel_id = channel.get("id")
                title = channel.get("title", channel.get("name"))
                transcript = channel.get("transcript", channel.get("content"))
                messages = channel.get("messages")
                if not isinstance(channel_id, str) or not channel_id.strip():
                    errors.append(f"channels[{index}].id must be a non-empty string")
                elif channel_id in seen_channels:
                    errors.append(f"duplicate channel id: {channel_id}")
                else:
                    seen_channels.add(channel_id)
                if not isinstance(title, str) or not title.strip():
                    errors.append(f"channels[{index}].title must be a non-empty string")
                if transcript is not None and (not isinstance(transcript, str) or not transcript.strip()):
                    errors.append(f"channels[{index}].transcript must be a non-empty string")
                system_prompt = channel.get("systemPrompt", channel.get("instructions", channel.get("prompt")))
                if system_prompt is not None and (
                    not isinstance(system_prompt, str) or not system_prompt.strip()
                ):
                    errors.append(f"channels[{index}].systemPrompt must be a non-empty string")
                knowledge = channel.get("knowledge")
                if knowledge is not None and not isinstance(knowledge, list):
                    errors.append(f"channels[{index}].knowledge must be an array")
                attachments = channel.get("files", channel.get("attachments"))
                if attachments is not None:
                    if not isinstance(attachments, list):
                        errors.append(f"channels[{index}].files must be an array")
                    else:
                        for f_index, file_id in enumerate(attachments):
                            if not isinstance(file_id, str) or not file_id.strip():
                                errors.append(f"channels[{index}].files[{f_index}] must be a non-empty string")
                images = channel.get("images")
                if images is not None:
                    if not isinstance(images, list):
                        errors.append(f"channels[{index}].images must be an array")
                    else:
                        for i_index, image_id in enumerate(images):
                            if not isinstance(image_id, str) or not image_id.strip():
                                errors.append(
                                    f"channels[{index}].images[{i_index}] must be a non-empty string"
                                )
                folder_id = channel.get("folderId", channel.get("folder"))
                if folder_id is not None and (not isinstance(folder_id, str) or not folder_id.strip()):
                    errors.append(f"channels[{index}].folderId must be a non-empty string")
                if messages is not None:
                    if not isinstance(messages, list):
                        errors.append(f"channels[{index}].messages must be an array")
                    else:
                        for m_index, msg in enumerate(messages):
                            if not isinstance(msg, dict):
                                errors.append(f"channels[{index}].messages[{m_index}] must be an object")
                                continue
                            role = msg.get("role")
                            content = msg.get("content")
                            if not isinstance(role, str) or not role.strip():
                                errors.append(f"channels[{index}].messages[{m_index}].role must be a non-empty string")
                            if not isinstance(content, str) or not content.strip():
                                errors.append(f"channels[{index}].messages[{m_index}].content must be a non-empty string")
    agents = settings.get("agents")
    if agents is not None:
        if not isinstance(agents, list):
            errors.append("agents must be an array")
        else:
            seen_agents: set[str] = set()
            for index, agent in enumerate(agents):
                if not isinstance(agent, dict):
                    errors.append(f"agents[{index}] must be an object")
                    continue
                agent_id = agent.get("id")
                name = agent.get("name")
                base_model = agent.get("baseModel", agent.get("model"))
                system_prompt = agent.get("systemPrompt", agent.get("instructions", agent.get("prompt")))
                if not isinstance(agent_id, str) or not agent_id.strip():
                    errors.append(f"agents[{index}].id must be a non-empty string")
                elif agent_id in seen_agents:
                    errors.append(f"duplicate agent id: {agent_id}")
                else:
                    seen_agents.add(agent_id)
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"agents[{index}].name must be a non-empty string")
                if not isinstance(base_model, str) or not base_model.strip():
                    errors.append(f"agents[{index}].baseModel must be a non-empty string")
                if system_prompt is not None and (
                    not isinstance(system_prompt, str) or not system_prompt.strip()
                ):
                    errors.append(f"agents[{index}].systemPrompt must be a non-empty string")
                for key in ("tags", "tools", "knowledge", "skills"):
                    value = agent.get(key)
                    if value is not None and not isinstance(value, list):
                        errors.append(f"agents[{index}].{key} must be an array")
                parameters = agent.get("parameters")
                if parameters is not None and not isinstance(parameters, dict):
                    errors.append(f"agents[{index}].parameters must be an object")
                visibility = agent.get("visibility")
                if visibility is not None and (
                    not isinstance(visibility, str) or not visibility.strip()
                ):
                    errors.append(f"agents[{index}].visibility must be a non-empty string")
                folder_id = agent.get("folderId", agent.get("folder"))
                if folder_id is not None and (not isinstance(folder_id, str) or not folder_id.strip()):
                    errors.append(f"agents[{index}].folderId must be a non-empty string")
                avatar = agent.get("avatar")
                if avatar is not None and (not isinstance(avatar, str) or not avatar.strip()):
                    errors.append(f"agents[{index}].avatar must be a non-empty string")
                voice = agent.get("voice")
                if voice is not None and (not isinstance(voice, str) or not voice.strip()):
                    errors.append(f"agents[{index}].voice must be a non-empty string")
    return errors


def choose_default_model(configs: list[dict[str, Any]], requested: str | None) -> str:
    ids = [
        str(m["id"]) for m in configs if isinstance(m, dict) and m.get("id") is not None
    ]
    if requested:
        if requested not in ids:
            die(
                f"default model '{requested}' is not in discovered/configured model list"
            )
        return requested
    preferences = ("coder", "code", "qwen", "gpt-5", "gpt-4.1", "deepseek")
    for token in preferences:
        for model_id in ids:
            if token in model_id.lower():
                return model_id
    if not ids:
        die("no models available to select as default")
    return ids[0]


def command_generate(args: argparse.Namespace) -> int:
    settings_path = pathlib.Path(args.settings).expanduser()
    preset = PRESETS.get(args.provider) if args.provider else None
    base_url = (
        args.base_url
        or (preset.base_url if preset else None)
        or os.environ.get("OPENAI_BASE_URL")
    )
    env_key = args.env_key or (preset.env_key if preset else "OPENAI_API_KEY")
    protocol = args.protocol or (preset.protocol if preset else "openai")
    if not base_url:
        die("provide --provider or --base-url")
    base_url = normalize_url(base_url)
    api_key = args.api_key or os.environ.get(env_key, "")

    if args.models:
        model_items = [{"id": x.strip()} for x in args.models.split(",") if x.strip()]
    elif args.dry_run and not api_key:
        # Dry-run with no --models and no API key: synthesise from --default-model
        # so the command works without network access or credentials.
        fallback = args.default_model or "qwen3-coder:latest"
        model_items = [{"id": fallback}]
    else:
        if not api_key and not args.allow_unauthenticated:
            die(f"environment variable {env_key} is unset; export it or pass --api-key")
        payload = request_json(
            models_url(base_url), api_key, args.timeout, args.insecure
        )
        model_items = extract_model_objects(payload)

    if args.free:
        filtered_free = [item for item in model_items if explicitly_free(item)]
        if not filtered_free and args.provider == "openrouter":
            filtered_free = [{"id": m} for m in KNOWN_FREE_MODELS]
        if not filtered_free:
            die(
                "no explicitly free models found; refusing to label accessible paid models as free"
            )
        model_items = filtered_free
    if args.filter_model:
        pattern = re.compile(args.filter_model, re.IGNORECASE)
        model_items = [
            item for item in model_items if pattern.search(str(item.get("id", "")))
        ]
    if args.include_regex:
        pattern = re.compile(args.include_regex, re.IGNORECASE)
        model_items = [
            item for item in model_items if pattern.search(str(item.get("id", "")))
        ]
    if args.exclude_regex:
        pattern = re.compile(args.exclude_regex, re.IGNORECASE)
        model_items = [
            item for item in model_items if not pattern.search(str(item.get("id", "")))
        ]
    if args.coder_only:
        coder_pattern = re.compile(
            r"code|coder|qwen.*code|deepseek.*coder|starcoder|codellama|dev",
            re.IGNORECASE,
        )
        model_items = [
            item
            for item in model_items
            if coder_pattern.search(str(item.get("id", "")))
        ]
    if args.min_context:
        filtered: list[dict[str, Any]] = []
        for item in model_items:
            ctx = (
                item.get("context_length")
                or item.get("context_window")
                or item.get("max_tokens")
            )
            if ctx is not None:
                try:
                    if int(ctx) >= args.min_context:
                        filtered.append(item)
                except (ValueError, TypeError):
                    filtered.append(item)
            else:
                filtered.append(item)
        model_items = filtered
    if args.limit:
        model_items = unique_models(model_items)[: args.limit]
    if not model_items:
        die("model list is empty after filtering")

    configs = to_model_configs(
        model_items,
        base_url,
        env_key,
        args.request_timeout_ms,
        args.max_retries,
        args.context_window,
    )
    default_model = choose_default_model(configs, args.default_model)

    settings = load_json(settings_path)
    repairs = normalize_existing_providers(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})

    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", args.approval_mode)
    settings["security"].setdefault("auth", {})
    settings["security"]["auth"]["selectedType"] = protocol
    apply_root_admin_emails(settings)
    settings["model"]["name"] = default_model
    settings["model"]["maxSessionTurns"] = args.max_session_turns
    settings["modelProviders"][protocol] = configs

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = None if args.no_backup else backup(settings_path)
    atomic_write_json(settings_path, settings)
    print(f"Installed Qwen settings: {settings_path}")
    print(f"Provider protocol: {protocol}")
    print(f"Models configured: {len(configs)}")
    print(f"Default model: {default_model}")
    print(f"Credential env key: {env_key}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    for repair in repairs:
        print(f"Repaired: {repair}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    errors = validate_settings(settings)
    if errors:
        for error in errors:
            eprint(f"ERROR: {error}")
        return 1
    providers = settings.get("modelProviders", {})
    total = sum(len(v) for v in providers.values() if isinstance(v, list))
    print(f"VALID: {path}")
    print(f"Protocols: {', '.join(providers) or '(none)'}")
    print(f"Models: {total}")
    return 0


def command_repair(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_existing_providers(settings)
    settings["$version"] = 4
    errors = validate_settings(settings)
    if errors:
        die("cannot safely repair configuration:\n- " + "\n- ".join(errors))
    if not args.dry_run:
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Repaired: {path}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
    else:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
    if repairs:
        for repair in repairs:
            print(f"- {repair}", file=sys.stderr if args.dry_run else sys.stdout)
    else:
        print("No structural repair required.")
    return 0


def command_snapshot(args: argparse.Namespace) -> int:
    settings_path = pathlib.Path(args.settings).expanduser()
    if args.action == "export":
        settings = load_json(settings_path)
        errors = validate_settings(settings)
        if errors:
            die("cannot export invalid settings:\n- " + "\n- ".join(errors))
        bundle = build_snapshot_bundle(settings, settings_path)
        output = pathlib.Path(args.output).expanduser()
        if args.dry_run:
            json.dump(bundle, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported snapshot: {output}")
        return 0

    if args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        settings, meta = load_snapshot_settings(source)
        if not isinstance(settings, dict):
            die("snapshot must contain a settings object")
        errors = validate_settings(settings)
        if errors:
            die("cannot import invalid settings:\n- " + "\n- ".join(errors))
        if args.dry_run:
            json.dump(
                {
                    "format": meta.get("format", SNAPSHOT_FORMAT),
                    "createdAt": meta.get("createdAt"),
                    "source": meta.get("source"),
                    "settings": settings,
                },
                sys.stdout,
                indent=2,
                ensure_ascii=False,
            )
            print()
            return 0
        saved_backup = backup(settings_path)
        atomic_write_json(settings_path, settings)
        print(f"Imported snapshot: {settings_path}")
        if meta.get("createdAt"):
            print(f"Snapshot createdAt: {meta['createdAt']}")
        if meta.get("source"):
            print(f"Snapshot source: {meta['source']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0

    if args.action == "sync":
        snapshot_path = pathlib.Path(args.snapshot).expanduser()
        settings_mtime = path_mtime(settings_path)
        snapshot_mtime = path_mtime(snapshot_path)
        mode = args.mode

        if mode == "push" or (mode == "mirror" and settings_mtime >= snapshot_mtime):
            settings = load_json(settings_path)
            errors = validate_settings(settings)
            if errors:
                die("cannot export invalid settings:\n- " + "\n- ".join(errors))
            bundle = build_snapshot_bundle(settings, settings_path)
            if args.dry_run:
                json.dump(bundle, sys.stdout, indent=2, ensure_ascii=False)
                print()
                return 0
            snapshot_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Synced snapshot: {snapshot_path}")
            print("Direction: push")
            return 0

        settings, meta = load_snapshot_settings(snapshot_path)
        if not isinstance(settings, dict):
            die("snapshot must contain a settings object")
        errors = validate_settings(settings)
        if errors:
            die("cannot import invalid settings:\n- " + "\n- ".join(errors))
        if args.dry_run:
            json.dump(
                {
                    "format": meta.get("format", SNAPSHOT_FORMAT),
                    "createdAt": meta.get("createdAt"),
                    "source": meta.get("source"),
                    "settings": settings,
                },
                sys.stdout,
                indent=2,
                ensure_ascii=False,
            )
            print()
            return 0
        saved_backup = backup(settings_path)
        atomic_write_json(settings_path, settings)
        print(f"Synced settings: {settings_path}")
        print("Direction: pull")
        if meta.get("createdAt"):
            print(f"Snapshot createdAt: {meta['createdAt']}")
        if meta.get("source"):
            print(f"Snapshot source: {meta['source']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0

    if args.action == "watch":
        iterations = args.iterations
        count = 0
        while iterations is None or count < iterations:
            sync_args = argparse.Namespace(**{**vars(args), "action": "sync"})
            command_snapshot(sync_args)
            count += 1
            if iterations is None or count < iterations:
                time.sleep(args.interval)
        print(f"Watched snapshot: {args.snapshot}")
        return 0

    die(f"unsupported snapshot action: {args.action}")


def command_providers(args: argparse.Namespace) -> int:
    if args.action == "add":
        if args.target != "all":
            die("usage: qwen-omega providers add all")
        if args.free:
            env_root = pathlib.Path(args.env_root).expanduser()
            env = read_env_files(env_root)
            path = pathlib.Path(args.settings).expanduser()
            settings = load_json(path)
            repairs = normalize_existing_providers(settings)
            settings["$version"] = 4
            settings.setdefault("general", {})
            settings.setdefault("ui", {})
            settings.setdefault("privacy", {})
            settings.setdefault("tools", {})
            settings.setdefault("security", {})
            settings.setdefault("model", {})
            settings["general"].setdefault("enableAutoUpdate", True)
            settings["ui"].setdefault("showMemoryUsage", True)
            settings["privacy"].setdefault("usageStatisticsEnabled", False)
            settings["tools"].setdefault("approvalMode", "default")
            settings["security"].setdefault("auth", {})
            settings["security"]["auth"]["selectedType"] = "openai"
            apply_root_admin_emails(settings)

            providers = settings.setdefault("modelProviders", {})
            openai_configs = providers.setdefault("openai", [])
            if not isinstance(openai_configs, list):
                die("modelProviders.openai must be an array")

            retained_configs = [
                item
                for item in openai_configs
                if isinstance(item, dict) and not is_placeholder_provider_entry(item)
            ]
            retained_ids = {
                str(item.get("id"))
                for item in retained_configs
                if isinstance(item.get("id"), str)
            }
            new_configs: list[dict[str, Any]] = []
            seen_keys: set[str] = set()
            for key, preset in sorted(PRESETS.items()):
                if not provider_enabled(key, preset, env):
                    continue
                model_items = build_free_model_items(
                    key,
                    preset,
                    env,
                    args.timeout,
                    args.insecure,
                    args.auto_fallback,
                )
                if not model_items:
                    eprint(f"WARNING: no free models found for {key}; skipping")
                    continue
                base_url = normalize_url(
                    env.get(BASE_URL_HINT_ENV.get(key, ""), preset.base_url)
                )
                configs = to_model_configs(
                    model_items,
                    base_url,
                    preset.env_key,
                    120000,
                    3,
                    None,
                )
                if not configs:
                    continue
                added_for_provider = False
                for config in configs:
                    model_id = str(config.get("id", "")).strip()
                    if not model_id or model_id in retained_ids or model_id in seen_keys:
                        continue
                    new_configs.append(config)
                    seen_keys.add(model_id)
                    added_for_provider = True
                if not added_for_provider:
                    eprint(f"WARNING: provider {key} yielded only duplicate models")

            openai_configs[:] = retained_configs + new_configs

            errors = validate_settings(settings)
            if errors:
                die("generated configuration failed validation:\n- " + "\n- ".join(errors))

            if args.dry_run:
                json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
                print()
                return 0

            saved_backup = backup(path)
            atomic_write_json(path, settings)
            print(f"Updated Qwen settings: {path}")
            print(f"Added free models: {len(new_configs)}")
            print(f"Scanned env root: {env_root}")
            if repairs:
                for repair in repairs:
                    print(f"Repaired: {repair}")
            if saved_backup:
                print(f"Backup: {saved_backup}")
            return 0

        path = pathlib.Path(args.settings).expanduser()
        settings = load_json(path)
        repairs = normalize_existing_providers(settings)
        settings["$version"] = 4
        settings.setdefault("general", {})
        settings.setdefault("ui", {})
        settings.setdefault("privacy", {})
        settings.setdefault("tools", {})
        settings.setdefault("security", {})
        settings.setdefault("model", {})
        settings["general"].setdefault("enableAutoUpdate", True)
        settings["ui"].setdefault("showMemoryUsage", True)
        settings["privacy"].setdefault("usageStatisticsEnabled", False)
        settings["tools"].setdefault("approvalMode", "default")
        settings["security"].setdefault("auth", {})
        apply_root_admin_emails(settings)

        providers = settings.setdefault("modelProviders", {})
        openai_configs = providers.setdefault("openai", [])
        if not isinstance(openai_configs, list):
            die("modelProviders.openai must be an array")

        existing_ids = {
            str(item.get("id"))
            for item in openai_configs
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        added: list[str] = []
        for key, preset in sorted(PRESETS.items()):
            model_id = f"{key}-provider"
            if model_id in existing_ids:
                continue
            openai_configs.append(
                {
                    "id": model_id,
                    "name": preset.name,
                    "description": (
                        f"Provider preset for {preset.name}; replace the placeholder "
                        f"model id with a real model supported by this provider."
                    ),
                    "baseUrl": normalize_url(preset.base_url),
                    "envKey": preset.env_key,
                    "generationConfig": {
                        "timeout": 120000,
                        "maxRetries": 3,
                    },
                }
            )
            existing_ids.add(model_id)
            added.append(key)

        errors = validate_settings(settings)
        if errors:
            die("generated configuration failed validation:\n- " + "\n- ".join(errors))

        if args.dry_run:
            json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0

        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Updated Qwen settings: {path}")
        print(f"Added provider presets: {len(added)}")
        if repairs:
            for repair in repairs:
                print(f"Repaired: {repair}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0

    query = args.query.lower() if args.query else None
    print("Available Provider Presets:")
    print("-" * 80)
    fmt = "{:<16} {:<24} {:<32} {:<20}"
    print(fmt.format("KEY", "NAME", "BASE URL", "ENV KEY"))
    print("-" * 80)
    for key, p in sorted(PRESETS.items()):
        if (
            query
            and query not in key
            and query not in p.name.lower()
            and query not in p.base_url.lower()
        ):
            continue
        print(fmt.format(key, p.name[:24], p.base_url[:32], p.env_key))
    return 0


def _prompt_template_from_markdown(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    name = path.stem
    if lines and lines[0].lstrip().startswith("#"):
        heading = lines[0].lstrip("#").strip()
        if heading:
            name = heading
            text = "\n".join(lines[1:]).strip() or text
    template_id = slugify(path.stem)
    return {"id": template_id, "name": name, "content": text}


def _load_prompt_templates_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        templates: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
                templates.append(_prompt_template_from_markdown(path))
        return templates
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("promptTemplates", payload.get("templates", []))
        if not isinstance(payload, list):
            die("prompt template JSON must be an array or an object with promptTemplates")
        templates = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            template_id = str(item.get("id", "")).strip()
            content = str(item.get("content", "")).strip()
            if not template_id or not content:
                continue
            templates.append(
                {
                    "id": template_id,
                    "name": str(item.get("name") or template_id).strip(),
                    "content": content,
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                }
            )
        return templates
    return [_prompt_template_from_markdown(source)]


def _find_prompt_template(templates: list[dict[str, Any]], template_id: str) -> dict[str, Any] | None:
    for template in templates:
        if str(template.get("id")) == template_id:
            return template
    return None


def render_prompt_md(template: dict[str, Any]) -> str:
    title = str(template.get("name") or template.get("id") or "Prompt Template").strip()
    lines = [f"# {title}", ""]
    for key, label in (("id", "ID"), ("description", "Description")):
        value = template.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"- {label}: {value.strip()}")
    tags = template.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            lines.append(f"- Tags: {tag_line}")
    content = str(template.get("content") or "").strip()
    if content:
        lines.extend(["", "## Content", content])
    return "\n".join(lines).strip() + "\n"


def render_prompt_html(template: dict[str, Any]) -> str:
    title = html_escape(str(template.get("name") or template.get("id") or "Prompt Template"))
    template_id = html_escape(str(template.get("id") or "prompt"))
    content = html_escape(str(template.get("content") or ""))
    meta_parts: list[str] = []
    description = template.get("description")
    if isinstance(description, str) and description.strip():
        meta_parts.append(f"<p class=\"meta\">Description: {html_escape(description.strip())}</p>")
    tags = template.get("tags")
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            meta_parts.append("<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>")
    body_html = f"<pre class=\"prompt-body\">{content}</pre>" if content else "<pre class=\"prompt-body\"></pre>"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-prompt-id=\"{template_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Prompt ID: {template_id}</p>
    {''.join(meta_parts)}
    {body_html}
  </article>
</body>
</html>
"""


def command_prompts(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_prompt_templates(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    templates = settings.setdefault("promptTemplates", [])
    if not isinstance(templates, list):
        die("promptTemplates must be an array")

    if args.action in (None, "list"):
        print("Prompt Templates:")
        print("-" * 80)
        if not templates:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<18}"
        print(fmt.format("ID", "NAME", "TAGS"))
        print("-" * 80)
        for item in templates:
            tags = ", ".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else ""
            print(fmt.format(item.get("id", ""), str(item.get("name", ""))[:28], tags[:18]))
        return 0

    if args.action == "add":
        template_id = args.id or slugify(args.name)
        new_template: dict[str, Any] = {
            "id": template_id,
            "name": args.name,
            "content": args.content,
        }
        if args.description:
            new_template["description"] = args.description
        if args.tag:
            new_template["tags"] = [tag for tag in args.tag if tag]
        templates[:] = [t for t in templates if str(t.get("id")) != template_id]
        templates.append(new_template)
        templates.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(templates)
        templates[:] = [t for t in templates if str(t.get("id")) != args.id]
        if len(templates) == before:
            die(f"prompt template '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_prompt_templates_source(source)
        if not imported:
            die(f"no prompt templates found in {source}")
        existing = {str(t.get("id")): t for t in templates if isinstance(t, dict)}
        for item in imported:
            existing[str(item.get("id"))] = item
        templates[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"promptTemplates": templates}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported prompt templates: {output}")
        return 0
    elif args.action == "share":
        template = _find_prompt_template(templates, args.id)
        if template is None:
            die(f"prompt template '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(template, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_prompt_html(template)
        else:
            rendered = render_prompt_md(template)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared prompt template: {output}")
        return 0
    elif args.action == "clone":
        template = _find_prompt_template(templates, args.id)
        if template is None:
            die(f"prompt template '{args.id}' not found")
        clone = dict(template)
        clone_id = args.new_id or slugify(f"{str(template.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in templates):
            die(f"prompt template '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.content is not None:
            clone["content"] = args.content
        if args.description is not None:
            clone["description"] = args.description
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        templates.append(clone)
        templates.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"promptTemplate": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned prompt template: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported prompt action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Prompt templates: {len(templates)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _skill_from_markdown(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    name = path.stem
    if lines and lines[0].lstrip().startswith("#"):
        heading = lines[0].lstrip("#").strip()
        if heading:
            name = heading
            text = "\n".join(lines[1:]).strip() or text
    skill_id = slugify(path.stem)
    return {"id": skill_id, "name": name, "content": text}


def _find_skill(skills: list[dict[str, Any]], skill_id: str) -> dict[str, Any] | None:
    for skill in skills:
        if str(skill.get("id")) == skill_id:
            return skill
    return None


def render_skill_md(skill: dict[str, Any]) -> str:
    title = str(skill.get("name") or skill.get("id") or "Skill").strip()
    lines = [f"# {title}", ""]
    for key, label in (("id", "ID"), ("description", "Description")):
        value = skill.get(key)
        if isinstance(value, str) and value.strip():
            lines.extend([f"- {label}: {value.strip()}"])
    tags = skill.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            lines.append(f"- Tags: {tag_line}")
    content = str(skill.get("content") or "").strip()
    if content:
        lines.extend(["", "## Content", content])
    return "\n".join(lines).strip() + "\n"


def render_skill_html(skill: dict[str, Any]) -> str:
    title = html_escape(str(skill.get("name") or skill.get("id") or "Skill"))
    skill_id = html_escape(str(skill.get("id") or "skill"))
    content = html_escape(str(skill.get("content") or ""))
    description = skill.get("description")
    description_html = ""
    if isinstance(description, str) and description.strip():
        description_html = f"<p class=\"meta\">Description: {html_escape(description.strip())}</p>"
    tags = skill.get("tags")
    tag_html = ""
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            tag_html = "<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>"
    body_html = f"<pre class=\"skill-body\">{content}</pre>" if content else "<pre class=\"skill-body\"></pre>"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-skill-id=\"{skill_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Skill ID: {skill_id}</p>
    {description_html}
    {tag_html}
    {body_html}
  </article>
</body>
</html>
"""


def _load_skill_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        skills: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
                skills.append(_skill_from_markdown(path))
        return skills
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("skills", payload.get("items", []))
        if not isinstance(payload, list):
            die("skill JSON must be an array or an object with skills")
        skills = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            skill_id = str(item.get("id", "")).strip()
            content = str(item.get("content", item.get("instructions", ""))).strip()
            if not skill_id or not content:
                continue
            skills.append(
                {
                    "id": skill_id,
                    "name": str(item.get("name") or skill_id).strip(),
                    "content": content,
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                }
            )
        return skills
    return [_skill_from_markdown(source)]


def command_skills(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_skills(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("promptTemplates", [])
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("folders", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    skills = settings.setdefault("skills", [])
    if not isinstance(skills, list):
        die("skills must be an array")

    if args.action in (None, "list"):
        print("Skills:")
        print("-" * 80)
        if not skills:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<18}"
        print(fmt.format("ID", "NAME", "TAGS"))
        print("-" * 80)
        for item in skills:
            tags = ", ".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else ""
            print(fmt.format(str(item.get("id", "")), str(item.get("name", ""))[:28], tags[:18]))
        return 0

    if args.action == "add":
        skill_id = args.id or slugify(args.name)
        new_skill: dict[str, Any] = {
            "id": skill_id,
            "name": args.name,
            "content": args.content,
        }
        if args.description:
            new_skill["description"] = args.description
        if args.tag:
            new_skill["tags"] = [tag for tag in args.tag if tag]
        if args.pinned is not None:
            new_skill["pinned"] = args.pinned
        if args.archived is not None:
            new_skill["archived"] = args.archived
        skills[:] = [s for s in skills if str(s.get("id")) != skill_id]
        skills.append(new_skill)
        skills.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(skills)
        skills[:] = [s for s in skills if str(s.get("id")) != args.id]
        if len(skills) == before:
            die(f"skill '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_skill_source(source)
        if not imported:
            die(f"no skills found in {source}")
        existing = {str(s.get("id")): s for s in skills if isinstance(s, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "skill"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        skills[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"skills": skills}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported skills: {output}")
        return 0
    elif args.action == "share":
        skill = _find_skill(skills, args.id)
        if skill is None:
            die(f"skill '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(skill, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_skill_html(skill)
        else:
            rendered = render_skill_md(skill)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared skill: {output}")
        return 0
    elif args.action == "clone":
        skill = _find_skill(skills, args.id)
        if skill is None:
            die(f"skill '{args.id}' not found")
        clone = dict(skill)
        clone_id = args.new_id or slugify(f"{str(skill.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in skills):
            die(f"skill '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.content is not None:
            clone["content"] = args.content
        if args.description is not None:
            clone["description"] = args.description
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.pinned is not None:
            clone["pinned"] = args.pinned
        if args.archived is not None:
            clone["archived"] = args.archived
        skills.append(clone)
        skills.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"skill": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned skill: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported skills action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Skills: {len(skills)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _plugin_from_markdown(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    name = path.stem
    if lines and lines[0].lstrip().startswith("#"):
        heading = lines[0].lstrip("#").strip()
        if heading:
            name = heading
            text = "\n".join(lines[1:]).strip() or text
    plugin_id = slugify(path.stem)
    return {"id": plugin_id, "name": name, "content": text}


def _find_plugin(plugins: list[dict[str, Any]], plugin_id: str) -> dict[str, Any] | None:
    for plugin in plugins:
        if str(plugin.get("id")) == plugin_id:
            return plugin
    return None


def render_plugin_md(plugin: dict[str, Any]) -> str:
    title = str(plugin.get("name") or plugin.get("id") or "Plugin").strip()
    lines = [f"# {title}", ""]
    for key, label in (("id", "ID"), ("description", "Description"), ("url", "URL")):
        value = plugin.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"- {label}: {value.strip()}")
    for key, label in (
        ("tools", "Tools"),
        ("knowledge", "Knowledge"),
        ("skills", "Skills"),
        ("events", "Events"),
    ):
        values = plugin.get(key)
        if isinstance(values, list) and values:
            joined = ", ".join(str(value) for value in values if str(value).strip())
            if joined:
                lines.append(f"- {label}: {joined}")
    tags = plugin.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            lines.append(f"- Tags: {tag_line}")
    if plugin.get("enabled") is not None:
        lines.append(f"- Enabled: {bool(plugin['enabled'])}")
    if plugin.get("archived") is not None:
        lines.append(f"- Archived: {bool(plugin['archived'])}")
    content = str(plugin.get("content") or "").strip()
    if content:
        lines.extend(["", "## Content", content])
    return "\n".join(lines).strip() + "\n"


def render_plugin_html(plugin: dict[str, Any]) -> str:
    title = html_escape(str(plugin.get("name") or plugin.get("id") or "Plugin"))
    plugin_id = html_escape(str(plugin.get("id") or "plugin"))
    content = html_escape(str(plugin.get("content") or ""))
    meta_parts: list[str] = []
    for key, label in (("description", "Description"), ("url", "URL")):
        value = plugin.get(key)
        if isinstance(value, str) and value.strip():
            meta_parts.append(f"<p class=\"meta\">{label}: {html_escape(value.strip())}</p>")
    for key, label in (
        ("tools", "Tools"),
        ("knowledge", "Knowledge"),
        ("skills", "Skills"),
        ("events", "Events"),
    ):
        values = plugin.get(key)
        if isinstance(values, list):
            cleaned = [html_escape(str(value)) for value in values if str(value).strip()]
            if cleaned:
                meta_parts.append(f"<p class=\"meta\">{label}: " + ", ".join(cleaned) + "</p>")
    tags = plugin.get("tags")
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            meta_parts.append("<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>")
    if plugin.get("enabled") is not None:
        meta_parts.append(
            f"<p class=\"meta\">Enabled: {html_escape(str(bool(plugin['enabled'])))}</p>"
        )
    if plugin.get("archived") is not None:
        meta_parts.append(
            f"<p class=\"meta\">Archived: {html_escape(str(bool(plugin['archived'])))}</p>"
        )
    body_html = (
        f"<pre class=\"plugin-body\">{content}</pre>" if content else "<pre class=\"plugin-body\"></pre>"
    )
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-plugin-id=\"{plugin_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Plugin ID: {plugin_id}</p>
    {''.join(meta_parts)}
    {body_html}
  </article>
</body>
</html>
"""


def _load_plugin_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        plugins: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
                plugins.append(_plugin_from_markdown(path))
        return plugins
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("plugins", payload.get("items", []))
        if not isinstance(payload, list):
            die("plugin JSON must be an array or an object with plugins")
        plugins = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            plugin_id = str(item.get("id", "")).strip()
            content = str(item.get("content", item.get("instructions", ""))).strip()
            if not plugin_id or not content:
                continue
            plugins.append(
                {
                    "id": plugin_id,
                    "name": str(item.get("name") or plugin_id).strip(),
                    "content": content,
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                }
            )
        return plugins
    return [_plugin_from_markdown(source)]


def command_plugins(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_plugins(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("promptTemplates", [])
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("folders", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("skills", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    plugins = settings.setdefault("plugins", [])
    if not isinstance(plugins, list):
        die("plugins must be an array")

    if args.action in (None, "list"):
        print("Plugins:")
        print("-" * 80)
        if not plugins:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<18}"
        print(fmt.format("ID", "NAME", "TAGS"))
        print("-" * 80)
        for item in plugins:
            tags = ", ".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else ""
            print(fmt.format(str(item.get("id", "")), str(item.get("name", ""))[:28], tags[:18]))
        return 0

    if args.action == "add":
        plugin_id = args.id or slugify(args.name)
        new_plugin: dict[str, Any] = {
            "id": plugin_id,
            "name": args.name,
            "content": args.content,
        }
        if args.description:
            new_plugin["description"] = args.description
        if args.tag:
            new_plugin["tags"] = [tag for tag in args.tag if tag]
        if args.tool:
            new_plugin["tools"] = [tool for tool in args.tool if tool]
        if args.knowledge:
            new_plugin["knowledge"] = [item for item in args.knowledge if item]
        if args.skill:
            new_plugin["skills"] = [skill for skill in args.skill if skill]
        if args.event:
            new_plugin["events"] = [event for event in args.event if event]
        if args.url:
            new_plugin["url"] = args.url
        if args.enabled is not None:
            new_plugin["enabled"] = args.enabled
        if args.archived is not None:
            new_plugin["archived"] = args.archived
        plugins[:] = [p for p in plugins if str(p.get("id")) != plugin_id]
        plugins.append(new_plugin)
        plugins.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(plugins)
        plugins[:] = [p for p in plugins if str(p.get("id")) != args.id]
        if len(plugins) == before:
            die(f"plugin '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_plugin_source(source)
        if not imported:
            die(f"no plugins found in {source}")
        existing = {str(p.get("id")): p for p in plugins if isinstance(p, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "plugin"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        plugins[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"plugins": plugins}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported plugins: {output}")
        return 0
    elif args.action == "share":
        plugin = _find_plugin(plugins, args.id)
        if plugin is None:
            die(f"plugin '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(plugin, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_plugin_html(plugin)
        else:
            rendered = render_plugin_md(plugin)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared plugin: {output}")
        return 0
    elif args.action == "clone":
        plugin = _find_plugin(plugins, args.id)
        if plugin is None:
            die(f"plugin '{args.id}' not found")
        clone = dict(plugin)
        clone_id = args.new_id or slugify(f"{str(plugin.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in plugins):
            die(f"plugin '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.content is not None:
            clone["content"] = args.content
        if args.description is not None:
            clone["description"] = args.description
        if args.url is not None:
            clone["url"] = args.url
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.tool is not None:
            clone["tools"] = [tool for tool in args.tool if tool]
        if args.knowledge is not None:
            clone["knowledge"] = [item for item in args.knowledge if item]
        if args.skill is not None:
            clone["skills"] = [skill for skill in args.skill if skill]
        if args.event is not None:
            clone["events"] = [event for event in args.event if event]
        if args.enabled is not None:
            clone["enabled"] = args.enabled
        if args.archived is not None:
            clone["archived"] = args.archived
        plugins.append(clone)
        plugins.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"plugin": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned plugin: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported plugins action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Plugins: {len(plugins)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _pipeline_from_markdown(path: pathlib.Path) -> dict[str, Any]:
    return _plugin_from_markdown(path)


def _find_pipeline(pipelines: list[dict[str, Any]], pipeline_id: str) -> dict[str, Any] | None:
    return _find_plugin(pipelines, pipeline_id)


def render_pipeline_md(pipeline: dict[str, Any]) -> str:
    return render_plugin_md(pipeline)


def render_pipeline_html(pipeline: dict[str, Any]) -> str:
    return render_plugin_html(pipeline)


def _load_pipeline_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        pipelines: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
                pipelines.append(_pipeline_from_markdown(path))
        return pipelines
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("pipelines", payload.get("items", []))
        if not isinstance(payload, list):
            die("pipeline JSON must be an array or an object with pipelines")
        pipelines = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            pipeline_id = str(item.get("id", "")).strip()
            content = str(item.get("content", item.get("instructions", ""))).strip()
            if not pipeline_id or not content:
                continue
            pipelines.append(
                {
                    "id": pipeline_id,
                    "name": str(item.get("name") or pipeline_id).strip(),
                    "content": content,
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                }
            )
        return pipelines
    return [_pipeline_from_markdown(source)]


def command_pipelines(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_pipelines(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("promptTemplates", [])
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("folders", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("skills", [])
    settings.setdefault("plugins", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    pipelines = settings.setdefault("pipelines", [])
    if not isinstance(pipelines, list):
        die("pipelines must be an array")

    if args.action in (None, "list"):
        print("Pipelines:")
        print("-" * 80)
        if not pipelines:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<18}"
        print(fmt.format("ID", "NAME", "TAGS"))
        print("-" * 80)
        for item in pipelines:
            tags = ", ".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else ""
            print(fmt.format(str(item.get("id", "")), str(item.get("name", ""))[:28], tags[:18]))
        return 0

    if args.action == "add":
        pipeline_id = args.id or slugify(args.name)
        new_pipeline: dict[str, Any] = {
            "id": pipeline_id,
            "name": args.name,
            "content": args.content,
        }
        if args.description:
            new_pipeline["description"] = args.description
        if args.tag:
            new_pipeline["tags"] = [tag for tag in args.tag if tag]
        if args.tool:
            new_pipeline["tools"] = [tool for tool in args.tool if tool]
        if args.knowledge:
            new_pipeline["knowledge"] = [item for item in args.knowledge if item]
        if args.skill:
            new_pipeline["skills"] = [skill for skill in args.skill if skill]
        if args.event:
            new_pipeline["events"] = [event for event in args.event if event]
        if args.url:
            new_pipeline["url"] = args.url
        if args.enabled is not None:
            new_pipeline["enabled"] = args.enabled
        if args.archived is not None:
            new_pipeline["archived"] = args.archived
        pipelines[:] = [p for p in pipelines if str(p.get("id")) != pipeline_id]
        pipelines.append(new_pipeline)
        pipelines.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(pipelines)
        pipelines[:] = [p for p in pipelines if str(p.get("id")) != args.id]
        if len(pipelines) == before:
            die(f"pipeline '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_pipeline_source(source)
        if not imported:
            die(f"no pipelines found in {source}")
        existing = {str(p.get("id")): p for p in pipelines if isinstance(p, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "pipeline"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        pipelines[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"pipelines": pipelines}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported pipelines: {output}")
        return 0
    elif args.action == "share":
        pipeline = _find_pipeline(pipelines, args.id)
        if pipeline is None:
            die(f"pipeline '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(pipeline, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_pipeline_html(pipeline)
        else:
            rendered = render_pipeline_md(pipeline)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared pipeline: {output}")
        return 0
    elif args.action == "clone":
        pipeline = _find_pipeline(pipelines, args.id)
        if pipeline is None:
            die(f"pipeline '{args.id}' not found")
        clone = dict(pipeline)
        clone_id = args.new_id or slugify(f"{str(pipeline.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in pipelines):
            die(f"pipeline '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.content is not None:
            clone["content"] = args.content
        if args.description is not None:
            clone["description"] = args.description
        if args.url is not None:
            clone["url"] = args.url
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.tool is not None:
            clone["tools"] = [tool for tool in args.tool if tool]
        if args.knowledge is not None:
            clone["knowledge"] = [item for item in args.knowledge if item]
        if args.skill is not None:
            clone["skills"] = [skill for skill in args.skill if skill]
        if args.event is not None:
            clone["events"] = [event for event in args.event if event]
        if args.enabled is not None:
            clone["enabled"] = args.enabled
        if args.archived is not None:
            clone["archived"] = args.archived
        pipelines.append(clone)
        pipelines.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"pipeline": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned pipeline: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported pipelines action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Pipelines: {len(pipelines)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def normalize_filters(settings: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_pipelines_registry(settings, "filters")


def normalize_actions(settings: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_pipelines_registry(settings, "actions")


def normalize_pipelines_registry(settings: dict[str, Any], key: str) -> list[dict[str, Any]]:
    registry = settings.get(key)
    if registry is None:
        settings[key] = []
        return []
    if isinstance(registry, list):
        normalized: list[dict[str, Any]] = []
        for item in registry:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            name = item.get("name")
            content = item.get("content", item.get("instructions"))
            if not isinstance(item_id, str) or not item_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = item_id.strip()
            if not isinstance(content, str) or not content.strip():
                continue
            normalized_item: dict[str, Any] = {
                "id": item_id.strip(),
                "name": str(name).strip(),
                "content": content,
            }
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized_item["description"] = str(item["description"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized_item["tags"] = tags
            for extra_key in ("tools", "knowledge", "skills", "events"):
                values = item.get(extra_key)
                if isinstance(values, list):
                    cleaned = [str(entry).strip() for entry in values if str(entry).strip()]
                    if cleaned:
                        normalized_item[extra_key] = cleaned
            if isinstance(item.get("url"), str) and str(item["url"]).strip():
                normalized_item["url"] = str(item["url"]).strip()
            if item.get("enabled") is not None:
                normalized_item["enabled"] = bool(item["enabled"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings[key] = normalized
        return normalized
    if isinstance(registry, dict):
        normalized = []
        for item_key, value in registry.items():
            if isinstance(value, str):
                normalized.append(
                    {"id": str(item_key).strip(), "name": str(item_key).strip(), "content": value}
                )
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(item_key).strip())
                item.setdefault("name", str(item_key).strip())
                if isinstance(item.get("content"), str) and item["content"].strip():
                    normalized.append(item)
                elif isinstance(item.get("instructions"), str) and item["instructions"].strip():
                    item["content"] = item.pop("instructions")
                    normalized.append(item)
        settings[key] = normalized
        return normalized
    settings[key] = []
    return []


def _manifest_from_markdown(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    name = path.stem
    if lines and lines[0].lstrip().startswith("#"):
        heading = lines[0].lstrip("#").strip()
        if heading:
            name = heading
            text = "\n".join(lines[1:]).strip() or text
    return {"id": slugify(path.stem), "name": name, "content": text}


def _find_manifest(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for item in items:
        if str(item.get("id")) == item_id:
            return item
    return None


def _render_manifest_md(item: dict[str, Any], title_label: str) -> str:
    title = str(item.get("name") or item.get("id") or title_label).strip()
    lines = [f"# {title}", ""]
    for key, label in (("id", "ID"), ("description", "Description"), ("url", "URL")):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"- {label}: {value.strip()}")
    for key, label in (("tools", "Tools"), ("knowledge", "Knowledge"), ("skills", "Skills"), ("events", "Events")):
        values = item.get(key)
        if isinstance(values, list) and values:
            joined = ", ".join(str(value) for value in values if str(value).strip())
            if joined:
                lines.append(f"- {label}: {joined}")
    tags = item.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            lines.append(f"- Tags: {tag_line}")
    if item.get("enabled") is not None:
        lines.append(f"- Enabled: {bool(item['enabled'])}")
    if item.get("archived") is not None:
        lines.append(f"- Archived: {bool(item['archived'])}")
    content = str(item.get("content") or "").strip()
    if content:
        lines.extend(["", "## Content", content])
    return "\n".join(lines).strip() + "\n"


def _render_manifest_html(item: dict[str, Any], title_label: str, data_attr: str) -> str:
    title = html_escape(str(item.get("name") or item.get("id") or title_label))
    item_id = html_escape(str(item.get("id") or title_label.lower()))
    content = html_escape(str(item.get("content") or ""))
    meta_parts: list[str] = []
    for key, label in (("description", "Description"), ("url", "URL")):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            meta_parts.append(f"<p class=\"meta\">{label}: {html_escape(value.strip())}</p>")
    for key, label in (("tools", "Tools"), ("knowledge", "Knowledge"), ("skills", "Skills"), ("events", "Events")):
        values = item.get(key)
        if isinstance(values, list):
            cleaned = [html_escape(str(value)) for value in values if str(value).strip()]
            if cleaned:
                meta_parts.append(f"<p class=\"meta\">{label}: " + ", ".join(cleaned) + "</p>")
    tags = item.get("tags")
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            meta_parts.append("<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>")
    if item.get("enabled") is not None:
        meta_parts.append(f"<p class=\"meta\">Enabled: {html_escape(str(bool(item['enabled'])) )}</p>")
    if item.get("archived") is not None:
        meta_parts.append(f"<p class=\"meta\">Archived: {html_escape(str(bool(item['archived'])) )}</p>")
    body_html = f"<pre class=\"manifest-body\">{content}</pre>" if content else "<pre class=\"manifest-body\"></pre>"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-{data_attr}=\"{item_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">{title_label} ID: {item_id}</p>
    {''.join(meta_parts)}
    {body_html}
  </article>
</body>
</html>
"""


def _load_manifest_source(source: pathlib.Path, key: str) -> list[dict[str, Any]]:
    if source.is_dir():
        items: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
                items.append(_manifest_from_markdown(path))
        return items
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get(key, payload.get("items", []))
        if not isinstance(payload, list):
            die(f"{key[:-1]} JSON must be an array or an object with {key}")
        items = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).strip()
            content = str(item.get("content", item.get("instructions", ""))).strip()
            if not item_id or not content:
                continue
            items.append(
                {
                    "id": item_id,
                    "name": str(item.get("name") or item_id).strip(),
                    "content": content,
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                }
            )
        return items
    return [_manifest_from_markdown(source)]


def _command_manifest_registry(
    args: argparse.Namespace,
    registry_key: str,
    title_label: str,
    data_attr: str,
) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_pipelines_registry(settings, registry_key)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("promptTemplates", [])
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("folders", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("skills", [])
    settings.setdefault("plugins", [])
    settings.setdefault("pipelines", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    registry = settings.setdefault(registry_key, [])
    if not isinstance(registry, list):
        die(f"{registry_key} must be an array")

    if args.action in (None, "list"):
        print(f"{title_label}s:")
        print("-" * 80)
        if not registry:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<18}"
        print(fmt.format("ID", "NAME", "TAGS"))
        print("-" * 80)
        for item in registry:
            tags = ", ".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else ""
            print(fmt.format(str(item.get("id", "")), str(item.get("name", ""))[:28], tags[:18]))
        return 0

    if args.action == "add":
        item_id = args.id or slugify(args.name)
        new_item: dict[str, Any] = {
            "id": item_id,
            "name": args.name,
            "content": args.content,
        }
        if args.description:
            new_item["description"] = args.description
        if args.tag:
            new_item["tags"] = [tag for tag in args.tag if tag]
        if args.tool:
            new_item["tools"] = [tool for tool in args.tool if tool]
        if args.knowledge:
            new_item["knowledge"] = [item for item in args.knowledge if item]
        if args.skill:
            new_item["skills"] = [skill for skill in args.skill if skill]
        if args.event:
            new_item["events"] = [event for event in args.event if event]
        if args.url:
            new_item["url"] = args.url
        if args.enabled is not None:
            new_item["enabled"] = args.enabled
        if args.archived is not None:
            new_item["archived"] = args.archived
        registry[:] = [p for p in registry if str(p.get("id")) != item_id]
        registry.append(new_item)
        registry.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(registry)
        registry[:] = [p for p in registry if str(p.get("id")) != args.id]
        if len(registry) == before:
            die(f"{registry_key[:-1]} '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_manifest_source(source, registry_key)
        if not imported:
            die(f"no {registry_key} found in {source}")
        existing = {str(p.get("id")): p for p in registry if isinstance(p, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or registry_key[:-1]))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        registry[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {registry_key: registry}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported {registry_key}: {output}")
        return 0
    elif args.action == "share":
        item = _find_manifest(registry, args.id)
        if item is None:
            die(f"{registry_key[:-1]} '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(item, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = _render_manifest_html(item, title_label, data_attr)
        else:
            rendered = _render_manifest_md(item, title_label)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared {registry_key[:-1]}: {output}")
        return 0
    elif args.action == "clone":
        item = _find_manifest(registry, args.id)
        if item is None:
            die(f"{registry_key[:-1]} '{args.id}' not found")
        clone = dict(item)
        clone_id = args.new_id or slugify(f"{str(item.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in registry):
            die(f"{registry_key[:-1]} '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.content is not None:
            clone["content"] = args.content
        if args.description is not None:
            clone["description"] = args.description
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.tool is not None:
            clone["tools"] = [tool for tool in args.tool if tool]
        if args.knowledge is not None:
            clone["knowledge"] = [item for item in args.knowledge if item]
        if args.skill is not None:
            clone["skills"] = [skill for skill in args.skill if skill]
        if args.event is not None:
            clone["events"] = [event for event in args.event if event]
        if args.url is not None:
            clone["url"] = args.url
        if args.enabled is not None:
            clone["enabled"] = args.enabled
        if args.archived is not None:
            clone["archived"] = args.archived
        registry.append(clone)
        registry.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({registry_key[:-1]: clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned {registry_key[:-1]}: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported {registry_key} action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"{title_label}s: {len(registry)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def command_filters(args: argparse.Namespace) -> int:
    return _command_manifest_registry(args, "filters", "Filter", "filter-id")


def command_actions(args: argparse.Namespace) -> int:
    return _command_manifest_registry(args, "actions", "Action", "action-id")


def normalize_automations(settings: dict[str, Any]) -> list[dict[str, Any]]:
    automations = settings.get("automations")
    if automations is None:
        settings["automations"] = []
        return []
    if isinstance(automations, list):
        normalized: list[dict[str, Any]] = []
        for item in automations:
            if not isinstance(item, dict):
                continue
            automation_id = item.get("id")
            name = item.get("name")
            prompt = item.get("prompt", item.get("content"))
            schedule = item.get("schedule")
            if not isinstance(automation_id, str) or not automation_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = automation_id.strip()
            if not isinstance(prompt, str) or not prompt.strip():
                continue
            if not isinstance(schedule, str) or not schedule.strip():
                continue
            normalized_item: dict[str, Any] = {
                "id": automation_id.strip(),
                "name": str(name).strip(),
                "prompt": prompt,
                "schedule": schedule.strip(),
            }
            for key in ("timezone", "model", "description"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    normalized_item[key] = value.strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized_item["tags"] = tags
            if item.get("enabled") is not None:
                normalized_item["enabled"] = bool(item["enabled"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings["automations"] = normalized
        return normalized
    if isinstance(automations, dict):
        normalized = []
        for key, value in automations.items():
            if isinstance(value, str):
                normalized.append(
                    {
                        "id": str(key).strip(),
                        "name": str(key).strip(),
                        "prompt": value,
                        "schedule": "manual",
                    }
                )
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("prompt"), str) and item["prompt"].strip():
                    normalized.append(item)
                elif isinstance(item.get("content"), str) and item["content"].strip():
                    item["prompt"] = item.pop("content")
                    normalized.append(item)
        settings["automations"] = normalized
        return normalized
    settings["automations"] = []
    return []


def _automation_from_markdown(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    name = path.stem
    if lines and lines[0].lstrip().startswith("#"):
        heading = lines[0].lstrip("#").strip()
        if heading:
            name = heading
            text = "\n".join(lines[1:]).strip() or text
    return {
        "id": slugify(path.stem),
        "name": name,
        "prompt": text,
        "schedule": "manual",
    }


def _find_automation(automations: list[dict[str, Any]], automation_id: str) -> dict[str, Any] | None:
    for item in automations:
        if str(item.get("id")) == automation_id:
            return item
    return None


def _load_automation_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        items: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
                items.append(_automation_from_markdown(path))
        return items
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("automations", payload.get("items", []))
        if not isinstance(payload, list):
            die("automation JSON must be an array or an object with automations")
        items = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            automation_id = str(item.get("id", "")).strip()
            prompt = str(item.get("prompt", item.get("content", ""))).strip()
            schedule = str(item.get("schedule", "")).strip()
            if not automation_id or not prompt or not schedule:
                continue
            items.append(
                {
                    "id": automation_id,
                    "name": str(item.get("name") or automation_id).strip(),
                    "prompt": prompt,
                    "schedule": schedule,
                    **(
                        {"timezone": str(item["timezone"]).strip()}
                        if isinstance(item.get("timezone"), str)
                        and str(item.get("timezone")).strip()
                        else {}
                    ),
                    **(
                        {"model": str(item["model"]).strip()}
                        if isinstance(item.get("model"), str)
                        and str(item.get("model")).strip()
                        else {}
                    ),
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                    **(
                        {"enabled": bool(item["enabled"])}
                        if item.get("enabled") is not None
                        else {}
                    ),
                    **(
                        {"archived": bool(item["archived"])}
                        if item.get("archived") is not None
                        else {}
                    ),
                }
            )
        return items
    return [_automation_from_markdown(source)]


def _render_automation_md(item: dict[str, Any]) -> str:
    title = str(item.get("name") or item.get("id") or "Automation").strip()
    lines = [f"# {title}", ""]
    for key, label in (("id", "ID"), ("schedule", "Schedule"), ("timezone", "Timezone"), ("model", "Model"), ("description", "Description")):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"- {label}: {value.strip()}")
    tags = item.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            lines.append(f"- Tags: {tag_line}")
    if item.get("enabled") is not None:
        lines.append(f"- Enabled: {bool(item['enabled'])}")
    if item.get("archived") is not None:
        lines.append(f"- Archived: {bool(item['archived'])}")
    prompt = str(item.get("prompt") or item.get("content") or "").strip()
    if prompt:
        lines.extend(["", "## Prompt", prompt])
    return "\n".join(lines).strip() + "\n"


def _render_automation_html(item: dict[str, Any]) -> str:
    title = html_escape(str(item.get("name") or item.get("id") or "Automation"))
    item_id = html_escape(str(item.get("id") or "automation"))
    prompt = html_escape(str(item.get("prompt") or item.get("content") or ""))
    meta_parts: list[str] = []
    for key, label in (("schedule", "Schedule"), ("timezone", "Timezone"), ("model", "Model"), ("description", "Description")):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            meta_parts.append(f"<p class=\"meta\">{label}: {html_escape(value.strip())}</p>")
    tags = item.get("tags")
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            meta_parts.append("<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>")
    if item.get("enabled") is not None:
        meta_parts.append(f"<p class=\"meta\">Enabled: {html_escape(str(bool(item['enabled'])))}</p>")
    if item.get("archived") is not None:
        meta_parts.append(f"<p class=\"meta\">Archived: {html_escape(str(bool(item['archived'])))}</p>")
    body_html = f"<pre class=\"automation-body\">{prompt}</pre>" if prompt else "<pre class=\"automation-body\"></pre>"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-automation-id=\"{item_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Automation ID: {item_id}</p>
    {''.join(meta_parts)}
    {body_html}
  </article>
</body>
</html>
"""


def command_automations(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_automations(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("promptTemplates", [])
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("folders", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("skills", [])
    settings.setdefault("plugins", [])
    settings.setdefault("pipelines", [])
    settings.setdefault("filters", [])
    settings.setdefault("actions", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    automations = settings.setdefault("automations", [])
    if not isinstance(automations, list):
        die("automations must be an array")

    if args.action in (None, "list"):
        print("Automations:")
        print("-" * 80)
        if not automations:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<24}"
        print(fmt.format("ID", "NAME", "SCHEDULE"))
        print("-" * 80)
        for item in automations:
            print(fmt.format(str(item.get("id", "")), str(item.get("name", ""))[:28], str(item.get("schedule", ""))[:24]))
        return 0

    if args.action == "add":
        automation_id = args.id or slugify(args.name)
        new_item: dict[str, Any] = {
            "id": automation_id,
            "name": args.name,
            "prompt": args.content,
            "schedule": args.schedule,
        }
        if args.timezone:
            new_item["timezone"] = args.timezone
        if args.model:
            new_item["model"] = args.model
        if args.description:
            new_item["description"] = args.description
        if args.tag:
            new_item["tags"] = [tag for tag in args.tag if tag]
        if args.enabled is not None:
            new_item["enabled"] = args.enabled
        if args.archived is not None:
            new_item["archived"] = args.archived
        automations[:] = [a for a in automations if str(a.get("id")) != automation_id]
        automations.append(new_item)
        automations.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(automations)
        automations[:] = [a for a in automations if str(a.get("id")) != args.id]
        if len(automations) == before:
            die(f"automation '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_automation_source(source)
        if not imported:
            die(f"no automations found in {source}")
        existing = {str(a.get("id")): a for a in automations if isinstance(a, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "automation"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        automations[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"automations": automations}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported automations: {output}")
        return 0
    elif args.action == "share":
        item = _find_automation(automations, args.id)
        if item is None:
            die(f"automation '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(item, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = _render_automation_html(item)
        else:
            rendered = _render_automation_md(item)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared automation: {output}")
        return 0
    elif args.action == "clone":
        item = _find_automation(automations, args.id)
        if item is None:
            die(f"automation '{args.id}' not found")
        clone = dict(item)
        clone_id = args.new_id or slugify(f"{str(item.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in automations):
            die(f"automation '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.content is not None:
            clone["prompt"] = args.content
        if args.schedule is not None:
            clone["schedule"] = args.schedule
        if args.timezone is not None:
            clone["timezone"] = args.timezone
        if args.model is not None:
            clone["model"] = args.model
        if args.description is not None:
            clone["description"] = args.description
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.enabled is not None:
            clone["enabled"] = args.enabled
        if args.archived is not None:
            clone["archived"] = args.archived
        automations.append(clone)
        automations.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"automation": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned automation: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported automations action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Automations: {len(automations)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _load_tool_servers_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        servers: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                payload = payload.get("toolServers", payload.get("servers", []))
            if not isinstance(payload, list):
                continue
            for item in payload:
                if isinstance(item, dict):
                    servers.append(item)
        return servers
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        die(f"unable to read tool server source: {source}")
    if isinstance(payload, dict):
        payload = payload.get("toolServers", payload.get("servers", payload))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    die("tool server JSON must be an array or an object with toolServers/servers")


def _find_tool_server(servers: list[dict[str, Any]], tool_id: str) -> dict[str, Any] | None:
    for server in servers:
        if str(server.get("id")) == tool_id:
            return server
    return None


def render_tool_server_md(server: dict[str, Any]) -> str:
    title = str(server.get("name") or server.get("id") or "Tool Server").strip()
    lines = [f"# {title}", ""]
    for key, label in (("id", "ID"), ("type", "Type"), ("description", "Description"), ("auth", "Auth")):
        value = server.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"- {label}: {value.strip()}")
    endpoint = server.get("endpoint", server.get("url"))
    if isinstance(endpoint, str) and endpoint.strip():
        lines.append(f"- Endpoint: {endpoint.strip()}")
    tags = server.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            lines.append(f"- Tags: {tag_line}")
    if server.get("enabled") is not None:
        lines.append(f"- Enabled: {bool(server['enabled'])}")
    return "\n".join(lines).strip() + "\n"


def render_tool_server_html(server: dict[str, Any]) -> str:
    title = html_escape(str(server.get("name") or server.get("id") or "Tool Server"))
    server_id = html_escape(str(server.get("id") or "tool"))
    endpoint = str(server.get("endpoint", server.get("url")) or "").strip()
    meta_parts: list[str] = []
    for key, label in (("type", "Type"), ("description", "Description"), ("auth", "Auth")):
        value = server.get(key)
        if isinstance(value, str) and value.strip():
            meta_parts.append(f"<p class=\"meta\">{label}: {html_escape(value.strip())}</p>")
    if endpoint:
        meta_parts.append(f"<p class=\"meta\">Endpoint: {html_escape(endpoint)}</p>")
    tags = server.get("tags")
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            meta_parts.append("<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>")
    if server.get("enabled") is not None:
        meta_parts.append(f"<p class=\"meta\">Enabled: {html_escape(str(bool(server['enabled'])))}</p>")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-tool-server-id=\"{server_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Tool Server ID: {server_id}</p>
    {''.join(meta_parts)}
  </article>
</body>
</html>
"""


def command_tools(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_tool_servers(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    servers = settings.setdefault("toolServers", [])
    if not isinstance(servers, list):
        die("toolServers must be an array")

    if args.action in (None, "list"):
        print("Tool Servers:")
        print("-" * 80)
        if not servers:
            print("(none)")
            return 0
        fmt = "{:<18} {:<24} {:<14} {:<28}"
        print(fmt.format("ID", "NAME", "TYPE", "ENDPOINT"))
        print("-" * 80)
        for item in servers:
            endpoint = item.get("endpoint") or item.get("url") or ""
            print(
                fmt.format(
                    str(item.get("id", "")),
                    str(item.get("name", ""))[:24],
                    str(item.get("type", ""))[:14],
                    str(endpoint)[:28],
                )
            )
        return 0

    if args.action == "add":
        tool_id = args.id or slugify(args.name)
        new_server: dict[str, Any] = {
            "id": tool_id,
            "name": args.name,
            "type": args.type,
            "endpoint": args.endpoint,
        }
        if args.description:
            new_server["description"] = args.description
        if args.auth:
            new_server["auth"] = args.auth
        if args.tag:
            new_server["tags"] = [tag for tag in args.tag if tag]
        if args.enabled is not None:
            new_server["enabled"] = args.enabled
        servers[:] = [s for s in servers if str(s.get("id")) != tool_id]
        servers.append(new_server)
        servers.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(servers)
        servers[:] = [s for s in servers if str(s.get("id")) != args.id]
        if len(servers) == before:
            die(f"tool server '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_tool_servers_source(source)
        if not imported:
            die(f"no tool servers found in {source}")
        existing = {str(s.get("id")): s for s in servers if isinstance(s, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "tool"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        servers[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"toolServers": servers}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported tool servers: {output}")
        return 0
    elif args.action == "share":
        server = _find_tool_server(servers, args.id)
        if server is None:
            die(f"tool server '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(server, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_tool_server_html(server)
        else:
            rendered = render_tool_server_md(server)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared tool server: {output}")
        return 0
    elif args.action == "clone":
        server = _find_tool_server(servers, args.id)
        if server is None:
            die(f"tool server '{args.id}' not found")
        clone = dict(server)
        clone_id = args.new_id or slugify(f"{str(server.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in servers):
            die(f"tool server '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.type is not None:
            clone["type"] = args.type
        if args.endpoint is not None:
            clone["endpoint"] = args.endpoint
        if args.description is not None:
            clone["description"] = args.description
        if args.auth is not None:
            clone["auth"] = args.auth
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.enabled is not None:
            clone["enabled"] = args.enabled
        servers.append(clone)
        servers.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"toolServer": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned tool server: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported tools action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Tool servers: {len(servers)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _load_knowledge_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        bases: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                payload = payload.get("knowledgeBases", payload.get("bases", []))
            if isinstance(payload, list):
                bases.extend(item for item in payload if isinstance(item, dict))
        return bases
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        die(f"unable to read knowledge source: {source}")
    if isinstance(payload, dict):
        payload = payload.get("knowledgeBases", payload.get("bases", payload))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    die("knowledge base JSON must be an array or an object with knowledgeBases/bases")


def _normalize_knowledge_source_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("knowledgeBases", payload.get("bases", payload.get("items", [])))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _normalize_knowledge_index_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if "documents" in payload:
            return [payload]
        payload = payload.get("knowledgeIndexes", payload.get("indexes", payload.get("items", [])))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def command_kb(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_knowledge_bases(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeIndexes", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    bases = settings.setdefault("knowledgeBases", [])
    if not isinstance(bases, list):
        die("knowledgeBases must be an array")

    if args.action in (None, "list"):
        print("Knowledge Bases:")
        print("-" * 80)
        if not bases:
            print("(none)")
            return 0
        fmt = "{:<18} {:<24} {:<30}"
        print(fmt.format("ID", "NAME", "SOURCE DIR"))
        print("-" * 80)
        for item in bases:
            print(
                fmt.format(
                    str(item.get("id", "")),
                    str(item.get("name", ""))[:24],
                    str(item.get("sourceDir", ""))[:30],
                )
            )
        return 0

    if args.action == "add":
        base_id = args.id or slugify(args.name)
        new_base: dict[str, Any] = {
            "id": base_id,
            "name": args.name,
        }
        if args.source_dir:
            new_base["sourceDir"] = args.source_dir
        if args.description:
            new_base["description"] = args.description
        if args.tag:
            new_base["tags"] = [tag for tag in args.tag if tag]
        if args.enabled is not None:
            new_base["enabled"] = args.enabled
        if args.sources is not None:
            new_base["sources"] = args.sources
        bases[:] = [b for b in bases if str(b.get("id")) != base_id]
        bases.append(new_base)
        bases.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(bases)
        bases[:] = [b for b in bases if str(b.get("id")) != args.id]
        if len(bases) == before:
            die(f"knowledge base '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_knowledge_source(source)
        if not imported:
            die(f"no knowledge bases found in {source}")
        existing = {str(b.get("id")): b for b in bases if isinstance(b, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "knowledge"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        bases[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"knowledgeBases": bases}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported knowledge bases: {output}")
        return 0
    elif args.action == "clone":
        base = next(
            (
                item
                for item in bases
                if isinstance(item, dict) and str(item.get("id")) == args.id
            ),
            None,
        )
        if base is None:
            die(f"knowledge base '{args.id}' not found")
        clone = dict(base)
        clone_id = args.new_id or slugify(f"{str(base.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in bases):
            die(f"knowledge base '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.source_dir is not None:
            clone["sourceDir"] = args.source_dir
        if args.description is not None:
            clone["description"] = args.description
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.enabled is not None:
            clone["enabled"] = args.enabled
        if args.sources is not None:
            clone["sources"] = [source for source in args.sources if source]
        bases.append(clone)
        bases.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"knowledgeBase": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned knowledge base: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    elif args.action == "ingest":
        source_dir = pathlib.Path(args.source_dir).expanduser()
        base_id = args.base_id or slugify(source_dir.name)
        index = build_knowledge_index(base_id, source_dir, args.chunk_size, args.overlap)
        indexes = settings.setdefault("knowledgeIndexes", [])
        if not isinstance(indexes, list):
            die("knowledgeIndexes must be an array")
        indexes[:] = [item for item in indexes if str(item.get("baseId")) != base_id]
        indexes.append(index)
        indexes.sort(key=lambda x: str(x.get("id", "")).lower())

        bases[:] = [b for b in bases if str(b.get("id")) != base_id]
        bases.append(
            {
                "id": base_id,
                "name": args.name or source_dir.name,
                "sourceDir": str(source_dir),
                "description": args.description or f"Indexed knowledge base from {source_dir}",
                "enabled": True,
                "sources": [str(source_dir)],
            }
        )
        bases.sort(key=lambda x: str(x.get("id", "")).lower())
        errors = validate_settings(settings)
        if errors:
            die("generated configuration failed validation:\n- " + "\n- ".join(errors))
        if args.dry_run:
            json.dump(
                {
                    "knowledgeIndex": index,
                    "knowledgeBases": bases,
                    "knowledgeIndexes": indexes,
                },
                sys.stdout,
                indent=2,
                ensure_ascii=False,
            )
            print()
            return 0
        output = pathlib.Path(args.output).expanduser()
        if output.suffix.lower() == ".json":
            output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Exported knowledge index: {output}")
        else:
            output.mkdir(parents=True, exist_ok=True)
            for doc in index["documents"]:
                doc_path = output / f"{doc['id']}.json"
                doc_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            manifest = output / "manifest.json"
            manifest.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Exported knowledge index: {manifest}")
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Updated Qwen settings: {path}")
        print(f"Knowledge index documents: {index['documentCount']}")
        print(f"Knowledge index chunks: {index['chunkCount']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    elif args.action == "refresh":
        base_id = args.base_id
        if not base_id:
            die("--base-id is required for kb refresh")
        base = next((item for item in bases if isinstance(item, dict) and str(item.get("id")) == base_id), None)
        if base is None:
            die(f"knowledge base '{base_id}' not found")
        try:
            source_label, index, refreshed_base = _refresh_knowledge_base_entry(
                base,
                base_id,
                args.chunk_size,
                args.overlap,
                args.timeout,
            )
        except ValueError as exc:
            die(str(exc))
        indexes = settings.setdefault("knowledgeIndexes", [])
        if not isinstance(indexes, list):
            die("knowledgeIndexes must be an array")
        indexes[:] = [item for item in indexes if str(item.get("baseId")) != base_id]
        indexes.append(index)
        indexes.sort(key=lambda x: str(x.get("id", "")).lower())

        bases[:] = [b for b in bases if str(b.get("id")) != base_id]
        bases.append(refreshed_base)
        bases.sort(key=lambda x: str(x.get("id", "")).lower())
        errors = validate_settings(settings)
        if errors:
            die("generated configuration failed validation:\n- " + "\n- ".join(errors))
        if args.dry_run:
            json.dump(
                {
                    "knowledgeIndex": index,
                    "knowledgeBases": bases,
                    "knowledgeIndexes": indexes,
                },
                sys.stdout,
                indent=2,
                ensure_ascii=False,
            )
            print()
            return 0
        output = pathlib.Path(args.output).expanduser()
        if output.suffix.lower() == ".json":
            output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Exported knowledge index: {output}")
        else:
            output.mkdir(parents=True, exist_ok=True)
            for doc in index["documents"]:
                doc_path = output / f"{doc['id']}.json"
                doc_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            manifest = output / "manifest.json"
            manifest.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Exported knowledge index: {manifest}")
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Refreshed knowledge base: {base_id}")
        print(f"Knowledge index documents: {index['documentCount']}")
        print(f"Knowledge index chunks: {index['chunkCount']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    elif args.action == "sync":
        selected_bases = [
            item
            for item in bases
            if isinstance(item, dict)
            and (
                not args.base_id or str(item.get("id")) == args.base_id
            )
        ]
        if args.base_id and not selected_bases:
            die(f"knowledge base '{args.base_id}' not found")
        if not selected_bases:
            die("no knowledge bases to sync")

        indexes = settings.setdefault("knowledgeIndexes", [])
        if not isinstance(indexes, list):
            die("knowledgeIndexes must be an array")

        refreshed_indexes: list[dict[str, Any]] = []
        refreshed_bases: list[dict[str, Any]] = []
        output = pathlib.Path(args.output).expanduser()
        for base in selected_bases:
            base_id = str(base.get("id", "")).strip()
            if not base_id:
                continue
            try:
                source_label, index, refreshed_base = _refresh_knowledge_base_entry(
                    base,
                    base_id,
                    args.chunk_size,
                    args.overlap,
                args.timeout,
            )
            except ValueError as exc:
                die(str(exc))
            indexes[:] = [item for item in indexes if str(item.get("baseId")) != base_id]
            indexes.append(index)
            refreshed_indexes.append(index)
            refreshed_bases.append(refreshed_base)
            if not args.dry_run:
                output.mkdir(parents=True, exist_ok=True)
                (output / f"{base_id}.json").write_text(
                    json.dumps(index, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            print(f"Refreshed knowledge base: {base_id} ({source_label})")

        refreshed_ids = {str(item.get("id")) for item in refreshed_bases}
        remaining_bases = [b for b in bases if str(b.get("id")) not in refreshed_ids]
        remaining_bases.extend(refreshed_bases)
        bases[:] = sorted(remaining_bases, key=lambda x: str(x.get("id", "")).lower())
        indexes.sort(key=lambda x: str(x.get("id", "")).lower())

        errors = validate_settings(settings)
        if errors:
            die("generated configuration failed validation:\n- " + "\n- ".join(errors))

        manifest = {
            "knowledgeBases": bases,
            "knowledgeIndexes": indexes,
            "refreshed": [str(item.get("baseId", "")) for item in refreshed_indexes],
        }
        if args.dry_run:
            json.dump(manifest, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.mkdir(parents=True, exist_ok=True)
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Updated Qwen settings: {path}")
        print(f"Knowledge bases synced: {len(refreshed_indexes)}")
        print(f"Knowledge indexes: {len(indexes)}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    elif args.action == "watch":
        iterations = args.iterations
        count = 0
        while iterations is None or count < iterations:
            sync_args = argparse.Namespace(
                settings=args.settings,
                dry_run=args.dry_run,
                base_id=getattr(args, "base_id", None),
                chunk_size=args.chunk_size,
                overlap=args.overlap,
                timeout=args.timeout,
                output=args.output,
                action="sync",
            )
            command_kb(sync_args)
            count += 1
            if iterations is None or count < iterations:
                time.sleep(args.interval)
        print(f"Watched knowledge bases: {args.output}")
        return 0
    elif args.action == "ingest-url":
        urls = [url.strip() for url in args.urls if url.strip()]
        if not urls:
            die("at least one URL is required")
        documents: list[dict[str, Any]] = []
        for url in urls:
            try:
                documents.append(fetch_web_document(url, args.timeout))
            except (urllib.error.URLError, TimeoutError, ValueError, UnicodeError) as exc:
                die(f"unable to fetch {url}: {exc}")
        base_id = args.base_id or slugify(urls[0])
        index = build_knowledge_index_from_documents(
            base_id,
            ", ".join(urls),
            documents,
            args.chunk_size,
            args.overlap,
        )
        indexes = settings.setdefault("knowledgeIndexes", [])
        if not isinstance(indexes, list):
            die("knowledgeIndexes must be an array")
        indexes[:] = [item for item in indexes if str(item.get("baseId")) != base_id]
        indexes.append(index)
        indexes.sort(key=lambda x: str(x.get("id", "")).lower())

        bases[:] = [b for b in bases if str(b.get("id")) != base_id]
        bases.append(
            {
                "id": base_id,
                "name": args.name or documents[0].get("name") or base_id,
                "sourceDir": ", ".join(urls),
                "description": args.description or f"Ingested web sources for {base_id}",
                "enabled": True,
                "sources": urls,
            }
        )
        bases.sort(key=lambda x: str(x.get("id", "")).lower())
        errors = validate_settings(settings)
        if errors:
            die("generated configuration failed validation:\n- " + "\n- ".join(errors))
        if args.dry_run:
            json.dump(
                {
                    "knowledgeIndex": index,
                    "knowledgeBases": bases,
                    "knowledgeIndexes": indexes,
                },
                sys.stdout,
                indent=2,
                ensure_ascii=False,
            )
            print()
            return 0
        output = pathlib.Path(args.output).expanduser()
        if output.suffix.lower() == ".json":
            output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Exported knowledge index: {output}")
        else:
            output.mkdir(parents=True, exist_ok=True)
            for doc in index["documents"]:
                doc_path = output / f"{doc['id']}.json"
                doc_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            manifest = output / "manifest.json"
            manifest.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Exported knowledge index: {manifest}")
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Updated Qwen settings: {path}")
        print(f"Knowledge index documents: {index['documentCount']}")
        print(f"Knowledge index chunks: {index['chunkCount']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    elif args.action == "query":
        indexes = _load_knowledge_indexes_from_settings(settings)
        if args.index:
            source = pathlib.Path(args.index).expanduser()
            if source.exists():
                indexes.extend(_load_knowledge_indexes_source(source))
            else:
                die(f"knowledge index source not found: {source}")
        matches = _search_knowledge_indexes(indexes, args.query, args.base_id)
        if not matches:
            print("No matches found.")
            return 0
        print("Knowledge Query Results:")
        print("-" * 100)
        fmt = "{:<18} {:<18} {:<24} {:<8} {:<24}"
        print(fmt.format("INDEX", "BASE", "DOCUMENT", "SCORE", "SNIPPET"))
        print("-" * 100)
        for item in matches:
            snippet = str(item.get("snippet", ""))[:24]
            print(
                fmt.format(
                    str(item.get("indexId", ""))[:18],
                    str(item.get("baseId", ""))[:18],
                    str(item.get("title", ""))[:24],
                    str(item.get("score", ""))[:8],
                    snippet,
                )
            )
        return 0
    else:
        die(f"unsupported kb action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Knowledge bases: {len(bases)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _load_note_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        notes: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
                text = path.read_text(encoding="utf-8").strip()
                if not text:
                    continue
                title = path.stem
                lines = text.splitlines()
                if lines and lines[0].lstrip().startswith("#"):
                    heading = lines[0].lstrip("#").strip()
                    if heading:
                        title = heading
                        text = "\n".join(lines[1:]).strip() or text
                notes.append({"id": slugify(path.stem), "title": title, "body": text})
        return notes
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("notes", payload.get("items", []))
        if not isinstance(payload, list):
            die("notes JSON must be an array or an object with notes")
        notes = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            note_id = str(item.get("id", "")).strip()
            body = str(item.get("body", item.get("content", ""))).strip()
            if not note_id or not body:
                continue
            notes.append(
                {
                    "id": note_id,
                    "title": str(item.get("title") or note_id).strip(),
                    "body": body,
                }
            )
        return notes
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    title = source.stem
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        heading = lines[0].lstrip("#").strip()
        if heading:
            title = heading
            text = "\n".join(lines[1:]).strip() or text
    return [{"id": slugify(source.stem), "title": title, "body": text}]


def _note_attachments(note: dict[str, Any]) -> list[str]:
    attachments = note.get("files", note.get("attachments", []))
    if not isinstance(attachments, list):
        return []
    return [str(item).strip() for item in attachments if str(item).strip()]


def _note_images(note: dict[str, Any]) -> list[str]:
    images = note.get("images", [])
    if not isinstance(images, list):
        return []
    return [str(item).strip() for item in images if str(item).strip()]


def render_note_md(note: dict[str, Any]) -> str:
    title = str(note.get("title") or note.get("id") or "Note").strip()
    body = str(note.get("body") or note.get("content") or "").strip()
    parts = [f"# {title}"]
    tags = note.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            parts.extend(["", f"Tags: {tag_line}"])
    attachments = _note_attachments(note)
    if attachments:
        parts.extend(["", f"Attachments: {', '.join(attachments)}"])
    images = _note_images(note)
    if images:
        parts.extend(["", f"Images: {', '.join(images)}"])
    if body:
        parts.extend(["", body])
    return "\n".join(parts).strip() + "\n"


def render_note_html(note: dict[str, Any]) -> str:
    title = html_escape(str(note.get("title") or note.get("id") or "Note"))
    note_id = html_escape(str(note.get("id") or "note"))
    body = html_escape(str(note.get("body") or note.get("content") or ""))
    tags = note.get("tags")
    tag_html = ""
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            tag_html = "<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>"
    attachment_html = ""
    attachments = _note_attachments(note)
    if attachments:
        attachment_html = "<p class=\"tags\">Attachments: " + ", ".join(html_escape(item) for item in attachments) + "</p>"
    image_html = ""
    images = _note_images(note)
    if images:
        image_html = "<p class=\"tags\">Images: " + ", ".join(html_escape(item) for item in images) + "</p>"
    body_html = f"<pre class=\"note-body\">{body}</pre>" if body else "<pre class=\"note-body\"></pre>"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-note-id=\"{note_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Note ID: {note_id}</p>
    {tag_html}
    {attachment_html}
    {image_html}
    {body_html}
  </article>
</body>
</html>
"""


def _load_artifact_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        artifacts: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt", ".html", ".htm"}:
                text = path.read_text(encoding="utf-8").strip()
                if not text:
                    continue
                title = path.stem
                artifacts.append(
                    {
                        "id": slugify(path.stem),
                        "title": title,
                        "content": text,
                        "kind": path.suffix.lstrip("."),
                    }
                )
        return artifacts
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("artifacts", payload.get("items", []))
        if not isinstance(payload, list):
            die("artifact JSON must be an array or an object with artifacts")
        artifacts = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            artifact_id = str(item.get("id", "")).strip()
            content = str(item.get("content", "")).strip()
            if not artifact_id or not content:
                continue
            artifacts.append(
                {
                    "id": artifact_id,
                    "title": str(item.get("title") or artifact_id).strip(),
                    "content": content,
                    **(
                        {"kind": str(item["kind"]).strip()}
                        if isinstance(item.get("kind"), str) and str(item.get("kind")).strip()
                        else {}
                    ),
                }
            )
        return artifacts
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    title = source.stem
    return [{"id": slugify(source.stem), "title": title, "content": text, "kind": source.suffix.lstrip(".") or "text"}]


def command_notes(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_notes(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("artifacts", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    notes = settings.setdefault("notes", [])
    if not isinstance(notes, list):
        die("notes must be an array")

    if args.action in (None, "list"):
        print("Notes:")
        print("-" * 80)
        if not notes:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<10}"
        print(fmt.format("ID", "TITLE", "STATE"))
        print("-" * 80)
        for item in notes:
            state = "pinned" if item.get("pinned") else "active"
            if item.get("archived"):
                state = "archived"
            print(fmt.format(str(item.get("id", "")), str(item.get("title", ""))[:28], state))
        return 0

    if args.action == "add":
        note_id = args.id or slugify(args.title)
        new_note: dict[str, Any] = {
            "id": note_id,
            "title": args.title,
            "body": args.body,
        }
        if args.file:
            new_note["files"] = [item for item in args.file if item]
        if args.image:
            new_note["images"] = [item for item in args.image if item]
        if args.tag:
            new_note["tags"] = [tag for tag in args.tag if tag]
        if args.pinned is not None:
            new_note["pinned"] = args.pinned
        if args.archived is not None:
            new_note["archived"] = args.archived
        notes[:] = [n for n in notes if str(n.get("id")) != note_id]
        notes.append(new_note)
        notes.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(notes)
        notes[:] = [n for n in notes if str(n.get("id")) != args.id]
        if len(notes) == before:
            die(f"note '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_note_source(source)
        if not imported:
            die(f"no notes found in {source}")
        existing = {str(n.get("id")): n for n in notes if isinstance(n, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("title") or "note"))
            if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                item["title"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        notes[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"notes": notes}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported notes: {output}")
        return 0
    elif args.action == "share":
        note = next((n for n in notes if str(n.get("id")) == args.id), None)
        if note is None:
            die(f"note '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "html":
            rendered = render_note_html(note)
        else:
            rendered = render_note_md(note)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared note: {output}")
        return 0
    elif args.action == "clone":
        clone = _clone_registry_item(
            notes,
            args.id,
            new_id=args.new_id,
            new_title=args.title,
        )
        if args.file is not None:
            clone["files"] = [item for item in args.file if item]
        if args.image is not None:
            clone["images"] = [item for item in args.image if item]
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.pinned is not None:
            clone["pinned"] = args.pinned
        if args.archived is not None:
            clone["archived"] = args.archived
        notes.append(clone)
        notes.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"note": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned note: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported notes action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Notes: {len(notes)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _load_memory_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        memories: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
                text = path.read_text(encoding="utf-8").strip()
                if not text:
                    continue
                title = path.stem
                lines = text.splitlines()
                if lines and lines[0].lstrip().startswith("#"):
                    heading = lines[0].lstrip("#").strip()
                    if heading:
                        title = heading
                        text = "\n".join(lines[1:]).strip() or text
                memories.append(
                    {
                        "id": slugify(path.stem),
                        "title": title,
                        "content": text,
                        "scope": "user",
                    }
                )
        return memories
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("memories", payload.get("items", []))
        if not isinstance(payload, list):
            die("memory JSON must be an array or an object with memories")
        memories = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            memory_id = str(item.get("id", "")).strip()
            content = str(item.get("content", item.get("body", ""))).strip()
            if not memory_id or not content:
                continue
            memory: dict[str, Any] = {
                "id": memory_id,
                "title": str(item.get("title") or item.get("name") or memory_id).strip(),
                "content": content,
            }
            if isinstance(item.get("scope"), str) and str(item.get("scope")).strip():
                memory["scope"] = str(item["scope"]).strip()
            if isinstance(item.get("source"), str) and str(item.get("source")).strip():
                memory["source"] = str(item["source"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    memory["tags"] = tags
            memories.append(memory)
        return memories
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    title = source.stem
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        heading = lines[0].lstrip("#").strip()
        if heading:
            title = heading
            text = "\n".join(lines[1:]).strip() or text
    return [{"id": slugify(source.stem), "title": title, "content": text, "scope": "user"}]


def _find_memory(memories: list[dict[str, Any]], memory_id: str) -> dict[str, Any] | None:
    for memory in memories:
        if str(memory.get("id")) == memory_id:
            return memory
    return None


def render_memory_md(memory: dict[str, Any]) -> str:
    title = str(memory.get("title") or memory.get("id") or "Memory").strip()
    lines = [f"# {title}", ""]
    for key, label in (("id", "ID"), ("scope", "Scope"), ("source", "Source")):
        value = memory.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"- {label}: {value.strip()}")
    tags = memory.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            lines.append(f"- Tags: {tag_line}")
    content = str(memory.get("content") or "").strip()
    if content:
        lines.extend(["", "## Content", content])
    return "\n".join(lines).strip() + "\n"


def render_memory_html(memory: dict[str, Any]) -> str:
    title = html_escape(str(memory.get("title") or memory.get("id") or "Memory"))
    memory_id = html_escape(str(memory.get("id") or "memory"))
    content = html_escape(str(memory.get("content") or ""))
    meta_parts: list[str] = []
    for key, label in (("scope", "Scope"), ("source", "Source")):
        value = memory.get(key)
        if isinstance(value, str) and value.strip():
            meta_parts.append(f"<p class=\"meta\">{label}: {html_escape(value.strip())}</p>")
    tags = memory.get("tags")
    tag_html = ""
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            tag_html = "<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>"
    body_html = f"<pre class=\"memory-body\">{content}</pre>" if content else "<pre class=\"memory-body\"></pre>"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-memory-id=\"{memory_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Memory ID: {memory_id}</p>
    {''.join(meta_parts)}
    {tag_html}
    {body_html}
  </article>
</body>
</html>
"""


def normalize_memories(settings: dict[str, Any]) -> list[dict[str, Any]]:
    memories = settings.get("memories")
    if memories is None:
        settings["memories"] = []
        return []
    if isinstance(memories, list):
        normalized: list[dict[str, Any]] = []
        for item in memories:
            if not isinstance(item, dict):
                continue
            memory_id = item.get("id")
            title = item.get("title", item.get("name"))
            content = item.get("content", item.get("body"))
            if not isinstance(memory_id, str) or not memory_id.strip():
                continue
            if not isinstance(title, str) or not title.strip():
                title = memory_id.strip()
            if not isinstance(content, str) or not content.strip():
                continue
            normalized_item: dict[str, Any] = {
                "id": memory_id.strip(),
                "title": str(title).strip(),
                "content": content,
            }
            if isinstance(item.get("scope"), str) and str(item.get("scope")).strip():
                normalized_item["scope"] = str(item["scope"]).strip()
            if isinstance(item.get("source"), str) and str(item.get("source")).strip():
                normalized_item["source"] = str(item["source"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized_item["tags"] = tags
            if item.get("pinned") is not None:
                normalized_item["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized_item["archived"] = bool(item["archived"])
            normalized.append(normalized_item)
        settings["memories"] = normalized
        return normalized
    if isinstance(memories, dict):
        normalized = []
        for key, value in memories.items():
            if isinstance(value, str):
                normalized.append(
                    {"id": str(key).strip(), "title": str(key).strip(), "content": value}
                )
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("title", str(key).strip())
                if isinstance(item.get("content"), str) and item["content"].strip():
                    normalized.append(item)
                elif isinstance(item.get("body"), str) and item["body"].strip():
                    item["content"] = item.pop("body")
                    normalized.append(item)
        settings["memories"] = normalized
        return normalized
    settings["memories"] = []
    return []


def command_memories(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_memories(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("files", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    memories = settings.setdefault("memories", [])
    if not isinstance(memories, list):
        die("memories must be an array")

    if args.action in (None, "list"):
        print("Memories:")
        print("-" * 80)
        if not memories:
            print("(none)")
            return 0
        fmt = "{:<18} {:<24} {:<12}"
        print(fmt.format("ID", "TITLE", "SCOPE"))
        print("-" * 80)
        for item in memories:
            print(fmt.format(str(item.get("id", "")), str(item.get("title", ""))[:24], str(item.get("scope", "user"))[:12]))
        return 0

    if args.action == "add":
        memory_id = args.id or slugify(args.title)
        new_memory: dict[str, Any] = {
            "id": memory_id,
            "title": args.title,
            "content": args.content,
            "scope": args.scope,
        }
        if args.source:
            new_memory["source"] = args.source
        if args.tag:
            new_memory["tags"] = [tag for tag in args.tag if tag]
        if args.pinned is not None:
            new_memory["pinned"] = args.pinned
        if args.archived is not None:
            new_memory["archived"] = args.archived
        memories[:] = [m for m in memories if str(m.get("id")) != memory_id]
        memories.append(new_memory)
        memories.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(memories)
        memories[:] = [m for m in memories if str(m.get("id")) != args.id]
        if len(memories) == before:
            die(f"memory '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_memory_source(source)
        if not imported:
            die(f"no memories found in {source}")
        existing = {str(m.get("id")): m for m in memories if isinstance(m, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("title") or "memory"))
            if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                item["title"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        memories[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"memories": memories}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported memories: {output}")
        return 0
    elif args.action == "share":
        memory = _find_memory(memories, args.id)
        if memory is None:
            die(f"memory '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(memory, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_memory_html(memory)
        else:
            rendered = render_memory_md(memory)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared memory: {output}")
        return 0
    elif args.action == "clone":
        memory = _find_memory(memories, args.id)
        if memory is None:
            die(f"memory '{args.id}' not found")
        clone = dict(memory)
        clone_id = args.new_id or slugify(f"{str(memory.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in memories):
            die(f"memory '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["title"] = args.title or clone.get("title", clone_id)
        if args.content is not None:
            clone["content"] = args.content
        if args.scope is not None:
            clone["scope"] = args.scope
        if args.source is not None:
            clone["source"] = args.source
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.pinned is not None:
            clone["pinned"] = args.pinned
        if args.archived is not None:
            clone["archived"] = args.archived
        memories.append(clone)
        memories.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"memory": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned memory: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported memories action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Memories: {len(memories)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def command_artifacts(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_artifacts(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("notes", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    artifacts = settings.setdefault("artifacts", [])
    if not isinstance(artifacts, list):
        die("artifacts must be an array")

    if args.action in (None, "list"):
        print("Artifacts:")
        print("-" * 80)
        if not artifacts:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<12}"
        print(fmt.format("ID", "TITLE", "KIND"))
        print("-" * 80)
        for item in artifacts:
            print(fmt.format(str(item.get("id", "")), str(item.get("title", ""))[:28], str(item.get("kind", ""))[:12]))
        return 0

    if args.action == "add":
        artifact_id = args.id or slugify(args.title)
        new_artifact: dict[str, Any] = {
            "id": artifact_id,
            "title": args.title,
            "content": args.content,
        }
        if args.kind:
            new_artifact["kind"] = args.kind
        if args.tag:
            new_artifact["tags"] = [tag for tag in args.tag if tag]
        artifacts[:] = [a for a in artifacts if str(a.get("id")) != artifact_id]
        artifacts.append(new_artifact)
        artifacts.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(artifacts)
        artifacts[:] = [a for a in artifacts if str(a.get("id")) != args.id]
        if len(artifacts) == before:
            die(f"artifact '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_artifact_source(source)
        if not imported:
            die(f"no artifacts found in {source}")
        existing = {str(a.get("id")): a for a in artifacts if isinstance(a, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("title") or "artifact"))
            if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                item["title"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        artifacts[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"artifacts": artifacts}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported artifacts: {output}")
        return 0
    elif args.action == "share":
        artifact = _find_artifact(artifacts, args.id)
        if artifact is None:
            die(f"artifact '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(artifact, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = _render_artifact_html(artifact)
        else:
            rendered = _render_artifact_md(artifact)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared artifact: {output}")
        return 0
    elif args.action == "clone":
        clone = _clone_registry_item(
            artifacts,
            args.id,
            new_id=args.new_id,
            new_title=args.title,
        )
        if args.kind is not None:
            clone["kind"] = args.kind
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        artifacts.append(clone)
        artifacts.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"artifact": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned artifact: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported artifacts action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Artifacts: {len(artifacts)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _load_conversation_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        conversations: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt", ".json"}:
                if path.suffix.lower() == ".json":
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(payload, dict):
                        payload = payload.get("conversations", payload.get("items", []))
                    if isinstance(payload, list):
                        for item in payload:
                            if isinstance(item, dict):
                                conversations.append(item)
                        continue
                text = path.read_text(encoding="utf-8").strip()
                if not text:
                    continue
                title = path.stem
                lines = text.splitlines()
                if lines and lines[0].lstrip().startswith("#"):
                    heading = lines[0].lstrip("#").strip()
                    if heading:
                        title = heading
                        text = "\n".join(lines[1:]).strip() or text
                conversations.append(
                    {
                        "id": slugify(path.stem),
                        "title": title,
                        "transcript": text,
                    }
                )
        return conversations
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("conversations", payload.get("items", []))
        if not isinstance(payload, list):
            die("conversation JSON must be an array or an object with conversations")
        return [item for item in payload if isinstance(item, dict)]
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    title = source.stem
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        heading = lines[0].lstrip("#").strip()
        if heading:
            title = heading
            text = "\n".join(lines[1:]).strip() or text
    return [{"id": slugify(source.stem), "title": title, "transcript": text}]


def _normalize_conversation_source_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("conversations", payload.get("items", []))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _conversation_text(conversation: dict[str, Any]) -> str:
    messages = conversation.get("messages")
    if isinstance(messages, list) and messages:
        lines: list[str] = []
        for msg in messages:
            if isinstance(msg, dict):
                role = str(msg.get("role", "")).strip()
                content = str(msg.get("content", "")).strip()
                if role and content:
                    lines.append(f"{role}: {content}")
        if lines:
            return "\n".join(lines)
    transcript = conversation.get("transcript")
    if isinstance(transcript, str) and transcript.strip():
        return transcript.strip()
    body = conversation.get("content")
    if isinstance(body, str) and body.strip():
        return body.strip()
    return ""


def _find_conversation(conversations: list[dict[str, Any]], convo_id: str) -> dict[str, Any] | None:
    for conversation in conversations:
        if str(conversation.get("id")) == convo_id:
            return conversation
    return None


def _clone_registry_item(
    items: list[dict[str, Any]],
    item_id: str,
    *,
    new_id: str | None = None,
    new_title: str | None = None,
) -> dict[str, Any]:
    item = next((entry for entry in items if isinstance(entry, dict) and str(entry.get("id")) == item_id), None)
    if item is None:
        die(f"item '{item_id}' not found")
    clone = dict(item)
    clone_id = new_id or slugify(f"{str(item.get('id') or item_id)}-copy")
    if any(str(entry.get("id")) == clone_id for entry in items):
        die(f"item '{clone_id}' already exists")
    clone["id"] = clone_id
    if new_title is not None:
        clone["title"] = new_title
    elif isinstance(item.get("title"), str) and item["title"].strip():
        clone["title"] = item["title"]
    return clone


def _load_folder_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        folders: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() == ".json":
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    payload = payload.get("folders", payload.get("items", []))
                if isinstance(payload, list):
                    folders.extend(item for item in payload if isinstance(item, dict))
        return folders
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("folders", payload.get("items", []))
        if not isinstance(payload, list):
            die("folder JSON must be an array or an object with folders")
        return [item for item in payload if isinstance(item, dict)]
    die("folder import expects a JSON file or directory")


def _find_folder(folders: list[dict[str, Any]], folder_id: str) -> dict[str, Any] | None:
    for folder in folders:
        if str(folder.get("id")) == folder_id:
            return folder
    return None


def _apply_folder_defaults(conversation: dict[str, Any], folder: dict[str, Any] | None) -> None:
    if folder is None:
        return
    system_prompt = folder.get("systemPrompt")
    if isinstance(system_prompt, str) and system_prompt.strip() and not str(conversation.get("systemPrompt", "")).strip():
        conversation["systemPrompt"] = system_prompt.strip()
    knowledge = folder.get("knowledge")
    if isinstance(knowledge, list):
        inherited = [str(entry).strip() for entry in knowledge if str(entry).strip()]
        if inherited and not conversation.get("knowledge"):
            conversation["knowledge"] = inherited


def _conversation_attachments(conversation: dict[str, Any]) -> list[str]:
    attachments = conversation.get("files", conversation.get("attachments", []))
    if not isinstance(attachments, list):
        return []
    return [str(item).strip() for item in attachments if str(item).strip()]


def _conversation_images(conversation: dict[str, Any]) -> list[str]:
    images = conversation.get("images", [])
    if not isinstance(images, list):
        return []
    return [str(item).strip() for item in images if str(item).strip()]


def render_folder_md(folder: dict[str, Any]) -> str:
    title = str(folder.get("name") or folder.get("id") or "Folder").strip()
    lines = [f"# {title}", ""]
    for key, label in (("id", "ID"), ("parentId", "Parent"), ("systemPrompt", "System Prompt"), ("sourceDir", "Source Dir"), ("description", "Description")):
        value = folder.get(key)
        if isinstance(value, str) and value.strip():
            lines.extend([f"- {label}: {value.strip()}"])
    for key, label in (("knowledge", "Knowledge"), ("tags", "Tags")):
        value = folder.get(key)
        if isinstance(value, list) and value:
            line = ", ".join(str(item) for item in value if str(item).strip())
            if line:
                lines.append(f"- {label}: {line}")
    if folder.get("unreadCount") is not None:
        lines.append(f"- Unread Count: {folder['unreadCount']}")
    if folder.get("pinned") is not None:
        lines.append(f"- Pinned: {bool(folder['pinned'])}")
    if folder.get("archived") is not None:
        lines.append(f"- Archived: {bool(folder['archived'])}")
    return "\n".join(lines).strip() + "\n"


def render_folder_html(folder: dict[str, Any]) -> str:
    title = html_escape(str(folder.get("name") or folder.get("id") or "Folder"))
    folder_id = html_escape(str(folder.get("id") or "folder"))
    meta_parts: list[str] = []
    for key, label in (("parentId", "Parent"), ("sourceDir", "Source Dir"), ("description", "Description")):
        value = folder.get(key)
        if isinstance(value, str) and value.strip():
            meta_parts.append(f"<p class=\"meta\">{label}: {html_escape(value.strip())}</p>")
    if folder.get("unreadCount") is not None:
        meta_parts.append(f"<p class=\"meta\">Unread Count: {html_escape(str(folder['unreadCount']))}</p>")
    if folder.get("pinned") is not None:
        meta_parts.append(f"<p class=\"meta\">Pinned: {html_escape(str(bool(folder['pinned'])))}</p>")
    if folder.get("archived") is not None:
        meta_parts.append(f"<p class=\"meta\">Archived: {html_escape(str(bool(folder['archived'])))}</p>")
    for key, label in (("systemPrompt", "System Prompt"),):
        value = folder.get(key)
        if isinstance(value, str) and value.strip():
            meta_parts.append(f"<pre class=\"system-prompt\">{html_escape(value.strip())}</pre>")
    for key, label in (("knowledge", "Knowledge"), ("tags", "Tags")):
        value = folder.get(key)
        if isinstance(value, list) and value:
            line = ", ".join(html_escape(str(item)) for item in value if str(item).strip())
            if line:
                meta_parts.append(f"<p class=\"tags\">{label}: {line}</p>")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
    .system-prompt {{ white-space: pre-wrap; word-wrap: break-word; background: #111827; padding: 1rem; border-radius: 12px; border: 1px solid #374151; }}
  </style>
</head>
<body>
  <article class=\"card\" data-folder-id=\"{folder_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Folder ID: {folder_id}</p>
    {''.join(meta_parts)}
  </article>
</body>
</html>
"""


def render_conversation_md(conversation: dict[str, Any]) -> str:
    title = str(conversation.get("title") or conversation.get("id") or "Conversation").strip()
    text = _conversation_text(conversation)
    parts = [f"# {title}"]
    folder_id = conversation.get("folderId")
    if isinstance(folder_id, str) and folder_id.strip():
        parts.extend(["", f"- Folder: {folder_id.strip()}"])
    system_prompt = conversation.get("systemPrompt")
    if isinstance(system_prompt, str) and system_prompt.strip():
        parts.extend(["", "## System Prompt", system_prompt.strip()])
    if text:
        parts.append("")
        parts.append(text)
    tags = conversation.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            parts.extend(["", f"Tags: {tag_line}"])
    knowledge = conversation.get("knowledge")
    if isinstance(knowledge, list) and knowledge:
        knowledge_line = ", ".join(str(item) for item in knowledge if str(item).strip())
        if knowledge_line:
            parts.extend(["", f"Knowledge: {knowledge_line}"])
    attachments = _conversation_attachments(conversation)
    if attachments:
        parts.extend(["", f"Attachments: {', '.join(attachments)}"])
    images = _conversation_images(conversation)
    if images:
        parts.extend(["", f"Images: {', '.join(images)}"])
    return "\n".join(parts).strip() + "\n"


def render_conversation_html(conversation: dict[str, Any]) -> str:
    title = html_escape(str(conversation.get("title") or conversation.get("id") or "Conversation"))
    convo_id = html_escape(str(conversation.get("id") or "conversation"))
    text = html_escape(_conversation_text(conversation))
    tags = conversation.get("tags")
    folder_id = html_escape(str(conversation.get("folderId") or "")) if conversation.get("folderId") else ""
    system_prompt = html_escape(str(conversation.get("systemPrompt") or "")) if conversation.get("systemPrompt") else ""
    knowledge = conversation.get("knowledge")
    tag_html = ""
    if isinstance(tags, list):
        tags = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tags:
            tag_html = "<p class=\"tags\">Tags: " + ", ".join(tags) + "</p>"
    folder_html = f"<p class=\"meta\">Folder: {folder_id}</p>" if folder_id else ""
    system_html = f"<pre class=\"system-prompt\">{system_prompt}</pre>" if system_prompt else ""
    knowledge_html = ""
    if isinstance(knowledge, list):
        items = [html_escape(str(item)) for item in knowledge if str(item).strip()]
        if items:
            knowledge_html = "<p class=\"tags\">Knowledge: " + ", ".join(items) + "</p>"
    attachment_html = ""
    attachments = _conversation_attachments(conversation)
    if attachments:
        attachment_html = "<p class=\"tags\">Attachments: " + ", ".join(html_escape(item) for item in attachments) + "</p>"
    image_html = ""
    images = _conversation_images(conversation)
    if images:
        image_html = "<p class=\"tags\">Images: " + ", ".join(html_escape(item) for item in images) + "</p>"
    body_html = ""
    messages = conversation.get("messages")
    if isinstance(messages, list) and messages:
        items = []
        for msg in messages:
            if isinstance(msg, dict):
                role = html_escape(str(msg.get("role", "")))
                content = html_escape(str(msg.get("content", "")))
                if role and content:
                    items.append(f"<div class=\"message\"><strong>{role}</strong><pre>{content}</pre></div>")
        if items:
            body_html = "\n".join(items)
    if not body_html and text:
        body_html = f"<pre class=\"transcript\">{text}</pre>"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .message {{ margin-bottom: 1rem; }}
    .message strong {{ display: block; margin-bottom: 0.35rem; }}
    .tags {{ color: #c7d2fe; }}
    .system-prompt {{ white-space: pre-wrap; word-wrap: break-word; background: #111827; padding: 1rem; border-radius: 12px; border: 1px solid #374151; }}
  </style>
</head>
<body>
  <article class=\"card\" data-conversation-id=\"{convo_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Conversation ID: {convo_id}</p>
    {tag_html}
    {folder_html}
    {system_html}
    {knowledge_html}
    {attachment_html}
    {image_html}
    {body_html or '<pre class=\"transcript\"></pre>'}
  </article>
</body>
</html>
"""


def _json_script_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _chat_model_label(model_id: str) -> str:
    return display_name(model_id)


def _chat_model_candidates(settings: dict[str, Any], model_id: str) -> list[str]:
    model_id = model_id.strip()
    if not model_id:
        return []
    entries = _iter_model_entries(settings)
    requested_entry = next((entry for entry in entries if str(entry.get("id")) == model_id), None)
    ordered: list[str] = []
    if isinstance(requested_entry, dict):
        requested_base = str(requested_entry.get("baseUrl") or "").strip()
        if requested_base:
            ordered.extend(
                str(entry.get("id"))
                for entry in entries
                if str(entry.get("id")) != model_id and str(entry.get("baseUrl") or "").strip() == requested_base
            )
    ordered.extend(str(entry.get("id")) for entry in entries if str(entry.get("id")) != model_id)
    candidates: list[str] = []
    seen: set[str] = set()
    for candidate in [model_id, *ordered]:
        candidate = candidate.strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def _request_error_is_missing_model(error: RequestError) -> bool:
    message = str(error).lower()
    return "not_found_error" in message or ("model" in message and "not found" in message)


def _settings_model_provider_key(settings: dict[str, Any]) -> str:
    auth = settings.get("security", {})
    if isinstance(auth, dict):
        auth = auth.get("auth", auth)
        if isinstance(auth, dict):
            selected = auth.get("selectedType")
            if isinstance(selected, str) and selected.strip():
                return selected.strip()
    return ""


def _settings_default_model(settings: dict[str, Any]) -> str:
    model = settings.get("model", {})
    if isinstance(model, dict):
        value = model.get("name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _provider_display_name(provider_key: str) -> str:
    preset = PRESETS.get(provider_key)
    if preset is not None:
        return preset.name
    return provider_key.replace("_", " ").replace("-", " ").title()


def _provider_env_key(provider_key: str, entry: dict[str, Any]) -> str:
    env_key = entry.get("envKey")
    if isinstance(env_key, str) and env_key.strip():
        return env_key.strip()
    preset = PRESETS.get(provider_key)
    if preset is not None:
        return preset.env_key
    return ""


def _provider_base_url(provider_key: str, entry: dict[str, Any]) -> str:
    base_url = entry.get("baseUrl")
    if isinstance(base_url, str) and base_url.strip():
        return normalize_url(base_url)
    preset = PRESETS.get(provider_key)
    if preset is not None:
        return normalize_url(os.environ.get(BASE_URL_HINT_ENV.get(provider_key, ""), preset.base_url))
    return ""


def _iter_model_entries(settings: dict[str, Any]) -> list[dict[str, Any]]:
    providers = settings.get("modelProviders", {})
    if not isinstance(providers, dict):
        return []
    selected_provider = _settings_model_provider_key(settings)
    selected_model = _settings_default_model(settings)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for provider_key, models in providers.items():
        if not isinstance(models, list):
            continue
        for item in models:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            model_id = model_id.strip()
            if model_id in seen:
                continue
            seen.add(model_id)
            entry = dict(item)
            entry["id"] = model_id
            entry["provider"] = provider_key
            entry["providerName"] = _provider_display_name(provider_key)
            entry["baseUrl"] = _provider_base_url(provider_key, entry)
            env_key = _provider_env_key(provider_key, entry)
            if env_key:
                entry["envKey"] = env_key
            if selected_model and selected_model == model_id:
                entry["selected"] = True
            elif not selected_model and provider_key == selected_provider:
                entry["selected"] = True
            entries.append(entry)
    entries.sort(
        key=lambda item: (
            0 if item.get("selected") else 1,
            str(item.get("provider", "")).lower(),
            str(item.get("id", "")).lower(),
        )
    )
    return entries


def _find_model_entry(settings: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    model_id = model_id.strip()
    if not model_id:
        return None
    for entry in _iter_model_entries(settings):
        if str(entry.get("id")) == model_id:
            return entry
    return None


def _model_timeout_seconds(entry: dict[str, Any] | None) -> int:
    if not isinstance(entry, dict):
        return 120
    generation = entry.get("generationConfig")
    if isinstance(generation, dict):
        timeout = generation.get("timeout")
        if isinstance(timeout, int) and timeout > 0:
            return max(5, min(300, timeout // 1000 if timeout >= 1000 else timeout))
    return 120


def _settings_prompt_templates(settings: dict[str, Any]) -> list[dict[str, Any]]:
    templates = normalize_prompt_templates(settings)
    templates.sort(key=lambda item: str(item.get("id", "")).lower())
    return templates


def _settings_conversations(settings: dict[str, Any]) -> list[dict[str, Any]]:
    conversations = normalize_conversations(settings)
    conversations.sort(key=lambda item: str(item.get("id", "")).lower())
    return conversations


def _settings_files(settings: dict[str, Any]) -> list[dict[str, Any]]:
    files = normalize_files(settings)
    files.sort(key=lambda item: str(item.get("id", "")).lower())
    return files


def _settings_knowledge_bases(settings: dict[str, Any]) -> list[dict[str, Any]]:
    bases = normalize_knowledge_bases(settings)
    bases.sort(key=lambda item: str(item.get("id", "")).lower())
    return bases


def _settings_knowledge_indexes(settings: dict[str, Any]) -> list[dict[str, Any]]:
    indexes = normalize_knowledge_indexes(settings)
    indexes.sort(key=lambda item: str(item.get("id", "")).lower())
    return indexes


def _settings_agents(settings: dict[str, Any]) -> list[dict[str, Any]]:
    agents = normalize_agents(settings)
    agents.sort(key=lambda item: str(item.get("id", "")).lower())
    return agents


def _settings_skills(settings: dict[str, Any]) -> list[dict[str, Any]]:
    skills = normalize_skills(settings)
    skills.sort(key=lambda item: str(item.get("id", "")).lower())
    return skills


def _settings_memories(settings: dict[str, Any]) -> list[dict[str, Any]]:
    memories = normalize_memories(settings)
    memories.sort(key=lambda item: str(item.get("id", "")).lower())
    return memories


def _settings_notes(settings: dict[str, Any]) -> list[dict[str, Any]]:
    notes = normalize_notes(settings)
    notes.sort(key=lambda item: str(item.get("id", "")).lower())
    return notes


def _settings_artifacts(settings: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = normalize_artifacts(settings)
    artifacts.sort(key=lambda item: str(item.get("id", "")).lower())
    return artifacts


def _settings_tool_servers(settings: dict[str, Any]) -> list[dict[str, Any]]:
    servers = normalize_tool_servers(settings)
    servers.sort(key=lambda item: str(item.get("id", "")).lower())
    return servers


def _settings_webhooks(settings: dict[str, Any]) -> list[dict[str, Any]]:
    webhooks = normalize_webhooks(settings)
    webhooks.sort(key=lambda item: str(item.get("id", "")).lower())
    return webhooks


def _settings_bootstrap(settings: dict[str, Any]) -> dict[str, Any]:
    models = _iter_model_entries(settings)
    templates = _settings_prompt_templates(settings)
    folders = _settings_folders(settings)
    conversations = _settings_conversations(settings)
    files = _settings_files(settings)
    knowledge_bases = normalize_knowledge_bases(settings)
    knowledge_indexes = normalize_knowledge_indexes(settings)
    agents = _settings_agents(settings)
    skills = _settings_skills(settings)
    memories = _settings_memories(settings)
    notes = _settings_notes(settings)
    artifacts = _settings_artifacts(settings)
    tool_servers = _settings_tool_servers(settings)
    webhooks = _settings_webhooks(settings)
    return {
        "version": VERSION,
        "selectedModel": _settings_default_model(settings),
        "selectedProvider": _settings_model_provider_key(settings),
        "models": models,
        "promptTemplates": templates,
        "folders": [
            {
                "id": folder.get("id"),
                "name": folder.get("name"),
                "parentId": folder.get("parentId", ""),
                "systemPrompt": folder.get("systemPrompt", ""),
                "description": folder.get("description", ""),
                "sourceDir": folder.get("sourceDir", ""),
            }
            for folder in folders
        ],
        "files": [
            {
                "id": file_item.get("id"),
                "name": file_item.get("name"),
                "kind": file_item.get("kind", ""),
                "size": file_item.get("size"),
                "description": file_item.get("description", ""),
            }
            for file_item in files
        ],
        "conversations": [
            {
                "id": convo.get("id"),
                "title": convo.get("title"),
                "folderId": convo.get("folderId"),
                "pinned": convo.get("pinned", False),
                "archived": convo.get("archived", False),
                "systemPrompt": convo.get("systemPrompt", ""),
            }
            for convo in conversations
        ],
        "knowledgeBases": [
            {
                "id": base.get("id"),
                "name": base.get("name"),
                "sourceDir": base.get("sourceDir", ""),
                "description": base.get("description", ""),
                "enabled": base.get("enabled", True),
            }
            for base in knowledge_bases
        ],
        "knowledgeIndexes": [
            {
                "id": index.get("id"),
                "baseId": index.get("baseId"),
                "path": index.get("path", ""),
                "sourceDir": index.get("sourceDir", ""),
                "documentCount": index.get("documentCount", 0),
                "chunkCount": index.get("chunkCount", 0),
            }
            for index in knowledge_indexes
        ],
        "agents": [
            {
                "id": agent.get("id"),
                "name": agent.get("name"),
                "baseModel": agent.get("baseModel", agent.get("model", "")),
                "systemPrompt": agent.get("systemPrompt", agent.get("instructions", agent.get("prompt", ""))),
                "description": agent.get("description", ""),
                "tools": agent.get("tools", []),
                "knowledge": agent.get("knowledge", []),
                "skills": agent.get("skills", []),
                "avatar": agent.get("avatar", ""),
                "voice": agent.get("voice", ""),
                "visibility": agent.get("visibility", ""),
            }
            for agent in agents
        ],
        "skills": [
            {
                "id": skill.get("id"),
                "name": skill.get("name"),
                "content": skill.get("content", ""),
                "description": skill.get("description", ""),
                "tags": skill.get("tags", []),
                "pinned": skill.get("pinned", False),
                "archived": skill.get("archived", False),
            }
            for skill in skills
        ],
        "memories": [
            {
                "id": memory.get("id"),
                "title": memory.get("title"),
                "content": memory.get("content", ""),
                "scope": memory.get("scope", "user"),
                "source": memory.get("source", ""),
                "tags": memory.get("tags", []),
                "pinned": memory.get("pinned", False),
                "archived": memory.get("archived", False),
            }
            for memory in memories
        ],
        "notes": [
            {
                "id": note.get("id"),
                "title": note.get("title"),
                "body": note.get("body", ""),
                "files": note.get("files", []),
                "images": note.get("images", []),
                "tags": note.get("tags", []),
                "pinned": note.get("pinned", False),
                "archived": note.get("archived", False),
            }
            for note in notes
        ],
        "artifacts": [
            {
                "id": artifact.get("id"),
                "title": artifact.get("title"),
                "content": artifact.get("content", ""),
                "kind": artifact.get("kind", ""),
                "tags": artifact.get("tags", []),
                "pinned": artifact.get("pinned", False),
                "archived": artifact.get("archived", False),
            }
            for artifact in artifacts
        ],
        "toolServers": [
            {
                "id": server.get("id"),
                "name": server.get("name"),
                "type": server.get("type", ""),
                "endpoint": server.get("endpoint", ""),
                "description": server.get("description", ""),
                "auth": server.get("auth"),
                "tags": server.get("tags", []),
                "enabled": server.get("enabled", True),
            }
            for server in tool_servers
        ],
        "webhooks": [
            {
                "id": hook.get("id"),
                "name": hook.get("name"),
                "url": hook.get("url", ""),
                "events": hook.get("events", []),
                "description": hook.get("description", ""),
                "secret": hook.get("secret", ""),
                "tags": hook.get("tags", []),
                "enabled": hook.get("enabled", True),
            }
            for hook in webhooks
        ],
    }


def request_json_post(
    url: str,
    api_key: str,
    payload: Any,
    timeout: int,
    insecure: bool = False,
) -> Any:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": f"qwen-omega/{VERSION}",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    context = (
        ssl._create_unverified_context() if insecure else ssl.create_default_context()
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:1000]
        die(f"HTTP {exc.code} from {url}: {body}")
    except urllib.error.URLError as exc:
        die(f"Cannot reach {url}: {exc.reason}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        die(f"Endpoint returned non-JSON data: {url}")


def request_stream_post(
    url: str,
    api_key: str,
    payload: Any,
    timeout: int,
    insecure: bool = False,
):
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": f"qwen-omega/{VERSION}",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    context = (
        ssl._create_unverified_context() if insecure else ssl.create_default_context()
    )
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=context)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:1000]
        raise RequestError(f"HTTP {exc.code} from {url}: {body}")
    except urllib.error.URLError as exc:
        raise RequestError(f"Cannot reach {url}: {exc.reason}")


def _chat_completion_url(base_url: str) -> str:
    return f"{normalize_url(base_url)}/chat/completions"


def _chat_messages(messages: Any) -> list[dict[str, str]]:
    if not isinstance(messages, list):
        die("messages must be an array")
    normalized: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if not isinstance(role, str) or not role.strip():
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        normalized.append({"role": role.strip(), "content": content})
    if not normalized:
        die("messages must contain at least one valid message")
    return normalized


def _suggest_chat_title(messages: list[dict[str, str]], fallback: str = "New chat") -> str:
    if not isinstance(messages, list):
        return fallback
    source = ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if role == "user" and content:
            source = content
            break
        if not source and content:
            source = content
    if not source:
        return fallback
    clean = re.sub(r"\s+", " ", source).strip(" -_,.:;")
    if not clean:
        return fallback
    words = clean.split()
    title = " ".join(words[:8]).strip()
    if len(title) > 48:
        title = title[:48].rstrip(" -_,.:;")
    if not title:
        return fallback
    return title[:1].upper() + title[1:]


def _chat_response_text(payload: Any, model_id: str) -> str:
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
                text = first.get("text")
                if isinstance(text, str):
                    return text
        content = payload.get("content")
        if isinstance(content, str):
            return content
        message = payload.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                die(message.strip())
        if isinstance(error, str) and error.strip():
            die(error.strip())
    die(f"no assistant content returned for model '{model_id}'")


def _chat_completion_request(
    settings: dict[str, Any],
    model_id: str,
    messages: list[dict[str, str]],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str, int, str, str, dict[str, Any]]:
    entry = _find_model_entry(settings, model_id)
    if entry is None:
        die(f"unknown model '{model_id}'")
    base_url = str(entry.get("baseUrl") or "").strip()
    if not base_url:
        die(f"model '{model_id}' does not define a baseUrl")
    env_key = str(entry.get("envKey") or "").strip()
    api_key = os.environ.get(env_key, "") if env_key else ""
    request_payload: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
    }
    attachment_context = _file_attachment_context(settings, payload.get("files"))
    if attachment_context:
        request_payload["messages"] = [
            {"role": "system", "content": attachment_context},
            *messages,
        ]
    for key in (
        "temperature",
        "top_p",
        "max_tokens",
        "presence_penalty",
        "frequency_penalty",
        "stop",
        "seed",
        "response_format",
        "tool_choice",
        "tools",
    ):
        if key in payload and payload[key] is not None:
            request_payload[key] = payload[key]
    timeout = _model_timeout_seconds(entry)
    return entry, base_url, timeout, api_key, _chat_completion_url(base_url), request_payload


def _chat_stream_event_text(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    choices = event.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            delta = first.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    return content
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
            text = first.get("text")
            if isinstance(text, str):
                return text
    content = event.get("content")
    if isinstance(content, str):
        return content
    return ""


def _iter_stream_data(response: Any):
    buffer = ""
    while True:
        chunk = response.read(4096)
        if not chunk:
            break
        buffer += chunk.decode("utf-8", "replace")
        buffer = buffer.replace("\r\n", "\n")
        while "\n\n" in buffer:
            event, buffer = buffer.split("\n\n", 1)
            if not event.strip():
                continue
            data_lines: list[str] = []
            for line in event.split("\n"):
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if data_lines:
                yield "\n".join(data_lines)
                continue
            yield event.strip()
    if buffer.strip():
        buffer = buffer.replace("\r\n", "\n")
        if buffer.startswith("data:"):
            yield buffer[5:].lstrip()
        else:
            yield buffer.strip()


def _stream_chat_completion(
    settings: dict[str, Any],
    model_id: str,
    messages: list[dict[str, str]],
    payload: dict[str, Any],
    insecure: bool = False,
    on_delta: Any | None = None,
):
    entry, base_url, timeout, api_key, url, request_payload = _chat_completion_request(
        settings, model_id, messages, payload
    )
    request_payload["stream"] = True
    content_parts: list[str] = []
    response_payload: dict[str, Any] | None = None
    with request_stream_post(url, api_key, request_payload, timeout, insecure=insecure) as response:
        content_type = ""
        if hasattr(response, "headers") and response.headers is not None:
            content_type = str(response.headers.get("Content-Type", ""))
        if "text/event-stream" not in content_type.lower():
            raw = response.read()
            try:
                response_payload = json.loads(raw)
            except json.JSONDecodeError:
                die(f"Endpoint returned non-JSON data: {url}")
            content = _chat_response_text(response_payload, model_id)
            if content:
                content_parts.append(content)
                if callable(on_delta):
                    on_delta(content)
            return response_payload, "".join(content_parts)
        for event_text in _iter_stream_data(response):
            if event_text.strip() == "[DONE]":
                break
            try:
                event = json.loads(event_text)
            except json.JSONDecodeError:
                continue
            if response_payload is None and isinstance(event, dict):
                response_payload = event
            delta = _chat_stream_event_text(event)
            if delta:
                content_parts.append(delta)
                if callable(on_delta):
                    on_delta(delta)
    content = "".join(content_parts)
    if response_payload is None:
        response_payload = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model_id,
        }
    response_payload = dict(response_payload)
    response_payload.setdefault("id", f"chatcmpl-{int(time.time())}")
    response_payload.setdefault("object", "chat.completion")
    response_payload.setdefault("created", int(time.time()))
    response_payload.setdefault("model", model_id)
    if "choices" not in response_payload:
        response_payload["choices"] = [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ]
    return response_payload, content


def _chat_completion(
    settings: dict[str, Any],
    model_id: str,
    messages: list[dict[str, str]],
    payload: dict[str, Any],
    insecure: bool = False,
) -> dict[str, Any]:
    entry, _, timeout, api_key, url, request_payload = _chat_completion_request(
        settings, model_id, messages, payload
    )
    request_payload["stream"] = False
    response = request_json_post(url, api_key, request_payload, timeout, insecure=insecure)
    content = _chat_response_text(response, model_id)
    created = int(time.time())
    if isinstance(response, dict):
        maybe_created = response.get("created")
        if isinstance(maybe_created, int):
            created = maybe_created
    return {
        "id": str(response.get("id", f"chatcmpl-{created}")) if isinstance(response, dict) else f"chatcmpl-{created}",
        "object": "chat.completion",
        "created": created,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": response.get("usage") if isinstance(response, dict) else None,
        "provider": entry.get("provider"),
        "providerName": entry.get("providerName"),
    }


def _chat_requested_models(payload: dict[str, Any], default_model: str) -> list[str]:
    models = payload.get("models")
    requested: list[str] = []
    if isinstance(models, list):
        raw_models = models
    elif isinstance(models, str):
        raw_models = [part.strip() for part in models.split(",")]
    else:
        raw_models = []
    for item in raw_models:
        if not isinstance(item, str):
            continue
        model_id = item.strip()
        if model_id and model_id not in requested:
            requested.append(model_id)
    default_model = default_model.strip()
    if default_model:
        if default_model in requested:
            requested = [default_model, *[model_id for model_id in requested if model_id != default_model]]
        else:
            requested.insert(0, default_model)
    return requested


def _chat_model_result(
    settings: dict[str, Any],
    model_id: str,
    messages: list[dict[str, str]],
    payload: dict[str, Any],
    *,
    insecure: bool = False,
    stream: bool = False,
    on_delta: Any | None = None,
) -> tuple[dict[str, Any], str]:
    if stream:
        return _stream_chat_completion(
            settings,
            model_id,
            messages,
            payload,
            insecure=insecure,
            on_delta=on_delta,
        )
    response = _chat_completion(settings, model_id, messages, payload, insecure=insecure)
    return response, _chat_response_text(response, model_id)


def _chat_multi_completion(
    settings: dict[str, Any],
    model_ids: list[str],
    messages: list[dict[str, str]],
    payload: dict[str, Any],
    *,
    insecure: bool = False,
    stream: bool = False,
    on_delta: Any | None = None,
) -> tuple[dict[str, Any], str]:
    results: list[dict[str, Any]] = []
    combined_parts: list[str] = []
    for index, model_id in enumerate(model_ids):
        if index:
            separator = "\n\n---\n\n"
            combined_parts.append(separator)
            if callable(on_delta):
                on_delta(separator)
        heading = f"### {model_id}\n\n" if len(model_ids) > 1 else ""
        if heading:
            combined_parts.append(heading)
            if callable(on_delta):
                on_delta(heading)
        response, content = _chat_model_result(
            settings,
            model_id,
            messages,
            payload,
            insecure=insecure,
            stream=stream,
            on_delta=on_delta,
        )
        results.append(
            {
                "model": model_id,
                "content": content,
                "provider": response.get("provider") if isinstance(response, dict) else None,
                "providerName": response.get("providerName") if isinstance(response, dict) else None,
            }
        )
        combined_parts.append(content or "(empty response)")
    combined_content = "".join(combined_parts).strip()
    created = int(time.time())
    response_payload = {
        "id": f"chatcmpl-{created}",
        "object": "chat.completion",
        "created": created,
        "model": model_ids[0] if model_ids else "",
        "comparison": results,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": combined_content},
                "finish_reason": "stop",
            }
        ],
    }
    return response_payload, combined_content


_CHAT_COMPLETION_SINGLE = _chat_completion
_STREAM_CHAT_COMPLETION_SINGLE = _stream_chat_completion


def _chat_completion(
    settings: dict[str, Any],
    model_id: str,
    messages: list[dict[str, str]],
    payload: dict[str, Any],
    insecure: bool = False,
) -> dict[str, Any]:
    candidates = _chat_model_candidates(settings, model_id)
    last_error: RequestError | None = None
    for candidate in candidates:
        try:
            return _CHAT_COMPLETION_SINGLE(settings, candidate, messages, payload, insecure=insecure)
        except RequestError as exc:
            last_error = exc
            if candidate != candidates[-1] and _request_error_is_missing_model(exc):
                continue
            raise
    if last_error is not None:
        raise last_error
    die(f"no assistant content returned for model '{model_id}'")


def _stream_chat_completion(
    settings: dict[str, Any],
    model_id: str,
    messages: list[dict[str, str]],
    payload: dict[str, Any],
    insecure: bool = False,
    on_delta: Any | None = None,
):
    candidates = _chat_model_candidates(settings, model_id)
    last_error: RequestError | None = None
    for candidate in candidates:
        try:
            return _STREAM_CHAT_COMPLETION_SINGLE(
                settings,
                candidate,
                messages,
                payload,
                insecure=insecure,
                on_delta=on_delta,
            )
        except RequestError as exc:
            last_error = exc
            if candidate != candidates[-1] and _request_error_is_missing_model(exc):
                continue
            raise
    if last_error is not None:
        raise last_error
    die(f"no assistant content returned for model '{model_id}'")


def _file_attachment_context(settings: dict[str, Any], file_ids: Any) -> str:
    if not isinstance(file_ids, list):
        return ""
    files = normalize_files(settings)
    blocks: list[str] = []
    for raw_id in file_ids:
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        file_item = _find_file(files, raw_id.strip())
        if file_item is None:
            continue
        title = str(file_item.get("name") or file_item.get("id") or raw_id).strip()
        parts = [f"File: {title}"]
        if isinstance(file_item.get("id"), str) and file_item["id"].strip():
            parts.append(f"ID: {file_item['id'].strip()}")
        kind = file_item.get("kind")
        if isinstance(kind, str) and kind.strip():
            parts.append(f"Kind: {kind.strip()}")
        path = file_item.get("path")
        if isinstance(path, str) and path.strip():
            parts.append(f"Path: {path.strip()}")
        description = file_item.get("description")
        if isinstance(description, str) and description.strip():
            parts.append(f"Description: {description.strip()}")
        content = str(file_item.get("content") or "").strip()
        if content:
            if len(content) > 6000:
                content = content[:6000].rstrip() + "\n[truncated]"
            parts.extend(["Content:", content])
        blocks.append("\n".join(parts))
    if not blocks:
        return ""
    return "Attached files:\n\n" + "\n\n---\n\n".join(blocks)


def render_chat_ui_html(settings: dict[str, Any]) -> str:
    bootstrap = _settings_bootstrap(settings)
    bootstrap_json = _json_script_value(bootstrap)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta name=\"theme-color\" id=\"theme-color\" content=\"#0b1020\">
  <meta name=\"apple-mobile-web-app-capable\" content=\"yes\">
  <meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\">
  <link rel=\"manifest\" href=\"/manifest.webmanifest\">
  <link rel=\"icon\" href=\"/qwen-gen-icon.svg\" type=\"image/svg+xml\">
  <title>Qwen Gen Chat</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1020;
      --panel: #11172b;
      --panel-2: #171f38;
      --line: rgba(255,255,255,0.10);
      --text: #e5eefc;
      --muted: #94a3b8;
      --accent: #66e3c4;
      --accent-2: #7c9cff;
      --danger: #ff7a90;
      --bubble-user: #1c2c4a;
      --bubble-assistant: #16253a;
      --shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top left, rgba(102, 227, 196, 0.14), transparent 32%),
        radial-gradient(circle at top right, rgba(124, 156, 255, 0.16), transparent 30%),
        linear-gradient(180deg, #09101e 0%, #0b1020 100%);
      color: var(--text);
    }}
    body[data-theme="light"] {{
      color-scheme: light;
      --bg: #f4f7fb;
      --panel: rgba(255,255,255,0.90);
      --panel-2: #eef3fb;
      --line: rgba(14, 23, 38, 0.12);
      --text: #132033;
      --muted: #5b6577;
      --accent: #15a98c;
      --accent-2: #4b73f0;
      --danger: #d94b63;
      --bubble-user: #dfe9ff;
      --bubble-assistant: #edf2fa;
      --shadow: 0 20px 50px rgba(35, 47, 74, 0.12);
      background:
        radial-gradient(circle at top left, rgba(21, 169, 140, 0.14), transparent 32%),
        radial-gradient(circle at top right, rgba(75, 115, 240, 0.14), transparent 30%),
        linear-gradient(180deg, #f8fbff 0%, #eef4fb 100%);
    }}
    body[data-theme="light"] .app::before {{
      opacity: 0.12;
      mix-blend-mode: multiply;
    }}
    .app {{
      display: grid;
      grid-template-columns: 292px 1fr;
      min-height: 100vh;
    }}
    .app::before {{
      content: '';
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        radial-gradient(circle at 15% 15%, rgba(102, 227, 196, 0.08), transparent 28%),
        radial-gradient(circle at 85% 0%, rgba(124, 156, 255, 0.10), transparent 24%),
        linear-gradient(transparent 95%, rgba(255,255,255,0.03) 95%),
        linear-gradient(90deg, transparent 95%, rgba(255,255,255,0.03) 95%);
      background-size: auto, auto, 72px 72px, 72px 72px;
      opacity: 0.26;
      mix-blend-mode: screen;
    }}
    .sidebar {{
      background: rgba(10, 16, 31, 0.82);
      border-right: 1px solid var(--line);
      backdrop-filter: blur(18px);
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
    }}
    .sidebar-toggle {{
      width: 100%;
      justify-content: center;
    }}
    .theme-toggle {{
      min-width: 112px;
      justify-content: center;
    }}
    .help-toggle {{
      min-width: 120px;
      justify-content: center;
    }}
    .voice-toggle {{
      min-width: 92px;
      justify-content: center;
    }}
    .brand {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 10px 10px 14px;
      border-bottom: 1px solid var(--line);
    }}
    .brand h1 {{
      margin: 0;
      font-size: 1.2rem;
      letter-spacing: 0.02em;
    }}
    .brand p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .workspace-hero {{
      display: grid;
      gap: 12px;
      padding: 14px;
      border-radius: 20px;
      border: 1px solid rgba(102, 227, 196, 0.18);
      background:
        linear-gradient(160deg, rgba(102, 227, 196, 0.14), rgba(124, 156, 255, 0.05)),
        rgba(17, 23, 43, 0.76);
      box-shadow: 0 22px 42px rgba(0, 0, 0, 0.18);
    }}
    .workspace-hero .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 0.7rem;
      color: var(--accent);
    }}
    .workspace-hero h2 {{
      margin: 0;
      font-size: 1.08rem;
      line-height: 1.15;
    }}
    .workspace-hero p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }}
    .workspace-stats {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .workspace-stat {{
      padding: 10px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
      min-width: 0;
    }}
    .workspace-stat strong {{
      display: block;
      font-size: 0.95rem;
      margin-bottom: 4px;
    }}
    .workspace-stat span {{
      display: block;
      color: var(--muted);
      font-size: 0.76rem;
      line-height: 1.4;
    }}
    .panel {{
      background: rgba(17, 23, 43, 0.84);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      box-shadow: var(--shadow);
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    select, textarea, input, button {{
      font: inherit;
    }}
    select, textarea, input {{
      width: 100%;
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      outline: none;
    }}
    textarea {{
      resize: vertical;
      min-height: 92px;
    }}
    button {{
      border: 0;
      border-radius: 14px;
      padding: 12px 14px;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #04111d;
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--line);
      font-weight: 600;
    }}
    button.danger {{
      background: rgba(255, 122, 144, 0.14);
      color: #ffd5dc;
      border: 1px solid rgba(255, 122, 144, 0.25);
    }}
    .row {{ display: flex; gap: 10px; }}
    .row > * {{ flex: 1; }}
    .toolbar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .toolbar > * {{
      flex: 1;
      min-width: 0;
    }}
    .stack {{ display: flex; flex-direction: column; gap: 12px; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .template-library {{
      display: grid;
      gap: 10px;
    }}
    .template-creator {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      margin-bottom: 10px;
    }}
    .compare-controls {{
      display: grid;
      gap: 10px;
    }}
    .compare-toggle {{
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .provider-controls {{
      display: grid;
      gap: 10px;
    }}
    .provider-controls .toolbar {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .provider-item {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .provider-item .chip {{
      flex: 1;
      text-align: left;
    }}
    .provider-item .danger {{
      width: 36px;
      height: 36px;
      padding: 0;
      border-radius: 999px;
      line-height: 1;
    }}
    .kb-controls {{
      display: grid;
      gap: 10px;
    }}
    .kb-controls .toolbar {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .web-search-controls {{
      display: grid;
      gap: 10px;
    }}
    .web-search-controls .toolbar {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .kb-item {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .kb-item .chip {{
      flex: 1;
      text-align: left;
    }}
    .kb-item .danger {{
      width: 36px;
      height: 36px;
      padding: 0;
      border-radius: 999px;
      line-height: 1;
    }}
    .agent-controls {{
      display: grid;
      gap: 10px;
    }}
    .agent-controls .toolbar {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .agent-editor {{
      display: grid;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.03);
    }}
    .agent-editor .template-creator {{
      margin-bottom: 0;
    }}
    .agent-item {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .agent-item .chip {{
      flex: 1;
      text-align: left;
    }}
    .resource-controls {{
      display: grid;
      gap: 10px;
    }}
    .resource-controls .toolbar {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .resource-editor {{
      display: grid;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.03);
    }}
    .kb-controls .resource-editor,
    .resource-controls .resource-editor {{
      margin-top: 4px;
    }}
    .resource-item {{
      display: grid;
      gap: 8px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.03);
    }}
    .resource-item .row {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .resource-item .chip {{
      flex: 1;
      text-align: left;
    }}
    .resource-preview {{
      max-height: 160px;
      overflow: auto;
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(11,16,32,0.78);
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .template-item {{
      display: grid;
      gap: 10px;
      padding: 12px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
    }}
    .template-item .chip {{
      width: 100%;
      text-align: left;
    }}
    .template-item .danger {{
      width: 36px;
      height: 36px;
      padding: 0;
      border-radius: 999px;
      line-height: 1;
    }}
    .template-item .template-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      min-width: 0;
    }}
    .template-item .template-title strong {{
      font-size: 0.98rem;
    }}
    .template-item .template-preview {{
      color: var(--muted);
      line-height: 1.5;
      font-size: 0.84rem;
      min-height: 2.6em;
    }}
    .template-item .template-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .template-item .template-actions button {{
      flex: 1;
      min-width: 0;
      padding: 9px 10px;
      border-radius: 12px;
      font-size: 0.84rem;
    }}
    .template-item.starter {{
      border-color: rgba(102, 227, 196, 0.22);
      background: linear-gradient(180deg, rgba(102, 227, 196, 0.10), rgba(255,255,255,0.03));
    }}
    .template-drawer-toggle {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .template-drawer-toggle .secondary {{
      flex: 1;
      min-width: 0;
    }}
    .template-drawer {{
      position: fixed;
      inset: 0;
      display: none;
      z-index: 42;
    }}
    .template-drawer.open {{
      display: block;
    }}
    .template-drawer-backdrop {{
      position: absolute;
      inset: 0;
      background: rgba(4, 9, 18, 0.72);
      backdrop-filter: blur(12px);
    }}
    .template-drawer-panel {{
      position: absolute;
      top: 16px;
      right: 16px;
      bottom: 16px;
      width: min(980px, calc(100vw - 32px));
      display: grid;
      grid-template-rows: auto auto 1fr;
      gap: 14px;
      padding: 18px;
      border-radius: 24px;
      border: 1px solid rgba(255,255,255,0.10);
      background: rgba(17, 23, 43, 0.98);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .template-drawer header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }}
    .template-drawer header h3 {{
      margin: 0 0 4px;
      font-size: 1.05rem;
    }}
    .template-drawer header p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.45;
    }}
    .template-drawer-tools {{
      display: grid;
      gap: 10px;
    }}
    .template-gallery-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .template-gallery-tabs button {{
      flex: 0 0 auto;
      padding: 8px 11px;
      border-radius: 999px;
      font-size: 0.82rem;
    }}
    .template-gallery-tabs button.active {{
      background: rgba(102, 227, 196, 0.18);
      border: 1px solid rgba(102, 227, 196, 0.35);
    }}
    .template-gallery-search {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
    }}
    .template-gallery-body {{
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(280px, 0.7fr);
      gap: 14px;
      min-height: 0;
    }}
    .template-gallery-list {{
      display: grid;
      gap: 10px;
      overflow: auto;
      padding-right: 4px;
      align-content: start;
    }}
    .template-gallery-card {{
      display: grid;
      gap: 10px;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
    }}
    .template-gallery-card.active {{
      border-color: rgba(102, 227, 196, 0.35);
      background: rgba(102, 227, 196, 0.08);
    }}
    .template-gallery-card .template-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}
    .template-gallery-card h4 {{
      margin: 0;
      font-size: 0.98rem;
    }}
    .template-gallery-card .meta {{
      font-size: 0.82rem;
      color: var(--muted);
    }}
    .template-gallery-card .preview {{
      color: var(--muted);
      line-height: 1.55;
      font-size: 0.86rem;
    }}
    .template-gallery-card .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .template-gallery-card .actions button {{
      flex: 1;
      min-width: 0;
      padding: 9px 10px;
      border-radius: 12px;
      font-size: 0.83rem;
    }}
    .template-compare {{
      display: grid;
      gap: 10px;
      min-height: 0;
      overflow: auto;
      padding-left: 4px;
    }}
    .template-compare .compare-card {{
      display: grid;
      gap: 10px;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
    }}
    .template-compare .compare-card h4 {{
      margin: 0;
      font-size: 0.94rem;
    }}
    .template-compare pre {{
      margin: 0;
      padding: 12px;
      border-radius: 14px;
      white-space: pre-wrap;
      background: rgba(11,16,32,0.82);
      border: 1px solid var(--line);
      color: var(--text);
      line-height: 1.55;
    }}
    .folder-item {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .folder-item .chip {{
      flex: 1;
      text-align: left;
    }}
    .folder-item .danger {{
      width: 36px;
      height: 36px;
      padding: 0;
      border-radius: 999px;
      line-height: 1;
    }}
    .conversation-filter {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .conversation-filter button {{
      flex: 0 0 auto;
      padding: 7px 10px;
      border-radius: 999px;
    }}
    .conversation-filter button.active {{
      background: rgba(102, 227, 196, 0.18);
      border-color: rgba(102, 227, 196, 0.35);
    }}
    .typing-indicator {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 0.92rem;
      letter-spacing: 0.02em;
    }}
    .typing-dots {{
      display: inline-flex;
      gap: 4px;
    }}
    .typing-dots span {{
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--accent);
      opacity: 0.35;
      animation: typingPulse 1.2s infinite ease-in-out;
    }}
    .typing-dots span:nth-child(2) {{ animation-delay: 0.15s; }}
    .typing-dots span:nth-child(3) {{ animation-delay: 0.3s; }}
    @keyframes typingPulse {{
      0%, 80%, 100% {{ transform: translateY(0); opacity: 0.35; }}
      40% {{ transform: translateY(-3px); opacity: 1; }}
    }}
    .chip {{
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
      color: var(--text);
      border-radius: 999px;
      padding: 8px 10px;
      cursor: pointer;
      font-size: 0.88rem;
    }}
    .file-item {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .file-item .chip {{
      flex: 1;
      text-align: left;
    }}
    .file-item .danger {{
      width: 36px;
      height: 36px;
      padding: 0;
      border-radius: 999px;
      line-height: 1;
    }}
    .file-preview-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(4, 9, 18, 0.72);
      backdrop-filter: blur(12px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 30;
      padding: 24px;
    }}
    .file-preview-backdrop.open {{
      display: flex;
    }}
    .file-preview {{
      width: min(960px, 100%);
      max-height: min(86vh, 960px);
      overflow: hidden;
      background: rgba(17, 23, 43, 0.98);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 24px;
      box-shadow: var(--shadow);
      display: grid;
      grid-template-rows: auto 1fr auto;
    }}
    .file-preview header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 18px 20px;
      border-bottom: 1px solid var(--line);
    }}
    .file-preview header h3 {{
      margin: 0;
      font-size: 1rem;
    }}
    .file-preview main {{
      overflow: auto;
      padding: 20px;
    }}
    .file-preview pre {{
      margin: 0;
      white-space: pre-wrap;
      word-wrap: break-word;
      background: #0b1020;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      color: var(--text);
    }}
    .file-preview-figure {{
      margin: 0 0 18px;
      display: grid;
      gap: 10px;
      justify-items: center;
    }}
    .file-preview-figure img {{
      max-width: 100%;
      max-height: 50vh;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: #0b1020;
      object-fit: contain;
    }}
    .file-preview-figure figcaption {{
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .file-preview footer {{
      display: flex;
      gap: 10px;
      justify-content: flex-end;
      padding: 16px 20px 20px;
      border-top: 1px solid var(--line);
    }}
    .conversations {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      overflow: auto;
      max-height: 42vh;
    }}
    .conversation-item {{
      width: 100%;
      text-align: left;
      background: rgba(255,255,255,0.03);
      border: 1px solid var(--line);
      color: var(--text);
      border-radius: 14px;
      padding: 11px 12px;
    }}
    .conversation-item.active {{
      border-color: rgba(102, 227, 196, 0.38);
      background: rgba(102, 227, 196, 0.08);
    }}
    .conversation-item small {{ color: var(--muted); display: block; margin-top: 4px; }}
    .conversation-item-body {{
      display: grid;
      gap: 8px;
    }}
    .conversation-item-select {{
      width: 100%;
      border: 0;
      background: transparent;
      color: inherit;
      text-align: left;
      padding: 0;
      font: inherit;
      cursor: pointer;
    }}
    .conversation-item-select strong {{
      display: block;
    }}
    .conversation-item-actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .conversation-item-actions button {{
      padding: 8px 10px;
      border-radius: 10px;
      font-size: 0.82rem;
      flex: 1;
    }}
    .main {{
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-width: 0;
      position: relative;
    }}
    .topbar {{
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      justify-content: flex-start;
      gap: 14px;
      padding: 18px 24px 16px;
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(180deg, rgba(14, 22, 39, 0.78), rgba(10, 16, 31, 0.60)),
        rgba(10, 16, 31, 0.60);
      backdrop-filter: blur(18px);
      position: sticky;
      top: 0;
      z-index: 4;
    }}
    .topbar-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      width: 100%;
    }}
    .topbar-head .toolbar {{
      justify-content: flex-end;
    }}
    .topbar h2 {{
      margin: 0;
      font-size: 1.15rem;
    }}
    .topbar .meta {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .session-banner {{
      width: 100%;
      display: grid;
      gap: 14px;
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px solid rgba(102, 227, 196, 0.18);
      background: linear-gradient(135deg, rgba(102, 227, 196, 0.10), rgba(124, 156, 255, 0.06));
    }}
    .session-banner .eyebrow {{
      display: inline-flex;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 0.68rem;
      color: var(--accent);
      margin-bottom: 8px;
    }}
    .session-banner h3 {{
      margin: 0;
      font-size: 0.98rem;
      line-height: 1.35;
      max-width: 78ch;
    }}
    .session-banner p {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.45;
      max-width: 86ch;
    }}
    .status-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      width: 100%;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 11px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
      color: var(--text);
      font-size: 0.82rem;
      line-height: 1;
    }}
    .pill strong {{
      font-weight: 700;
    }}
    .chat {{
      padding: 24px;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
      width: min(1120px, 100%);
      margin: 0 auto;
    }}
    .scroll-latest {{
      position: fixed;
      right: 24px;
      bottom: 24px;
      z-index: 40;
      border-radius: 999px;
      box-shadow: var(--shadow);
      display: none;
    }}
    .scroll-latest.visible {{
      display: inline-flex;
    }}
    .message {{
      max-width: min(860px, 100%);
      padding: 17px 18px;
      border: 1px solid var(--line);
      border-radius: 20px;
      white-space: pre-wrap;
      word-wrap: break-word;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.16);
      position: relative;
      overflow: hidden;
    }}
    .message.user {{
      margin-left: auto;
      background:
        linear-gradient(180deg, rgba(28, 44, 74, 0.98), rgba(22, 32, 54, 0.96));
      border-color: rgba(124, 156, 255, 0.18);
    }}
    .message.assistant {{
      background:
        linear-gradient(180deg, rgba(22, 37, 58, 0.98), rgba(15, 25, 44, 0.96));
      border-color: rgba(102, 227, 196, 0.12);
    }}
    .message.system {{
      margin-left: auto;
      margin-right: auto;
      max-width: min(920px, 100%);
      background: rgba(17, 23, 43, 0.90);
      border-color: rgba(148, 163, 184, 0.20);
    }}
    .message::before {{
      content: '';
      position: absolute;
      inset: 0 auto 0 0;
      width: 4px;
      background: linear-gradient(180deg, rgba(102, 227, 196, 0.9), rgba(124, 156, 255, 0.8));
    }}
    .message.user::before {{
      inset: 0 0 0 auto;
      background: linear-gradient(180deg, rgba(124, 156, 255, 0.95), rgba(102, 227, 196, 0.8));
    }}
    .message.system::before {{
      inset: 0 auto 0 0;
      background: linear-gradient(180deg, rgba(148, 163, 184, 0.9), rgba(102, 227, 196, 0.35));
    }}
    .message.error {{ border-color: rgba(255, 122, 144, 0.38); color: #ffd5dc; }}
    .message .role {{
      display: block;
      font-size: 0.78rem;
      color: var(--text);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 10px;
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.06);
    }}
    .message-content {{
      display: grid;
      gap: 0.75rem;
      line-height: 1.65;
    }}
    .message-content :first-child {{
      margin-top: 0;
    }}
    .message-content :last-child {{
      margin-bottom: 0;
    }}
    .message-content a {{
      color: #90cdf4;
    }}
    .message-content code {{
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      padding: 0.1rem 0.35rem;
    }}
    .message-content pre {{
      margin: 0;
      padding: 14px;
      overflow: auto;
      background: #0b1020;
      border-radius: 14px;
      border: 1px solid var(--line);
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .message-content pre code {{
      background: transparent;
      border: 0;
      padding: 0;
    }}
    .message-content ul,
    .message-content ol {{
      margin: 0;
      padding-left: 1.4rem;
    }}
    .message-content blockquote {{
      margin: 0;
      padding-left: 1rem;
      border-left: 3px solid rgba(124, 156, 255, 0.45);
      color: #c8d6f7;
    }}
    .message-content h1,
    .message-content h2,
    .message-content h3,
    .message-content h4 {{
      margin: 0.2rem 0 0;
      line-height: 1.25;
    }}
    .message-content table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 14px;
    }}
    .message-content th,
    .message-content td {{
      border: 1px solid rgba(255,255,255,0.08);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    .message-content th {{
      background: rgba(255,255,255,0.05);
    }}
    .message-content .math {{
      font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
      padding: 0.05rem 0.35rem;
      border-radius: 999px;
      background: rgba(102, 227, 196, 0.1);
      border: 1px solid rgba(102, 227, 196, 0.18);
      color: #d5fff5;
    }}
    .message-content del {{
      color: #94a3b8;
    }}
    .task-item {{
      display: flex;
      gap: 0.5rem;
      align-items: flex-start;
    }}
    .task-box {{
      flex: 0 0 auto;
      font-weight: 700;
      color: #66e3c4;
    }}
    .search-hit {{
      background: rgba(250, 204, 21, 0.16);
      box-shadow: 0 0 0 1px rgba(250, 204, 21, 0.2) inset;
      border-radius: 4px;
    }}
    .search-hit.current {{
      background: rgba(102, 227, 196, 0.24);
      box-shadow: 0 0 0 1px rgba(102, 227, 196, 0.38) inset;
    }}
    .message-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }}
    .message-actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .message-actions button {{
      padding: 7px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
    }}
    .message.editing {{
      border-color: rgba(102, 227, 196, 0.38);
      background: rgba(102, 227, 196, 0.06);
    }}
    .message-editor {{
      display: grid;
      gap: 10px;
    }}
    .message-editor textarea {{
      min-height: 140px;
    }}
    .chat-empty {{
      display: grid;
      place-items: center;
      min-height: 100%;
      padding: 28px 12px 56px;
    }}
    .chat-empty-card {{
      width: min(760px, 100%);
      display: grid;
      gap: 14px;
      padding: 22px;
      border-radius: 24px;
      border: 1px solid rgba(255,255,255,0.10);
      background:
        radial-gradient(circle at top left, rgba(102, 227, 196, 0.12), transparent 32%),
        rgba(17, 23, 43, 0.82);
      box-shadow: var(--shadow);
    }}
    .chat-empty-card .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 0.7rem;
      color: var(--accent);
    }}
    .chat-empty-card h3 {{
      margin: 0;
      font-size: 1.45rem;
    }}
    .chat-empty-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
    }}
    .chat-empty-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .chat-empty-actions button {{
      flex: 1;
      min-width: 140px;
    }}
    .composer {{
      padding: 18px 24px 24px;
      border-top: 1px solid var(--line);
      background:
        linear-gradient(180deg, rgba(10, 16, 31, 0.66), rgba(10, 16, 31, 0.82)),
        rgba(10, 16, 31, 0.72);
      backdrop-filter: blur(18px);
    }}
    .composer.drag-over {{
      border-top-color: rgba(102, 227, 196, 0.48);
      background: rgba(102, 227, 196, 0.10);
      box-shadow: inset 0 0 0 1px rgba(102, 227, 196, 0.20);
    }}
    .composer.paste-over {{
      border-top-color: rgba(124, 156, 255, 0.48);
      background: rgba(124, 156, 255, 0.10);
      box-shadow: inset 0 0 0 1px rgba(124, 156, 255, 0.20);
    }}
    .composer form {{
      display: grid;
      gap: 14px;
      width: min(1120px, 100%);
      margin: 0 auto;
    }}
    .composer-actions {{
      display: flex;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
    }}
    .composer-actions .stack {{
      gap: 4px;
    }}
    .composer-surface {{
      display: grid;
      gap: 12px;
      padding: 14px;
      border-radius: 24px;
      border: 1px solid rgba(255,255,255,0.08);
      background:
        linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015)),
        rgba(17, 23, 43, 0.70);
      box-shadow: var(--shadow);
    }}
    .composer-surface textarea {{
      min-height: 132px;
      border-radius: 18px;
      padding: 16px 18px;
      line-height: 1.6;
    }}
    .composer-strip {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
    }}
    .composer-strip .hint {{
      flex: 1;
      min-width: min(460px, 100%);
    }}
    .composer-quick-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .composer-quick-actions button {{
      padding: 8px 11px;
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 600;
    }}
    .composer-attachments {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .composer-attachments .chip {{
      background: rgba(255,255,255,0.05);
    }}
    .hint {{ color: var(--muted); font-size: 0.9rem; }}
    .muted {{ color: var(--muted); }}
    .shortcuts-backdrop {{
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background: rgba(4, 9, 18, 0.72);
      backdrop-filter: blur(12px);
      z-index: 40;
    }}
    .shortcuts-backdrop.open {{
      display: flex;
    }}
    .shortcuts-dialog {{
      width: min(720px, 100%);
      border-radius: 24px;
      border: 1px solid var(--line);
      background: rgba(17, 23, 43, 0.98);
      box-shadow: var(--shadow);
      padding: 20px;
      display: grid;
      gap: 16px;
    }}
    .shortcuts-dialog header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .shortcuts-dialog h3 {{
      margin: 0;
      font-size: 1rem;
    }}
    .shortcut-list {{
      display: grid;
      gap: 10px;
    }}
    .shortcut-row {{
      display: grid;
      grid-template-columns: 180px 1fr;
      gap: 12px;
      align-items: start;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.03);
    }}
    .shortcut-row kbd {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 92px;
      padding: 7px 10px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      font: inherit;
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }}
    .app.sidebar-collapsed {{
      grid-template-columns: 92px 1fr;
    }}
    .app.sidebar-collapsed .sidebar {{
      padding: 14px 10px;
      overflow: hidden;
    }}
    .app.sidebar-collapsed .sidebar > :not(.brand) {{
      display: none;
    }}
    .app.sidebar-collapsed .brand {{
      align-items: center;
      text-align: center;
      padding: 8px 0 10px;
    }}
    .app.sidebar-collapsed .brand p {{
      display: none;
    }}
    .app.sidebar-collapsed .brand h1 {{
      font-size: 0.95rem;
      line-height: 1.15;
      letter-spacing: 0.04em;
    }}
    @media (max-width: 980px) {{
      .app {{ grid-template-columns: 1fr; }}
      .sidebar {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .conversations {{ max-height: none; }}
      .app.sidebar-collapsed .sidebar {{
        display: none;
      }}
    }}
  </style>
</head>
<body>
  <div class=\"app\" id=\"app\">
    <aside class=\"sidebar\">
      <div class=\"brand\">
        <h1>Qwen Gen Chat</h1>
        <p>Ready-to-use local chat interface driven by your qwen-gen settings.</p>
      </div>
      <div class=\"workspace-hero\">
        <div>
          <div class=\"eyebrow\">Workspace overview</div>
          <h2>Chat interface ready for use</h2>
          <p>Model routing, templates, files, memory, notes, tools, and webhooks stay in one place and are ready once your settings are loaded.</p>
        </div>
        <div class=\"workspace-stats\">
          <div class=\"workspace-stat\">
            <strong id=\"workspace-model-count\">0 models</strong>
            <span>Configured providers and routing targets.</span>
          </div>
          <div class=\"workspace-stat\">
            <strong id=\"workspace-template-count\">0 templates</strong>
            <span>Saved prompts plus built-in starters.</span>
          </div>
          <div class=\"workspace-stat\">
            <strong id=\"workspace-chat-count\">0 chats</strong>
            <span>Saved conversations in the active workspace.</span>
          </div>
        </div>
      </div>
      <div class=\"panel stack\">
        <div>
          <label class=\"label\" for=\"model-select\">Model</label>
          <select id=\"model-select\"></select>
        </div>
        <div class=\"compare-controls\">
          <label class=\"label\" for=\"compare-model-select\">Compare models</label>
          <div class=\"template-creator\">
            <label class=\"compare-toggle\" for=\"compare-model-toggle\">
              <input id=\"compare-model-toggle\" type=\"checkbox\">
              Enable compare mode
            </label>
            <select id=\"compare-model-select\"></select>
          </div>
          <div class=\"hint\">Send one prompt to two models and merge the answers.</div>
        </div>
        <div class=\"provider-controls\">
          <label class=\"label\">Providers</label>
          <div class=\"toolbar\">
            <button id=\"add-provider-presets\" class=\"secondary\" type=\"button\">Add presets</button>
            <button id=\"refresh-providers\" class=\"secondary\" type=\"button\">Refresh</button>
          </div>
          <div id=\"provider-chips\" class=\"chips\"></div>
          <div class=\"hint\">Manage the model registry that powers the browser chat and `serve` API.</div>
        </div>
        <div class=\"kb-controls\">
          <label class=\"label\">Knowledge Bases</label>
          <div class=\"template-creator\">
            <input id=\"kb-query\" type=\"search\" placeholder=\"Search knowledge base indexes\">
            <button id=\"kb-run-query\" class=\"secondary\" type=\"button\">Query</button>
          </div>
          <div class=\"toolbar\">
            <button id=\"new-kb\" class=\"secondary\" type=\"button\">New</button>
            <button id=\"edit-kb\" class=\"secondary\" type=\"button\">Edit</button>
            <button id=\"delete-kb\" class=\"danger\" type=\"button\">Delete</button>
            <button id=\"refresh-kb\" class=\"secondary\" type=\"button\">Refresh</button>
            <button id=\"add-kb\" class=\"secondary\" type=\"button\">Open editor</button>
          </div>
          <div class=\"template-creator\">
            <input id=\"kb-import-file\" type=\"file\" accept=\"application/json,.json\">
            <button id=\"kb-import\" class=\"secondary\" type=\"button\">Import JSON</button>
            <button id=\"kb-export\" class=\"secondary\" type=\"button\">Export JSON</button>
          </div>
          <div class=\"template-creator\">
            <input id=\"kb-output-dir\" type=\"text\" placeholder=\"Sync output directory (optional)\">
            <input id=\"kb-watch-iterations\" type=\"number\" min=\"1\" step=\"1\" value=\"1\">
            <input id=\"kb-watch-interval\" type=\"number\" min=\"0\" step=\"0.5\" value=\"0\">
          </div>
          <div class=\"toolbar\">
            <button id=\"kb-sync\" class=\"secondary\" type=\"button\">Sync</button>
            <button id=\"kb-watch\" class=\"secondary\" type=\"button\">Watch</button>
          </div>
          <div id=\"kb-chips\" class=\"chips\"></div>
          <div id=\"kb-preview\" class=\"resource-preview muted\">Select a knowledge base to preview it here.</div>
          <div class=\"resource-editor\">
            <label class=\"label\" for=\"kb-editor-name\">Knowledge base editor</label>
            <input id=\"kb-editor-name\" type=\"text\" placeholder=\"Knowledge base name\">
            <textarea id=\"kb-editor-source-dir\" placeholder=\"Source directory or URLs\"></textarea>
            <textarea id=\"kb-editor-description\" placeholder=\"Description\"></textarea>
            <input id=\"kb-editor-tags\" type=\"text\" placeholder=\"Tags, comma-separated\">
            <div class=\"toolbar\">
              <button id=\"kb-save\" class=\"secondary\" type=\"button\">Save</button>
              <button id=\"kb-cancel\" class=\"secondary\" type=\"button\">Cancel</button>
            </div>
            <div class=\"hint\" id=\"kb-editor-hint\">Create or edit a knowledge base without dialogs.</div>
          </div>
          <div id=\"kb-results\" class=\"stack\"></div>
          <div class=\"hint\">Browse registered RAG sources and inspect matched chunks from existing indexes.</div>
        </div>
        <div class=\"web-search-controls\">
          <label class=\"label\">Web Search</label>
          <div class=\"template-creator\">
            <input id=\"web-search-query\" type=\"search\" placeholder=\"Search the web\">
            <button id=\"web-search-run\" class=\"secondary\" type=\"button\">Search</button>
          </div>
          <div class=\"template-creator\">
            <select id=\"web-search-provider\"></select>
            <input id=\"web-search-fallback\" type=\"text\" placeholder=\"Fallback providers, comma-separated\">
          </div>
          <div class=\"template-creator\">
            <input id=\"web-search-engine-url\" type=\"text\" placeholder=\"Custom engine URL\">
            <input id=\"web-search-api-key\" type=\"password\" placeholder=\"API key (optional)\">
          </div>
          <div class=\"template-creator\">
            <input id=\"web-search-base-id\" type=\"text\" placeholder=\"Knowledge base id (optional)\">
            <input id=\"web-search-name\" type=\"text\" placeholder=\"Knowledge base name (optional)\">
          </div>
          <div class=\"template-creator\">
            <input id=\"web-search-description\" type=\"text\" placeholder=\"Knowledge base description (optional)\">
            <input id=\"web-search-save-limit\" type=\"number\" min=\"1\" max=\"20\" value=\"5\">
          </div>
          <div class=\"toolbar\">
            <button id=\"web-search-save\" class=\"secondary\" type=\"button\">Save to knowledge</button>
            <button id=\"web-search-clear\" class=\"secondary\" type=\"button\">Clear</button>
          </div>
          <div id=\"web-search-results\" class=\"stack\"></div>
          <div class=\"hint\">Search from the browser, then save selected results into a knowledge base.</div>
        </div>
        <div class=\"agent-controls\">
          <label class=\"label\" for=\"agent-select\">Agents</label>
          <div class=\"template-creator\">
            <select id=\"agent-select\"></select>
            <button id=\"agent-apply\" class=\"secondary\" type=\"button\">Apply</button>
          </div>
          <div class=\"toolbar\">
            <button id=\"new-agent\" class=\"secondary\" type=\"button\">New</button>
            <button id=\"edit-agent\" class=\"secondary\" type=\"button\">Edit</button>
            <button id=\"delete-agent\" class=\"danger\" type=\"button\">Delete</button>
            <button id=\"refresh-agents\" class=\"secondary\" type=\"button\">Refresh</button>
            <button id=\"new-agent-chat\" class=\"secondary\" type=\"button\">New chat</button>
          </div>
          <div class=\"template-creator\">
            <input id=\"agent-import-file\" type=\"file\" accept=\"application/json,.json\">
            <button id=\"agent-import\" class=\"secondary\" type=\"button\">Import JSON</button>
            <button id=\"agent-export\" class=\"secondary\" type=\"button\">Export JSON</button>
          </div>
          <div class=\"toolbar\">
            <button id=\"agent-share-md\" class=\"secondary\" type=\"button\">Share MD</button>
            <button id=\"agent-share-html\" class=\"secondary\" type=\"button\">Share HTML</button>
            <button id=\"agent-share-json\" class=\"secondary\" type=\"button\">Share JSON</button>
            <button id=\"agent-clone\" class=\"secondary\" type=\"button\">Clone</button>
          </div>
          <div id=\"agent-chips\" class=\"chips\"></div>
          <div id=\"agent-preview\" class=\"resource-preview muted\">Select an agent to preview it here.</div>
          <div class=\"agent-editor\">
            <label class=\"label\" for=\"agent-editor-name\">Agent editor</label>
            <div class=\"template-creator\">
              <input id=\"agent-editor-name\" type=\"text\" placeholder=\"Agent name\">
              <input id=\"agent-editor-base-model\" type=\"text\" placeholder=\"Base model\">
            </div>
            <div class=\"template-creator\">
              <select id=\"agent-editor-folder\"></select>
              <input id=\"agent-editor-description\" type=\"text\" placeholder=\"Description\">
            </div>
            <textarea id=\"agent-editor-system-prompt\" placeholder=\"System prompt\"></textarea>
            <textarea id=\"agent-editor-tools\" placeholder=\"Tools, comma-separated\"></textarea>
            <textarea id=\"agent-editor-knowledge\" placeholder=\"Knowledge, comma-separated\"></textarea>
            <textarea id=\"agent-editor-skills\" placeholder=\"Skills, comma-separated\"></textarea>
            <div class=\"template-creator\">
              <input id=\"agent-editor-avatar\" type=\"text\" placeholder=\"Avatar URL\">
              <input id=\"agent-editor-voice\" type=\"text\" placeholder=\"Voice\">
            </div>
            <select id=\"agent-editor-visibility\">
              <option value=\"\">Visibility</option>
              <option value=\"public\">Public</option>
              <option value=\"private\">Private</option>
            </select>
            <div class=\"toolbar\">
              <button id=\"agent-save\" class=\"secondary\" type=\"button\">Save</button>
              <button id=\"agent-cancel\" class=\"secondary\" type=\"button\">Cancel</button>
            </div>
            <div class=\"hint\" id=\"agent-editor-hint\">Create or edit an agent preset without leaving the page.</div>
          </div>
          <div class=\"hint\">Choose a preset agent to seed the active chat with its model and system prompt.</div>
        </div>
        <div class=\"resource-controls\">
          <label class=\"label\">Skills</label>
          <div class=\"toolbar\">
            <button id=\"new-skill\" class=\"secondary\" type=\"button\">New</button>
            <button id=\"edit-skill\" class=\"secondary\" type=\"button\">Edit</button>
            <button id=\"delete-skill\" class=\"danger\" type=\"button\">Delete</button>
            <button id=\"refresh-skills\" class=\"secondary\" type=\"button\">Refresh</button>
            <button id=\"skill-use\" class=\"secondary\" type=\"button\">Use in prompt</button>
          </div>
          <div id=\"skill-chips\" class=\"stack\"></div>
          <div id=\"skill-preview\" class=\"resource-preview muted\">Select a skill to preview it here.</div>
          <div class=\"resource-editor\">
            <label class=\"label\" for=\"skill-editor-name\">Skill editor</label>
            <input id=\"skill-editor-name\" type=\"text\" placeholder=\"Skill name\">
            <textarea id=\"skill-editor-content\" placeholder=\"Skill content\"></textarea>
            <input id=\"skill-editor-tags\" type=\"text\" placeholder=\"Tags, comma-separated\">
            <div class=\"toolbar\">
              <button id=\"skill-save\" class=\"secondary\" type=\"button\">Save</button>
              <button id=\"skill-cancel\" class=\"secondary\" type=\"button\">Cancel</button>
            </div>
            <div class=\"hint\" id=\"skill-editor-hint\">Create or edit a reusable skill without dialogs.</div>
          </div>
        </div>
        <div class=\"resource-controls\">
          <label class=\"label\">Memories</label>
          <div class=\"toolbar\">
            <button id=\"new-memory\" class=\"secondary\" type=\"button\">New</button>
            <button id=\"edit-memory\" class=\"secondary\" type=\"button\">Edit</button>
            <button id=\"delete-memory\" class=\"danger\" type=\"button\">Delete</button>
            <button id=\"refresh-memories\" class=\"secondary\" type=\"button\">Refresh</button>
            <button id=\"memory-use\" class=\"secondary\" type=\"button\">Use in prompt</button>
          </div>
          <div id=\"memory-chips\" class=\"stack\"></div>
          <div id=\"memory-preview\" class=\"resource-preview muted\">Select a memory to preview it here.</div>
          <div class=\"resource-editor\">
            <label class=\"label\" for=\"memory-editor-title\">Memory editor</label>
            <input id=\"memory-editor-title\" type=\"text\" placeholder=\"Memory title\">
            <textarea id=\"memory-editor-content\" placeholder=\"Memory content\"></textarea>
            <select id=\"memory-editor-scope\">
              <option value=\"user\">User</option>
              <option value=\"project\">Project</option>
              <option value=\"global\">Global</option>
            </select>
            <div class=\"toolbar\">
              <button id=\"memory-save\" class=\"secondary\" type=\"button\">Save</button>
              <button id=\"memory-cancel\" class=\"secondary\" type=\"button\">Cancel</button>
            </div>
            <div class=\"hint\" id=\"memory-editor-hint\">Create or edit a memory entry without dialogs.</div>
          </div>
        </div>
        <div class=\"resource-controls\">
          <label class=\"label\">Notes</label>
          <div class=\"toolbar\">
            <button id=\"new-note\" class=\"secondary\" type=\"button\">New</button>
            <button id=\"edit-note\" class=\"secondary\" type=\"button\">Edit</button>
            <button id=\"delete-note\" class=\"danger\" type=\"button\">Delete</button>
            <button id=\"refresh-notes\" class=\"secondary\" type=\"button\">Refresh</button>
            <button id=\"notes-use\" class=\"secondary\" type=\"button\">Use in prompt</button>
          </div>
          <div id=\"note-chips\" class=\"stack\"></div>
          <div id=\"note-preview\" class=\"resource-preview muted\">Select a note to preview it here.</div>
          <div class=\"resource-editor\">
            <label class=\"label\" for=\"note-editor-title\">Note editor</label>
            <input id=\"note-editor-title\" type=\"text\" placeholder=\"Note title\">
            <textarea id=\"note-editor-body\" placeholder=\"Note body\"></textarea>
            <div class=\"toolbar\">
              <button id=\"note-save\" class=\"secondary\" type=\"button\">Save</button>
              <button id=\"note-cancel\" class=\"secondary\" type=\"button\">Cancel</button>
            </div>
            <div class=\"hint\" id=\"note-editor-hint\">Create or edit a note without dialogs.</div>
          </div>
        </div>
        <div class=\"resource-controls\">
          <label class=\"label\">Artifacts</label>
          <div class=\"toolbar\">
            <button id=\"new-artifact\" class=\"secondary\" type=\"button\">New</button>
            <button id=\"edit-artifact\" class=\"secondary\" type=\"button\">Edit</button>
            <button id=\"delete-artifact\" class=\"danger\" type=\"button\">Delete</button>
            <button id=\"refresh-artifacts\" class=\"secondary\" type=\"button\">Refresh</button>
            <button id=\"artifact-use\" class=\"secondary\" type=\"button\">Use in prompt</button>
          </div>
          <div id=\"artifact-chips\" class=\"stack\"></div>
          <div id=\"artifact-preview\" class=\"resource-preview muted\">Select an artifact to preview it here.</div>
          <div class=\"resource-editor\">
            <label class=\"label\" for=\"artifact-editor-title\">Artifact editor</label>
            <input id=\"artifact-editor-title\" type=\"text\" placeholder=\"Artifact title\">
            <textarea id=\"artifact-editor-content\" placeholder=\"Artifact content\"></textarea>
            <input id=\"artifact-editor-kind\" type=\"text\" placeholder=\"Kind\">
            <input id=\"artifact-editor-tags\" type=\"text\" placeholder=\"Tags, comma-separated\">
            <div class=\"toolbar\">
              <button id=\"artifact-save\" class=\"secondary\" type=\"button\">Save</button>
              <button id=\"artifact-cancel\" class=\"secondary\" type=\"button\">Cancel</button>
            </div>
            <div class=\"hint\" id=\"artifact-editor-hint\">Create or edit an artifact without dialogs.</div>
          </div>
        </div>
        <div class=\"resource-controls\">
          <label class=\"label\">Tools</label>
          <div class=\"toolbar\">
            <button id=\"new-tool\" class=\"secondary\" type=\"button\">New</button>
            <button id=\"edit-tool\" class=\"secondary\" type=\"button\">Edit</button>
            <button id=\"delete-tool\" class=\"danger\" type=\"button\">Delete</button>
            <button id=\"refresh-tools\" class=\"secondary\" type=\"button\">Refresh</button>
          </div>
          <div id=\"tool-chips\" class=\"stack\"></div>
          <div id=\"tool-preview\" class=\"resource-preview muted\">Select a tool server to preview it here.</div>
          <div class=\"resource-editor\">
            <label class=\"label\" for=\"tool-editor-name\">Tool server editor</label>
            <input id=\"tool-editor-name\" type=\"text\" placeholder=\"Tool server name\">
            <input id=\"tool-editor-endpoint\" type=\"text\" placeholder=\"Endpoint or URL\">
            <select id=\"tool-editor-type\">
              <option value=\"mcp\">MCP</option>
              <option value=\"openai\">OpenAI compatible</option>
              <option value=\"custom\">Custom</option>
            </select>
            <textarea id=\"tool-editor-description\" placeholder=\"Description\"></textarea>
            <input id=\"tool-editor-auth\" type=\"text\" placeholder=\"Auth JSON or token\">
            <div class=\"toolbar\">
              <button id=\"tool-save\" class=\"secondary\" type=\"button\">Save</button>
              <button id=\"tool-cancel\" class=\"secondary\" type=\"button\">Cancel</button>
            </div>
            <div class=\"hint\" id=\"tool-editor-hint\">Create or edit a tool server without dialogs.</div>
          </div>
        </div>
        <div class=\"resource-controls\">
          <label class=\"label\">Webhooks</label>
          <div class=\"toolbar\">
            <button id=\"new-webhook\" class=\"secondary\" type=\"button\">New</button>
            <button id=\"edit-webhook\" class=\"secondary\" type=\"button\">Edit</button>
            <button id=\"delete-webhook\" class=\"danger\" type=\"button\">Delete</button>
            <button id=\"refresh-webhooks\" class=\"secondary\" type=\"button\">Refresh</button>
          </div>
          <div id=\"webhook-chips\" class=\"stack\"></div>
          <div id=\"webhook-preview\" class=\"resource-preview muted\">Select a webhook to preview it here.</div>
          <div class=\"resource-editor\">
            <label class=\"label\" for=\"webhook-editor-name\">Webhook editor</label>
            <input id=\"webhook-editor-name\" type=\"text\" placeholder=\"Webhook name\">
            <input id=\"webhook-editor-url\" type=\"text\" placeholder=\"Webhook URL\">
            <input id=\"webhook-editor-events\" type=\"text\" placeholder=\"Events, comma-separated\">
            <textarea id=\"webhook-editor-description\" placeholder=\"Description\"></textarea>
            <input id=\"webhook-editor-secret\" type=\"text\" placeholder=\"Secret\">
            <div class=\"toolbar\">
              <button id=\"webhook-save\" class=\"secondary\" type=\"button\">Save</button>
              <button id=\"webhook-cancel\" class=\"secondary\" type=\"button\">Cancel</button>
            </div>
            <div class=\"hint\" id=\"webhook-editor-hint\">Create or edit a webhook without dialogs.</div>
          </div>
        </div>
        <div>
          <label class=\"label\" for=\"conversation-title\">Conversation</label>
          <input id=\"conversation-title\" type=\"text\" placeholder=\"Untitled conversation\">
        </div>
        <div>
          <label class=\"label\" for=\"folder-select\">Workspace</label>
          <select id=\"folder-select\"></select>
          <div class=\"template-creator\">
            <input id=\"folder-name\" type=\"text\" placeholder=\"New workspace name\">
            <button id=\"create-folder\" class=\"secondary\" type=\"button\">Create</button>
          </div>
          <div class=\"chips\" id=\"folder-chips\"></div>
        </div>
        <div>
          <label class=\"label\" for=\"conversation-search\">Search chats</label>
          <input id=\"conversation-search\" type=\"search\" placeholder=\"Find a conversation\">
        </div>
        <div>
          <label class=\"label\" for=\"message-search\">Find in chat</label>
          <div class=\"template-creator\">
            <input id=\"message-search\" type=\"search\" placeholder=\"Search transcript\">
            <button id=\"message-search-prev\" class=\"secondary\" type=\"button\">Prev</button>
            <button id=\"message-search-next\" class=\"secondary\" type=\"button\">Next</button>
          </div>
          <div class=\"hint\" id=\"message-search-meta\">No transcript search.</div>
        </div>
        <div>
          <label class=\"label\" for=\"system-prompt\">System prompt</label>
          <textarea id=\"system-prompt\" placeholder=\"Optional system prompt\"></textarea>
        </div>
        <div>
          <label class=\"label\" for=\"template-name\">Prompt templates</label>
          <div class=\"hint\">Pick a starter, save your own templates, or load a prompt directly into the system prompt.</div>
          <div class=\"template-drawer-toggle\">
            <button id=\"open-template-drawer\" class=\"secondary\" type=\"button\">Open template gallery</button>
            <button id=\"copy-system-prompt\" class=\"secondary\" type=\"button\">Copy system prompt</button>
          </div>
          <div class=\"template-creator\">
            <input id=\"template-name\" type=\"text\" placeholder=\"Template name\">
            <button id=\"save-template\" class=\"secondary\" type=\"button\">Save</button>
            <button id=\"reset-template\" class=\"secondary\" type=\"button\">New</button>
          </div>
          <div class=\"hint\">Quick access uses a compact strip. The gallery adds search, categories, compare, and copy actions.</div>
          <div id=\"template-chips\" class=\"template-library\"></div>
        </div>
        <div>
          <label class=\"label\" for=\"file-select\">Attached files</label>
          <div class=\"template-creator\">
            <input id=\"file-import-file\" type=\"file\" accept=\"application/json,.json\">
            <button id=\"file-import\" class=\"secondary\" type=\"button\">Import</button>
            <button id=\"file-export\" class=\"secondary\" type=\"button\">Export</button>
          </div>
          <div class=\"template-creator\">
            <input id=\"file-upload\" type=\"file\" multiple>
            <button id=\"upload-files\" class=\"secondary\" type=\"button\">Upload files</button>
            <button id=\"clear-file-attachments\" class=\"secondary\" type=\"button\">Clear attachments</button>
          </div>
          <div class=\"template-creator\">
            <input id=\"file-search\" type=\"search\" placeholder=\"Search files by name, tag, path, or content\">
            <button id=\"clear-file-search\" class=\"secondary\" type=\"button\">Clear</button>
          </div>
          <div class=\"toolbar\">
            <button id=\"file-clone\" class=\"secondary\" type=\"button\">Clone</button>
          </div>
          <div class=\"hint\" id=\"selected-file-meta\">No attachments selected.</div>
          <div id=\"selected-file-chips\" class=\"chips\"></div>
          <select id=\"file-select\" multiple size=\"5\"></select>
        </div>
        <div>
          <div class=\"chips\" id=\"file-chips\"></div>
        </div>
        <div>
          <div class=\"toolbar\">
            <button id=\"new-chat\" class=\"secondary\" type=\"button\">New chat</button>
            <button id=\"clear-chat\" class=\"danger\" type=\"button\">Clear</button>
          </div>
        </div>
      </div>
      <div class=\"panel stack\">
        <div class=\"label\">Saved chats</div>
        <div class=\"template-creator\">
          <input id=\"conversation-import-file\" type=\"file\" accept=\"application/json,.json,.md,.markdown,.txt\">
          <button id=\"conversation-import\" class=\"secondary\" type=\"button\">Import</button>
          <button id=\"conversation-export\" class=\"secondary\" type=\"button\">Export</button>
        </div>
        <div class=\"toolbar\">
          <button id=\"conversation-share-md\" class=\"secondary\" type=\"button\">Share MD</button>
          <button id=\"conversation-share-html\" class=\"secondary\" type=\"button\">Share HTML</button>
          <button id=\"conversation-clone\" class=\"secondary\" type=\"button\">Clone</button>
        </div>
        <div class=\"conversation-filter\">
          <button id=\"conversation-filter-all\" class=\"secondary active\" type=\"button\">All</button>
          <button id=\"conversation-filter-pinned\" class=\"secondary\" type=\"button\">Pinned</button>
          <button id=\"conversation-filter-archived\" class=\"secondary\" type=\"button\">Archived</button>
        </div>
        <div class=\"conversations\" id=\"conversation-list\"></div>
      </div>
    </aside>
    <main class=\"main\">
      <header class=\"topbar\">
        <div class=\"topbar-head\">
          <div>
            <h2 id=\"chat-title\">New chat</h2>
            <div class=\"meta\" id=\"chat-meta\">Ready.</div>
            <div class=\"hint\" id=\"chat-usage\">Token estimate: ~0</div>
          </div>
          <div class=\"toolbar\">
            <button id=\"new-chat-header\" class=\"secondary\" type=\"button\">New chat</button>
            <button id=\"toggle-sidebar\" class=\"secondary sidebar-toggle\" type=\"button\">Collapse sidebar</button>
            <button id=\"theme-toggle\" class=\"secondary theme-toggle\" type=\"button\">Theme: Dark</button>
            <button id=\"shortcuts-help\" class=\"secondary help-toggle\" type=\"button\">Keyboard shortcuts</button>
            <button id=\"export-chat-md\" class=\"secondary\" type=\"button\">Export MD</button>
            <button id=\"export-chat-json\" class=\"secondary\" type=\"button\">Export JSON</button>
            <button id=\"export-chat-html\" class=\"secondary\" type=\"button\">Export HTML</button>
            <button id=\"export-chat-sharegpt\" class=\"secondary\" type=\"button\">ShareGPT</button>
            <button id=\"copy-chat\" class=\"secondary\" type=\"button\">Copy</button>
            <button id=\"share-chat-image\" class=\"secondary\" type=\"button\">Share Image</button>
            <button id=\"rename-chat\" class=\"secondary\" type=\"button\" title=\"Edit conversation title\">Rename</button>
            <button id=\"duplicate-chat\" class=\"secondary\" type=\"button\" title=\"Duplicate this chat\">Duplicate</button>
            <button id=\"toggle-chat-pin\" class=\"secondary\" type=\"button\" title=\"Pin or unpin this chat\">Pin</button>
            <button id=\"toggle-chat-archive\" class=\"secondary\" type=\"button\" title=\"Archive or unarchive this chat\">Archive</button>
            <button id=\"delete-chat\" class=\"danger\" type=\"button\" title=\"Delete this chat\">Delete</button>
            <button id=\"regenerate-chat\" class=\"secondary\" type=\"button\">Regenerate</button>
            <button id=\"stop-chat\" class=\"danger\" type=\"button\" disabled>Stop</button>
          </div>
        </div>
        <div class=\"session-banner\">
          <div>
            <div class=\"eyebrow\">Unified workspace</div>
            <h3>Switch between models, prompt templates, attached files, and history without leaving the chat view.</h3>
            <p>Built for full-feature sessions: compare models, shape the system prompt, reuse saved templates, and export the conversation when you're done.</p>
          </div>
        </div>
        <div class=\"status-pills\" id=\"status-pills\"></div>
        <div class=\"hint\" id=\"streaming-status\">Idle.</div>
      </header>
      <section class=\"chat\" id=\"chat\"></section>
      <button id=\"scroll-latest\" class=\"secondary scroll-latest\" type=\"button\">Latest</button>
      <section class=\"composer\">
        <form id=\"composer-form\">
          <div class=\"composer-surface\">
            <textarea id=\"prompt\" rows=\"4\" placeholder=\"Ask Qwen something...\"></textarea>
            <div class=\"composer-actions\">
              <div class=\"stack\">
                <div class=\"hint\">Enter to send, Shift+Enter for a new line, or drag/paste files here to upload.</div>
                <div class=\"hint\" id=\"voice-status\">Voice input is unavailable.</div>
              </div>
              <div class=\"toolbar\">
                <button id=\"dictate-button\" class=\"secondary voice-toggle\" type=\"button\">Dictate</button>
                <button type=\"submit\" id=\"send-button\">Send</button>
              </div>
            </div>
          </div>
          <div class=\"composer-strip\">
            <div class=\"hint\" id=\"queue-status\">No queued messages.</div>
          </div>
        </form>
      </section>
    </main>
  </div>
  <div id=\"template-drawer\" class=\"template-drawer\" aria-hidden=\"true\">
    <div class=\"template-drawer-backdrop\"></div>
    <section class=\"template-drawer-panel\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"template-drawer-title\">
      <header>
        <div>
          <h3 id=\"template-drawer-title\">Template gallery</h3>
          <p>Search starter and saved prompts, compare a template against the current system prompt, or copy a template for reuse.</p>
        </div>
        <button id=\"close-template-drawer\" class=\"secondary\" type=\"button\">Close</button>
      </header>
      <div class=\"template-drawer-tools\">
        <div class=\"template-gallery-search\">
          <input id=\"template-search\" type=\"search\" placeholder=\"Search templates by name, tag, or content\">
          <button id=\"template-gallery-clear\" class=\"secondary\" type=\"button\">Clear</button>
        </div>
        <div class=\"template-gallery-tabs\" id=\"template-gallery-tabs\"></div>
      </div>
      <div class=\"template-gallery-body\">
        <div class=\"template-gallery-list\" id=\"template-gallery-list\"></div>
        <aside class=\"template-compare\">
          <div class=\"compare-card\">
            <h4>Current system prompt</h4>
            <pre id=\"template-compare-current\">No system prompt set.</pre>
            <div class=\"actions\">
              <button id=\"template-compare-copy-current\" class=\"secondary\" type=\"button\">Copy current</button>
            </div>
          </div>
          <div class=\"compare-card\">
            <h4>Selected template compare</h4>
            <pre id=\"template-compare-selected\">Select a template to compare it here.</pre>
            <div class=\"actions\">
              <button id=\"template-compare-copy-selected\" class=\"secondary\" type=\"button\">Copy template</button>
              <button id=\"template-compare-apply-selected\" class=\"secondary\" type=\"button\">Use template</button>
            </div>
          </div>
          <div class=\"compare-card\">
            <h4>Diff summary</h4>
            <pre id=\"template-compare-diff\">Select a template to see a summary.</pre>
          </div>
        </aside>
      </div>
    </section>
  </div>
  <div id=\"file-preview-backdrop\" class=\"file-preview-backdrop\" aria-hidden=\"true\">
    <section class=\"file-preview\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"file-preview-title\">
      <header>
        <div>
          <h3 id=\"file-preview-title\">File preview</h3>
          <div class=\"meta\" id=\"file-preview-meta\"></div>
        </div>
        <button id=\"close-file-preview\" class=\"secondary\" type=\"button\">Close</button>
      </header>
      <main id=\"file-preview-body\"></main>
      <footer>
        <button id=\"copy-file-preview\" class=\"secondary\" type=\"button\">Copy content</button>
      </footer>
    </section>
  </div>
  <div id=\"shortcuts-backdrop\" class=\"shortcuts-backdrop\" aria-hidden=\"true\">
    <section class=\"shortcuts-dialog\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"shortcuts-title\">
      <header>
        <div>
          <h3 id=\"shortcuts-title\">Keyboard shortcuts</h3>
          <div class=\"meta\">Fast access to common chat actions.</div>
        </div>
        <button id=\"close-shortcuts\" class=\"secondary\" type=\"button\">Close</button>
      </header>
      <div class=\"shortcut-list\">
        <div class=\"shortcut-row\">
          <kbd>Ctrl / Cmd + K</kbd>
          <div>Focus the prompt composer.</div>
        </div>
        <div class=\"shortcut-row\">
          <kbd>Ctrl / Cmd + Shift + F</kbd>
          <div>Focus transcript search.</div>
        </div>
        <div class=\"shortcut-row\">
          <kbd>Ctrl / Cmd + /</kbd>
          <div>Open this shortcut help overlay.</div>
        </div>
        <div class=\"shortcut-row\">
          <kbd>Esc</kbd>
          <div>Close file preview, shortcut help, or cancel a focused overlay.</div>
        </div>
      </div>
    </section>
  </div>
  <script id=\"bootstrap\" type=\"application/json\">{bootstrap_json}</script>
  <script>
    const bootstrap = JSON.parse(document.getElementById('bootstrap').textContent);
    const state = {{
      conversations: bootstrap.conversations || [],
      activeId: localStorage.getItem('qwen-gen.chat.activeId') || '',
      models: bootstrap.models || [],
      promptTemplates: bootstrap.promptTemplates || [],
      folders: bootstrap.folders || [],
      knowledgeBases: bootstrap.knowledgeBases || [],
      knowledgeIndexes: bootstrap.knowledgeIndexes || [],
      selectedKnowledgeBaseId: '',
      agents: bootstrap.agents || [],
      skills: bootstrap.skills || [],
      memories: bootstrap.memories || [],
      notes: bootstrap.notes || [],
      artifacts: bootstrap.artifacts || [],
      toolServers: bootstrap.toolServers || [],
      webhooks: bootstrap.webhooks || [],
      selectedSkillId: '',
      selectedMemoryId: '',
      selectedNoteId: '',
      selectedArtifactId: '',
      selectedToolId: '',
      selectedWebhookId: '',
      kbResults: [],
      webSearchProviders: [],
      webSearchResults: [],
      files: bootstrap.files || [],
      selectedFileId: localStorage.getItem('qwen-gen.chat.fileId') || '',
      webSearchQuery: localStorage.getItem('qwen-gen.chat.webSearchQuery') || '',
      webSearchProvider: localStorage.getItem('qwen-gen.chat.webSearchProvider') || 'duckduckgo',
      webSearchFallback: localStorage.getItem('qwen-gen.chat.webSearchFallback') || '',
      webSearchEngineUrl: localStorage.getItem('qwen-gen.chat.webSearchEngineUrl') || '',
      webSearchBaseId: localStorage.getItem('qwen-gen.chat.webSearchBaseId') || '',
      webSearchName: localStorage.getItem('qwen-gen.chat.webSearchName') || '',
      webSearchDescription: localStorage.getItem('qwen-gen.chat.webSearchDescription') || '',
      webSearchSaveLimit: Number(localStorage.getItem('qwen-gen.chat.webSearchSaveLimit') || '5') || 5,
      fileSearch: localStorage.getItem('qwen-gen.chat.fileSearch') || '',
      currentModel: localStorage.getItem('qwen-gen.chat.model') || bootstrap.selectedModel || '',
      currentAgentId: localStorage.getItem('qwen-gen.chat.agentId') || '',
      compareEnabled: localStorage.getItem('qwen-gen.chat.compareEnabled') === '1',
      compareModel: localStorage.getItem('qwen-gen.chat.compareModel') || '',
      conversationFilter: localStorage.getItem('qwen-gen.chat.filter') || 'all',
      sidebarCollapsed: localStorage.getItem('qwen-gen.chat.sidebarCollapsed') !== '0',
      themeMode: localStorage.getItem('qwen-gen.chat.themeMode') || 'dark',
      templateDrawerOpen: false,
      templateSearch: localStorage.getItem('qwen-gen.chat.templateSearch') || '',
      templateFilter: localStorage.getItem('qwen-gen.chat.templateFilter') || 'all',
      templateCompareId: localStorage.getItem('qwen-gen.chat.templateCompareId') || '',
      voiceListening: false,
      voiceRecognitionSupported: Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
      messageSearchIndex: 0,
    }};
    const els = {{
      app: document.getElementById('app'),
      modelSelect: document.getElementById('model-select'),
      toggleSidebar: document.getElementById('toggle-sidebar'),
      themeToggle: document.getElementById('theme-toggle'),
      newChatHeader: document.getElementById('new-chat-header'),
      dictateButton: document.getElementById('dictate-button'),
      compareToggle: document.getElementById('compare-model-toggle'),
      compareModelSelect: document.getElementById('compare-model-select'),
      addProviderPresets: document.getElementById('add-provider-presets'),
      refreshProviders: document.getElementById('refresh-providers'),
      providerChips: document.getElementById('provider-chips'),
      kbQuery: document.getElementById('kb-query'),
      kbRunQuery: document.getElementById('kb-run-query'),
      newKb: document.getElementById('new-kb'),
      editKb: document.getElementById('edit-kb'),
      deleteKb: document.getElementById('delete-kb'),
      refreshKb: document.getElementById('refresh-kb'),
      addKb: document.getElementById('add-kb'),
      kbImportFile: document.getElementById('kb-import-file'),
      kbImport: document.getElementById('kb-import'),
      kbExport: document.getElementById('kb-export'),
      kbOutputDir: document.getElementById('kb-output-dir'),
      kbWatchIterations: document.getElementById('kb-watch-iterations'),
      kbWatchInterval: document.getElementById('kb-watch-interval'),
      kbSync: document.getElementById('kb-sync'),
      kbWatch: document.getElementById('kb-watch'),
      kbChips: document.getElementById('kb-chips'),
      kbPreview: document.getElementById('kb-preview'),
      kbEditorName: document.getElementById('kb-editor-name'),
      kbEditorSourceDir: document.getElementById('kb-editor-source-dir'),
      kbEditorDescription: document.getElementById('kb-editor-description'),
      kbEditorTags: document.getElementById('kb-editor-tags'),
      kbSave: document.getElementById('kb-save'),
      kbCancel: document.getElementById('kb-cancel'),
      kbEditorHint: document.getElementById('kb-editor-hint'),
      kbResults: document.getElementById('kb-results'),
      webSearchQuery: document.getElementById('web-search-query'),
      webSearchRun: document.getElementById('web-search-run'),
      webSearchProvider: document.getElementById('web-search-provider'),
      webSearchFallback: document.getElementById('web-search-fallback'),
      webSearchEngineUrl: document.getElementById('web-search-engine-url'),
      webSearchApiKey: document.getElementById('web-search-api-key'),
      webSearchBaseId: document.getElementById('web-search-base-id'),
      webSearchName: document.getElementById('web-search-name'),
      webSearchDescription: document.getElementById('web-search-description'),
      webSearchSaveLimit: document.getElementById('web-search-save-limit'),
      webSearchSave: document.getElementById('web-search-save'),
      webSearchClear: document.getElementById('web-search-clear'),
      webSearchResults: document.getElementById('web-search-results'),
      conversationImportFile: document.getElementById('conversation-import-file'),
      conversationImport: document.getElementById('conversation-import'),
      conversationExport: document.getElementById('conversation-export'),
      conversationShareMd: document.getElementById('conversation-share-md'),
      conversationShareHtml: document.getElementById('conversation-share-html'),
      conversationClone: document.getElementById('conversation-clone'),
      fileImportFile: document.getElementById('file-import-file'),
      fileImport: document.getElementById('file-import'),
      fileExport: document.getElementById('file-export'),
      fileClone: document.getElementById('file-clone'),
      agentImportFile: document.getElementById('agent-import-file'),
      agentImport: document.getElementById('agent-import'),
      agentExport: document.getElementById('agent-export'),
      agentShareMd: document.getElementById('agent-share-md'),
      agentShareHtml: document.getElementById('agent-share-html'),
      agentShareJson: document.getElementById('agent-share-json'),
      agentClone: document.getElementById('agent-clone'),
      fileSearch: document.getElementById('file-search'),
      clearFileSearch: document.getElementById('clear-file-search'),
      agentSelect: document.getElementById('agent-select'),
      agentApply: document.getElementById('agent-apply'),
      newAgent: document.getElementById('new-agent'),
      editAgent: document.getElementById('edit-agent'),
      deleteAgent: document.getElementById('delete-agent'),
      refreshAgents: document.getElementById('refresh-agents'),
      newAgentChat: document.getElementById('new-agent-chat'),
      agentChips: document.getElementById('agent-chips'),
      agentPreview: document.getElementById('agent-preview'),
      agentEditorName: document.getElementById('agent-editor-name'),
      agentEditorBaseModel: document.getElementById('agent-editor-base-model'),
      agentEditorFolder: document.getElementById('agent-editor-folder'),
      agentEditorDescription: document.getElementById('agent-editor-description'),
      agentEditorSystemPrompt: document.getElementById('agent-editor-system-prompt'),
      agentEditorTools: document.getElementById('agent-editor-tools'),
      agentEditorKnowledge: document.getElementById('agent-editor-knowledge'),
      agentEditorSkills: document.getElementById('agent-editor-skills'),
      agentEditorAvatar: document.getElementById('agent-editor-avatar'),
      agentEditorVoice: document.getElementById('agent-editor-voice'),
      agentEditorVisibility: document.getElementById('agent-editor-visibility'),
      agentSave: document.getElementById('agent-save'),
      agentCancel: document.getElementById('agent-cancel'),
      agentEditorHint: document.getElementById('agent-editor-hint'),
      refreshSkills: document.getElementById('refresh-skills'),
      newSkill: document.getElementById('new-skill'),
      deleteSkill: document.getElementById('delete-skill'),
      skillUse: document.getElementById('skill-use'),
      skillChips: document.getElementById('skill-chips'),
      skillPreview: document.getElementById('skill-preview'),
      editSkill: document.getElementById('edit-skill'),
      skillEditorName: document.getElementById('skill-editor-name'),
      skillEditorContent: document.getElementById('skill-editor-content'),
      skillEditorTags: document.getElementById('skill-editor-tags'),
      skillSave: document.getElementById('skill-save'),
      skillCancel: document.getElementById('skill-cancel'),
      skillEditorHint: document.getElementById('skill-editor-hint'),
      refreshMemories: document.getElementById('refresh-memories'),
      newMemory: document.getElementById('new-memory'),
      editMemory: document.getElementById('edit-memory'),
      deleteMemory: document.getElementById('delete-memory'),
      memoryUse: document.getElementById('memory-use'),
      memoryChips: document.getElementById('memory-chips'),
      memoryPreview: document.getElementById('memory-preview'),
      memoryEditorTitle: document.getElementById('memory-editor-title'),
      memoryEditorContent: document.getElementById('memory-editor-content'),
      memoryEditorScope: document.getElementById('memory-editor-scope'),
      memorySave: document.getElementById('memory-save'),
      memoryCancel: document.getElementById('memory-cancel'),
      memoryEditorHint: document.getElementById('memory-editor-hint'),
      refreshNotes: document.getElementById('refresh-notes'),
      newNote: document.getElementById('new-note'),
      editNote: document.getElementById('edit-note'),
      deleteNote: document.getElementById('delete-note'),
      notesUse: document.getElementById('notes-use'),
      noteChips: document.getElementById('note-chips'),
      notePreview: document.getElementById('note-preview'),
      noteEditorTitle: document.getElementById('note-editor-title'),
      noteEditorBody: document.getElementById('note-editor-body'),
      noteSave: document.getElementById('note-save'),
      noteCancel: document.getElementById('note-cancel'),
      noteEditorHint: document.getElementById('note-editor-hint'),
      refreshArtifacts: document.getElementById('refresh-artifacts'),
      newArtifact: document.getElementById('new-artifact'),
      editArtifact: document.getElementById('edit-artifact'),
      deleteArtifact: document.getElementById('delete-artifact'),
      artifactUse: document.getElementById('artifact-use'),
      artifactChips: document.getElementById('artifact-chips'),
      artifactPreview: document.getElementById('artifact-preview'),
      artifactEditorTitle: document.getElementById('artifact-editor-title'),
      artifactEditorContent: document.getElementById('artifact-editor-content'),
      artifactEditorKind: document.getElementById('artifact-editor-kind'),
      artifactEditorTags: document.getElementById('artifact-editor-tags'),
      artifactSave: document.getElementById('artifact-save'),
      artifactCancel: document.getElementById('artifact-cancel'),
      artifactEditorHint: document.getElementById('artifact-editor-hint'),
      refreshTools: document.getElementById('refresh-tools'),
      newTool: document.getElementById('new-tool'),
      editTool: document.getElementById('edit-tool'),
      deleteTool: document.getElementById('delete-tool'),
      toolChips: document.getElementById('tool-chips'),
      toolPreview: document.getElementById('tool-preview'),
      toolEditorName: document.getElementById('tool-editor-name'),
      toolEditorEndpoint: document.getElementById('tool-editor-endpoint'),
      toolEditorType: document.getElementById('tool-editor-type'),
      toolEditorDescription: document.getElementById('tool-editor-description'),
      toolEditorAuth: document.getElementById('tool-editor-auth'),
      toolSave: document.getElementById('tool-save'),
      toolCancel: document.getElementById('tool-cancel'),
      toolEditorHint: document.getElementById('tool-editor-hint'),
      refreshWebhooks: document.getElementById('refresh-webhooks'),
      newWebhook: document.getElementById('new-webhook'),
      editWebhook: document.getElementById('edit-webhook'),
      deleteWebhook: document.getElementById('delete-webhook'),
      webhookChips: document.getElementById('webhook-chips'),
      webhookPreview: document.getElementById('webhook-preview'),
      webhookEditorName: document.getElementById('webhook-editor-name'),
      webhookEditorUrl: document.getElementById('webhook-editor-url'),
      webhookEditorEvents: document.getElementById('webhook-editor-events'),
      webhookEditorDescription: document.getElementById('webhook-editor-description'),
      webhookEditorSecret: document.getElementById('webhook-editor-secret'),
      webhookSave: document.getElementById('webhook-save'),
      webhookCancel: document.getElementById('webhook-cancel'),
      webhookEditorHint: document.getElementById('webhook-editor-hint'),
      title: document.getElementById('chat-title'),
      meta: document.getElementById('chat-meta'),
      usage: document.getElementById('chat-usage'),
      workspaceModelCount: document.getElementById('workspace-model-count'),
      workspaceTemplateCount: document.getElementById('workspace-template-count'),
      workspaceChatCount: document.getElementById('workspace-chat-count'),
      prompt: document.getElementById('prompt'),
      systemPrompt: document.getElementById('system-prompt'),
      templateName: document.getElementById('template-name'),
      openTemplateDrawer: document.getElementById('open-template-drawer'),
      copySystemPrompt: document.getElementById('copy-system-prompt'),
      folderSelect: document.getElementById('folder-select'),
      folderName: document.getElementById('folder-name'),
      createFolder: document.getElementById('create-folder'),
      folderChips: document.getElementById('folder-chips'),
      fileSelect: document.getElementById('file-select'),
      fileUpload: document.getElementById('file-upload'),
      uploadFiles: document.getElementById('upload-files'),
      clearFileAttachments: document.getElementById('clear-file-attachments'),
      selectedFileChips: document.getElementById('selected-file-chips'),
      selectedFileMeta: document.getElementById('selected-file-meta'),
      conversationTitle: document.getElementById('conversation-title'),
      conversationSearch: document.getElementById('conversation-search'),
      conversationFilterAll: document.getElementById('conversation-filter-all'),
      conversationFilterPinned: document.getElementById('conversation-filter-pinned'),
      conversationFilterArchived: document.getElementById('conversation-filter-archived'),
      messageSearch: document.getElementById('message-search'),
      messageSearchPrev: document.getElementById('message-search-prev'),
      messageSearchNext: document.getElementById('message-search-next'),
      messageSearchMeta: document.getElementById('message-search-meta'),
      statusPills: document.getElementById('status-pills'),
      streamingStatus: document.getElementById('streaming-status'),
      chat: document.getElementById('chat'),
      scrollLatest: document.getElementById('scroll-latest'),
      conversationList: document.getElementById('conversation-list'),
      templateChips: document.getElementById('template-chips'),
      templateDrawer: document.getElementById('template-drawer'),
      closeTemplateDrawer: document.getElementById('close-template-drawer'),
      templateSearch: document.getElementById('template-search'),
      templateGalleryClear: document.getElementById('template-gallery-clear'),
      templateGalleryTabs: document.getElementById('template-gallery-tabs'),
      templateGalleryList: document.getElementById('template-gallery-list'),
      templateCompareCurrent: document.getElementById('template-compare-current'),
      templateCompareSelected: document.getElementById('template-compare-selected'),
      templateCompareDiff: document.getElementById('template-compare-diff'),
      templateCompareCopyCurrent: document.getElementById('template-compare-copy-current'),
      templateCompareCopySelected: document.getElementById('template-compare-copy-selected'),
      templateCompareApplySelected: document.getElementById('template-compare-apply-selected'),
      fileChips: document.getElementById('file-chips'),
      form: document.getElementById('composer-form'),
      composer: document.querySelector('.composer'),
      queueStatus: document.getElementById('queue-status'),
      voiceStatus: document.getElementById('voice-status'),
      filePreviewBackdrop: document.getElementById('file-preview-backdrop'),
      filePreviewTitle: document.getElementById('file-preview-title'),
      filePreviewMeta: document.getElementById('file-preview-meta'),
      filePreviewBody: document.getElementById('file-preview-body'),
      closeFilePreview: document.getElementById('close-file-preview'),
      copyFilePreview: document.getElementById('copy-file-preview'),
      shortcutsBackdrop: document.getElementById('shortcuts-backdrop'),
      shortcutsHelp: document.getElementById('shortcuts-help'),
      closeShortcuts: document.getElementById('close-shortcuts'),
      newChat: document.getElementById('new-chat'),
      clearChat: document.getElementById('clear-chat'),
      exportChatMd: document.getElementById('export-chat-md'),
      exportChatJson: document.getElementById('export-chat-json'),
      exportChatHtml: document.getElementById('export-chat-html'),
      exportChatSharegpt: document.getElementById('export-chat-sharegpt'),
      copyChat: document.getElementById('copy-chat'),
      shareChatImage: document.getElementById('share-chat-image'),
      renameChat: document.getElementById('rename-chat'),
      duplicateChat: document.getElementById('duplicate-chat'),
      toggleChatPin: document.getElementById('toggle-chat-pin'),
      toggleChatArchive: document.getElementById('toggle-chat-archive'),
      deleteChat: document.getElementById('delete-chat'),
      regenerateChat: document.getElementById('regenerate-chat'),
      stopChat: document.getElementById('stop-chat'),
      saveTemplate: document.getElementById('save-template'),
      resetTemplate: document.getElementById('reset-template'),
    }};
    let activeAbortController = null;
    let editingMessageIndex = null;
    let editingMessageDraft = '';
    let editingTemplateId = null;
    let editingAgentId = null;
    let editingSkillId = null;
    let editingMemoryId = null;
    let editingNoteId = null;
    let editingArtifactId = null;
    let editingKnowledgeBaseId = null;
    let editingToolId = null;
    let editingWebhookId = null;
    let messageSearchMatches = [];
    let pendingMessageQueue = [];
    let dragDepth = 0;
    let pasteDepth = 0;
    let previewFile = null;
    function save() {{
      localStorage.setItem('qwen-gen.chat.activeId', state.activeId || '');
      localStorage.setItem('qwen-gen.chat.model', state.currentModel || '');
      localStorage.setItem('qwen-gen.chat.agentId', state.currentAgentId || '');
      localStorage.setItem('qwen-gen.chat.fileId', state.selectedFileId || '');
      localStorage.setItem('qwen-gen.chat.compareEnabled', state.compareEnabled ? '1' : '0');
      localStorage.setItem('qwen-gen.chat.compareModel', state.compareModel || '');
      localStorage.setItem('qwen-gen.chat.filter', state.conversationFilter || 'all');
      localStorage.setItem('qwen-gen.chat.sidebarCollapsed', state.sidebarCollapsed ? '1' : '0');
      localStorage.setItem('qwen-gen.chat.themeMode', state.themeMode || 'dark');
      localStorage.setItem('qwen-gen.chat.templateSearch', state.templateSearch || '');
      localStorage.setItem('qwen-gen.chat.templateFilter', state.templateFilter || 'all');
      localStorage.setItem('qwen-gen.chat.templateCompareId', state.templateCompareId || '');
      localStorage.setItem('qwen-gen.chat.webSearchQuery', state.webSearchQuery || '');
      localStorage.setItem('qwen-gen.chat.webSearchProvider', state.webSearchProvider || 'duckduckgo');
      localStorage.setItem('qwen-gen.chat.webSearchFallback', state.webSearchFallback || '');
      localStorage.setItem('qwen-gen.chat.webSearchEngineUrl', state.webSearchEngineUrl || '');
      localStorage.setItem('qwen-gen.chat.webSearchBaseId', state.webSearchBaseId || '');
      localStorage.setItem('qwen-gen.chat.webSearchName', state.webSearchName || '');
      localStorage.setItem('qwen-gen.chat.webSearchDescription', state.webSearchDescription || '');
      localStorage.setItem('qwen-gen.chat.webSearchSaveLimit', String(state.webSearchSaveLimit || 5));
      localStorage.setItem('qwen-gen.chat.fileSearch', state.fileSearch || '');
    }}
    function setSidebarCollapsed(collapsed) {{
      state.sidebarCollapsed = Boolean(collapsed);
      els.app.classList.toggle('sidebar-collapsed', state.sidebarCollapsed);
      if (els.toggleSidebar) {{
        els.toggleSidebar.textContent = state.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar';
        els.toggleSidebar.setAttribute('aria-expanded', state.sidebarCollapsed ? 'false' : 'true');
      }}
      save();
    }}
    function applyTheme() {{
      const theme = state.themeMode === 'light' ? 'light' : 'dark';
      state.themeMode = theme;
      document.body.dataset.theme = theme;
      if (els.themeToggle) {{
        els.themeToggle.textContent = theme === 'light' ? 'Theme: Light' : 'Theme: Dark';
      }}
      const themeColor = document.getElementById('theme-color');
      if (themeColor) {{
        themeColor.setAttribute('content', theme === 'light' ? '#f4f7fb' : '#0b1020');
      }}
    }}
    function toggleTheme() {{
      state.themeMode = state.themeMode === 'light' ? 'dark' : 'light';
      applyTheme();
      save();
    }}
    function renderVoiceControls() {{
      if (!els.dictateButton || !els.voiceStatus) return;
      els.dictateButton.disabled = !state.voiceRecognitionSupported;
      els.dictateButton.textContent = state.voiceListening ? 'Stop dictation' : 'Dictate';
      els.voiceStatus.textContent = state.voiceRecognitionSupported
        ? (state.voiceListening
          ? 'Listening for speech input.'
          : 'Voice input is ready.')
        : 'Voice input is unavailable in this browser.';
    }}
    function ensureVoiceRecognition() {{
      if (window.__qwenVoiceRecognition) return window.__qwenVoiceRecognition;
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) return null;
      const recognition = new SpeechRecognition();
      recognition.interimResults = true;
      recognition.continuous = false;
      recognition.lang = navigator.language || 'en-US';
      recognition.onstart = () => {{
        state.voiceListening = true;
        renderVoiceControls();
      }};
      recognition.onresult = (event) => {{
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i += 1) {{
          const result = event.results[i];
          if (result && result[0] && result[0].transcript) {{
            transcript += result[0].transcript;
          }}
        }}
        transcript = transcript.trim();
        if (transcript) {{
          const current = els.prompt.value || '';
          els.prompt.value = current ? `${{current.trimEnd()}} ${{transcript}}` : transcript;
          els.prompt.focus();
          els.prompt.selectionStart = els.prompt.selectionEnd = els.prompt.value.length;
        }}
      }};
      recognition.onerror = () => {{
        state.voiceListening = false;
        renderVoiceControls();
      }};
      recognition.onend = () => {{
        state.voiceListening = false;
        renderVoiceControls();
      }};
      window.__qwenVoiceRecognition = recognition;
      return recognition;
    }}
    function toggleVoiceInput() {{
      if (!state.voiceRecognitionSupported) {{
        window.alert('Voice input is not supported in this browser.');
        return;
      }}
      const recognition = ensureVoiceRecognition();
      if (!recognition) {{
        window.alert('Voice input is not supported in this browser.');
        return;
      }}
      if (state.voiceListening) {{
        try {{
          recognition.stop();
        }} catch (err) {{}}
        state.voiceListening = false;
        renderVoiceControls();
        return;
      }}
      try {{
        recognition.start();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }}
    function speakMessage(text) {{
      if (!('speechSynthesis' in window)) {{
        window.alert('Read aloud is not supported in this browser.');
        return;
      }}
      const content = String(text || '').trim();
      if (!content) return;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(content);
      utterance.lang = navigator.language || 'en-US';
      window.speechSynthesis.speak(utterance);
    }}
    function setStreaming(active) {{
      els.stopChat.disabled = !active;
      els.regenerateChat.disabled = active || !activeConversation();
      els.exportChatMd.disabled = active || !activeConversation();
      els.exportChatJson.disabled = active || !activeConversation();
      els.exportChatSharegpt.disabled = active || !activeConversation();
      els.shareChatImage.disabled = active || !activeConversation();
      if (els.streamingStatus) {{
        els.streamingStatus.textContent = active ? 'Generating response live.' : 'Idle.';
      }}
    }}
    function updateQueueStatus() {{
      if (!els.queueStatus) return;
      if (!pendingMessageQueue.length) {{
        els.queueStatus.textContent = 'No queued messages.';
        return;
      }}
      const queuedModels = new Set(
        pendingMessageQueue
          .map((item) => item.options && item.options.model ? item.options.model : '')
          .filter(Boolean)
      );
      const queueModels = queuedModels.size ? ` · ${{queuedModels.size}} model(s)` : '';
      els.queueStatus.textContent = `${{pendingMessageQueue.length}} queued message(s)${{queueModels}}`;
    }}
    function snapshotSendOptions() {{
      return {{
        model: els.modelSelect.value || state.currentModel || bootstrap.selectedModel || '',
        systemPrompt: els.systemPrompt.value.trim(),
        files: selectedFiles(),
        compareEnabled: !!els.compareToggle.checked,
        compareModel: els.compareModelSelect.value || '',
      }};
    }}
    async function saveConversation(convo) {{
      try {{
        const response = await fetch('/api/ai/conversations', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(convo),
        }});
        if (!response.ok) {{
          return null;
        }}
        const data = await response.json();
        return data.data || null;
      }} catch (err) {{
        return null;
      }}
    }}
    async function saveFolder(folder) {{
      try {{
        const response = await fetch('/api/ai/folders', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(folder),
        }});
        if (!response.ok) {{
          return null;
        }}
        const data = await response.json();
        return data.data || null;
      }} catch (err) {{
        return null;
      }}
    }}
    async function refreshProviders() {{
      try {{
        const response = await fetch('/api/ai/models');
        if (!response.ok) return;
        const data = await response.json();
        state.models = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function addProviderPresets() {{
      const response = await fetch('/api/ai/providers', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'add-presets' }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Provider preset update failed');
      }}
      await refreshProviders();
      renderAll();
    }}
    async function deleteProviderModel(modelId) {{
      const response = await fetch('/api/ai/providers', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete-model', id: modelId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Provider delete failed');
      }}
      await refreshProviders();
      renderAll();
    }}
    async function refreshKnowledgeBases() {{
      try {{
        const response = await fetch('/api/ai/kb');
        if (!response.ok) return;
        const data = await response.json();
        state.knowledgeBases = Array.isArray(data.data && data.data.knowledgeBases) ? data.data.knowledgeBases : [];
        state.knowledgeIndexes = Array.isArray(data.data && data.data.knowledgeIndexes) ? data.data.knowledgeIndexes : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function refreshConversations() {{
      try {{
        const response = await fetch('/api/ai/conversations');
        if (!response.ok) return;
        const data = await response.json();
        state.conversations = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function saveKnowledgeBase(base) {{
      const response = await fetch('/api/ai/kb', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(base),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Knowledge base save failed');
      }}
      const data = await response.json();
      await refreshKnowledgeBases();
      renderAll();
      return data.data || null;
    }}
    function currentConversation() {{
      return activeConversation();
    }}
    function currentAgentPreset() {{
      return state.agents.find((item) => String(item.id || '') === String(els.agentSelect.value || '')) || null;
    }}
    function conversationsExportPayload() {{
      return JSON.stringify({{ conversations: state.conversations || [] }}, null, 2) + '\\n';
    }}
    function agentsExportPayload() {{
      return JSON.stringify({{ agents: state.agents || [] }}, null, 2) + '\\n';
    }}
    async function importConversationsFromFile() {{
      const file = els.conversationImportFile && els.conversationImportFile.files ? els.conversationImportFile.files[0] : null;
      if (!file) {{
        window.alert('Select a conversation JSON file first.');
        return;
      }}
      const content = await file.text();
      const response = await fetch('/api/ai/conversations', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'import', content }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Conversation import failed');
      }}
      await refreshConversations();
      renderAll();
    }}
    async function importAgentsFromFile() {{
      const file = els.agentImportFile && els.agentImportFile.files ? els.agentImportFile.files[0] : null;
      if (!file) {{
        window.alert('Select an agent JSON file first.');
        return;
      }}
      const content = await file.text();
      const response = await fetch('/api/ai/agents', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'import', content }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Agent import failed');
      }}
      await refreshAgents();
      renderAll();
    }}
    async function exportConversationsToFile() {{
      const response = await fetch('/api/ai/conversations', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'export' }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Conversation export failed');
      }}
      const data = await response.json();
      downloadText('conversations.json', String(data.data && data.data.content || conversationsExportPayload()), 'application/json;charset=utf-8');
    }}
    async function exportAgentsToFile() {{
      const response = await fetch('/api/ai/agents', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'export' }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Agent export failed');
      }}
      const data = await response.json();
      downloadText('agents.json', String(data.data && data.data.content || agentsExportPayload()), 'application/json;charset=utf-8');
    }}
    async function shareConversation(format = 'md') {{
      const convo = currentConversation();
      if (!convo) {{
        window.alert('Select a conversation first.');
        return;
      }}
      const response = await fetch('/api/ai/conversations', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'share', id: convo.id, format }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Conversation share failed');
      }}
      const data = await response.json();
      const ext = format === 'html' ? 'html' : 'md';
      downloadText(`${{convo.id}}.${{ext}}`, String(data.data && data.data.content || ''), format === 'html' ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8');
    }}
    async function shareAgent(format = 'md') {{
      const agent = currentAgentPreset();
      if (!agent) {{
        window.alert('Select an agent first.');
        return;
      }}
      const response = await fetch('/api/ai/agents', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'share', id: agent.id, format }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Agent share failed');
      }}
      const data = await response.json();
      const ext = format === 'html' ? 'html' : format === 'json' ? 'json' : 'md';
      downloadText(`${{agent.id}}.${{ext}}`, String(data.data && data.data.content || ''), format === 'html' ? 'text/html;charset=utf-8' : 'text/plain;charset=utf-8');
    }}
    async function cloneConversationFromSelection() {{
      const convo = currentConversation();
      if (!convo) {{
        window.alert('Select a conversation first.');
        return;
      }}
      const response = await fetch('/api/ai/conversations', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'clone', id: convo.id }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Conversation clone failed');
      }}
      await refreshConversations();
      renderAll();
    }}
    async function cloneAgentFromSelection() {{
      const agent = currentAgentPreset();
      if (!agent) {{
        window.alert('Select an agent first.');
        return;
      }}
      const response = await fetch('/api/ai/agents', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'clone', id: agent.id }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Agent clone failed');
      }}
      await refreshAgents();
      renderAll();
    }}
    function knowledgeBasesExportPayload() {{
      return JSON.stringify(
        {{
          knowledgeBases: state.knowledgeBases || [],
          knowledgeIndexes: state.knowledgeIndexes || [],
        }},
        null,
        2,
      ) + '\\n';
    }}
    async function importKnowledgeBasesFromFile() {{
      const file = els.kbImportFile && els.kbImportFile.files ? els.kbImportFile.files[0] : null;
      if (!file) {{
        window.alert('Select a knowledge base JSON file first.');
        return;
      }}
      let content = '';
      try {{
        content = await file.text();
      }} catch (err) {{
        throw new Error('Unable to read the selected file.');
      }}
      const response = await fetch('/api/ai/kb', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'import', content }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Knowledge base import failed');
      }}
      await refreshKnowledgeBases();
      renderAll();
    }}
    async function syncKnowledgeBases(action = 'sync') {{
      const selected = (state.knowledgeBases || []).find((item) => String(item.id || '') === String(state.selectedKnowledgeBaseId || '')) || null;
      const baseId = selected && selected.id ? String(selected.id) : '';
      const response = await fetch('/api/ai/kb', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          action,
          baseId,
          outputDir: (els.kbOutputDir.value || '').trim(),
          iterations: Number(els.kbWatchIterations.value || '1') || 1,
          interval: Number(els.kbWatchInterval.value || '0') || 0,
        }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Knowledge base sync failed');
      }}
      const data = await response.json();
      await refreshKnowledgeBases();
      renderAll();
      return data.data || null;
    }}
    async function refreshKnowledgeBaseIndex(baseId) {{
      const response = await fetch('/api/ai/kb', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          action: 'refresh',
          baseId,
        }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Knowledge base refresh failed');
      }}
      const data = await response.json();
      await refreshKnowledgeBases();
      renderAll();
      return data.data || null;
    }}
    async function deleteKnowledgeBase(baseId) {{
      const response = await fetch('/api/ai/kb', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: baseId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Knowledge base delete failed');
      }}
      state.selectedKnowledgeBaseId = '';
      await refreshKnowledgeBases();
      renderAll();
    }}
    async function refreshAgents() {{
      try {{
        const response = await fetch('/api/ai/agents');
        if (!response.ok) return;
        const data = await response.json();
        state.agents = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function saveAgent(agent) {{
      const response = await fetch('/api/ai/agents', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(agent),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Agent save failed');
      }}
      const data = await response.json();
      await refreshAgents();
      renderAll();
      return data.data || null;
    }}
    async function deleteAgent(agentId) {{
      const response = await fetch('/api/ai/agents', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: agentId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Agent delete failed');
      }}
      state.currentAgentId = '';
      await refreshAgents();
      renderAll();
    }}
    async function refreshSkills() {{
      try {{
        const response = await fetch('/api/ai/skills');
        if (!response.ok) return;
        const data = await response.json();
        state.skills = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function saveSkill(skill) {{
      const response = await fetch('/api/ai/skills', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(skill),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Skill save failed');
      }}
      const data = await response.json();
      await refreshSkills();
      renderAll();
      return data.data || null;
    }}
    async function refreshMemories() {{
      try {{
        const response = await fetch('/api/ai/memories');
        if (!response.ok) return;
        const data = await response.json();
        state.memories = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function deleteSkill(skillId) {{
      const response = await fetch('/api/ai/skills', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: skillId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Skill delete failed');
      }}
      state.selectedSkillId = '';
      await refreshSkills();
      renderAll();
    }}
    async function saveMemory(memory) {{
      const response = await fetch('/api/ai/memories', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(memory),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Memory save failed');
      }}
      const data = await response.json();
      await refreshMemories();
      renderAll();
      return data.data || null;
    }}
    async function deleteMemory(memoryId) {{
      const response = await fetch('/api/ai/memories', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: memoryId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Memory delete failed');
      }}
      state.selectedMemoryId = '';
      await refreshMemories();
      renderAll();
    }}
    function activeAgent() {{
      const convo = activeConversation();
      const agentId = convo && convo.agentId ? String(convo.agentId) : state.currentAgentId;
      return state.agents.find((item) => String(item.id || '') === String(agentId || '')) || null;
    }}
    function listToText(values) {{
      if (!Array.isArray(values) || !values.length) return '';
      return values.map((value) => String(value).trim()).filter(Boolean).join(', ');
    }}
    function textToList(value) {{
      return String(value || '')
        .split(/[\n,]/)
        .map((entry) => entry.trim())
        .filter(Boolean);
    }}
    function agentSummary(agent) {{
      if (!agent) return '';
      const parts = [];
      if (agent.baseModel) parts.push(agent.baseModel);
      if (agent.folderId) parts.push(`workspace: ${{folderLabel(agent.folderId)}}`);
      if (Array.isArray(agent.tools) && agent.tools.length) parts.push(`${{agent.tools.length}} tool(s)`);
      if (Array.isArray(agent.knowledge) && agent.knowledge.length) parts.push(`${{agent.knowledge.length}} knowledge`);
      if (Array.isArray(agent.skills) && agent.skills.length) parts.push(`${{agent.skills.length}} skill(s)`);
      return parts.join(' · ');
    }}
    function agentPromptValues(agent) {{
      const convo = activeConversation();
      return {{
        name: agent?.name || (els.conversationTitle.value || els.title.textContent || 'Agent').trim() || 'Agent',
        baseModel: agent?.baseModel || els.modelSelect.value || state.currentModel || bootstrap.selectedModel || '',
        systemPrompt: agent?.systemPrompt || els.systemPrompt.value || els.prompt.value || '',
        description: agent?.description || '',
        folderId: agent?.folderId || (convo && convo.folderId) || els.folderSelect.value || '',
        tools: Array.isArray(agent?.tools) ? agent.tools.slice() : [],
        knowledge: Array.isArray(agent?.knowledge) ? agent.knowledge.slice() : [],
        skills: Array.isArray(agent?.skills) ? agent.skills.slice() : [],
        avatar: agent?.avatar || '',
        voice: agent?.voice || '',
        visibility: agent?.visibility || '',
      }};
    }}
    function agentEditorValues() {{
      const existing = editingAgentId ? (state.agents || []).find((item) => String(item.id || '') === String(editingAgentId || '')) || null : null;
      const fallback = agentPromptValues(existing);
      return {{
        ...(existing || {{}}),
        id: existing?.id || editingAgentId || undefined,
        name: (els.agentEditorName.value || fallback.name || '').trim(),
        baseModel: (els.agentEditorBaseModel.value || fallback.baseModel || '').trim(),
        systemPrompt: els.agentEditorSystemPrompt.value || fallback.systemPrompt || '',
        description: (els.agentEditorDescription.value || fallback.description || '').trim(),
        folderId: els.agentEditorFolder.value || fallback.folderId || '',
        tools: textToList(els.agentEditorTools.value || listToText(fallback.tools || [])),
        knowledge: textToList(els.agentEditorKnowledge.value || listToText(fallback.knowledge || [])),
        skills: textToList(els.agentEditorSkills.value || listToText(fallback.skills || [])),
        avatar: (els.agentEditorAvatar.value || fallback.avatar || '').trim(),
        voice: (els.agentEditorVoice.value || fallback.voice || '').trim(),
        visibility: els.agentEditorVisibility.value || fallback.visibility || '',
      }};
    }}
    function renderAgentEditor(selectedFolderId = '') {{
      els.agentEditorFolder.innerHTML = '';
      const none = document.createElement('option');
      none.value = '';
      none.textContent = 'No workspace';
      els.agentEditorFolder.appendChild(none);
      for (const folder of state.folders || []) {{
        const option = document.createElement('option');
        option.value = folder.id || '';
        option.textContent = `${{folder.name || folder.id}}${{folder.parentId ? ` · ${{folder.parentId}}` : ''}}`;
        els.agentEditorFolder.appendChild(option);
      }}
      els.agentEditorFolder.value = selectedFolderId || '';
    }}
    function openAgentEditor(agent) {{
      editingAgentId = agent && agent.id ? agent.id : null;
      const values = agentPromptValues(agent || null);
      els.agentEditorName.value = values.name || '';
      els.agentEditorBaseModel.value = values.baseModel || '';
      els.agentEditorDescription.value = values.description || '';
      els.agentEditorSystemPrompt.value = values.systemPrompt || '';
      els.agentEditorTools.value = listToText(values.tools || []);
      els.agentEditorKnowledge.value = listToText(values.knowledge || []);
      els.agentEditorSkills.value = listToText(values.skills || []);
      els.agentEditorAvatar.value = values.avatar || '';
      els.agentEditorVoice.value = values.voice || '';
      els.agentEditorVisibility.value = values.visibility || '';
      renderAgentEditor(values.folderId || '');
      els.agentEditorHint.textContent = agent
        ? `Editing ${{agent.name || agent.id}}.`
        : 'Create a new agent preset without leaving the page.';
    }}
    async function saveAgentEditor() {{
      const values = agentEditorValues();
      if (!values.name) {{
        throw new Error('Agent name is required');
      }}
      if (!values.baseModel) {{
        throw new Error('Base model is required');
      }}
      const existing = editingAgentId ? (state.agents || []).find((item) => String(item.id || '') === String(editingAgentId || '')) || {{}} : {{ tools: [], knowledge: [], skills: [] }};
      const saved = await saveAgent({{
        ...existing,
        ...values,
        id: editingAgentId || values.id,
      }});
      if (saved && saved.id) {{
        state.currentAgentId = saved.id;
        els.agentSelect.value = saved.id;
        editingAgentId = saved.id;
        els.agentEditorHint.textContent = `Saved ${{saved.name || saved.id}}.`;
      }}
    }}
    function clearAgentEditor() {{
      editingAgentId = null;
      els.agentEditorName.value = '';
      els.agentEditorBaseModel.value = '';
      els.agentEditorDescription.value = '';
      els.agentEditorSystemPrompt.value = '';
      els.agentEditorTools.value = '';
      els.agentEditorKnowledge.value = '';
      els.agentEditorSkills.value = '';
      els.agentEditorAvatar.value = '';
      els.agentEditorVoice.value = '';
      els.agentEditorVisibility.value = '';
      renderAgentEditor('');
      els.agentEditorHint.textContent = 'Create or edit an agent preset without leaving the page.';
    }}
    function renderAgents() {{
      els.agentSelect.innerHTML = '';
      els.agentChips.innerHTML = '';
      els.agentPreview.textContent = 'Select an agent to preview it here.';
      const agents = state.agents || [];
      const current = activeAgent();
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = agents.length ? 'Select an agent preset' : 'No agents registered';
      els.agentSelect.appendChild(empty);
      for (const agent of agents) {{
        const option = document.createElement('option');
        option.value = agent.id || '';
        option.textContent = `${{agent.name || agent.id}} — ${{agent.baseModel || 'model'}}`;
        els.agentSelect.appendChild(option);

        const row = document.createElement('div');
        row.className = 'agent-item';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = agent.name || agent.id;
        chip.title = [agent.description, agent.baseModel, agent.folderId ? `workspace: ${{folderLabel(agent.folderId)}}` : '', agent.systemPrompt].filter(Boolean).join(' · ');
        chip.addEventListener('click', () => {{
          els.agentSelect.value = agent.id || '';
          state.currentAgentId = agent.id || '';
          els.agentPreview.textContent = [
            agent.name || agent.id,
            agentSummary(agent),
            agent.description || '',
            agent.systemPrompt || '',
            agent.folderId ? `Workspace: ${{folderLabel(agent.folderId)}}` : '',
            Array.isArray(agent.tools) ? `Tools: ${{agent.tools.join(', ')}}` : '',
            Array.isArray(agent.knowledge) ? `Knowledge: ${{agent.knowledge.join(', ')}}` : '',
            Array.isArray(agent.skills) ? `Skills: ${{agent.skills.join(', ')}}` : '',
          ].filter(Boolean).join('\\n\\n');
          renderAll();
        }});
        const meta = document.createElement('span');
        meta.className = 'muted';
        meta.textContent = agentSummary(agent);
        row.appendChild(chip);
        row.appendChild(meta);
        els.agentChips.appendChild(row);
      }}
      if (current && current.id) {{
        els.agentSelect.value = current.id;
      }} else if (!els.agentSelect.value && agents.length) {{
        els.agentSelect.value = agents[0].id || '';
      }}
      state.currentAgentId = els.agentSelect.value || state.currentAgentId;
      if (current) {{
        els.agentPreview.textContent = [
          current.name || current.id,
          agentSummary(current),
          current.description || '',
          current.systemPrompt || '',
          current.folderId ? `Workspace: ${{folderLabel(current.folderId)}}` : '',
          Array.isArray(current.tools) ? `Tools: ${{current.tools.join(', ')}}` : '',
          Array.isArray(current.knowledge) ? `Knowledge: ${{current.knowledge.join(', ')}}` : '',
          Array.isArray(current.skills) ? `Skills: ${{current.skills.join(', ')}}` : '',
        ].filter(Boolean).join('\\n\\n');
      }}
    }}
    function skillSummary(skill) {{
      const parts = [];
      if (Array.isArray(skill.tags) && skill.tags.length) parts.push(skill.tags.join(', '));
      if (skill.pinned) parts.push('pinned');
      if (skill.archived) parts.push('archived');
      return parts.join(' · ');
    }}
    function sharedFilename(kind, item, format) {{
      const slug = String(item?.id || item?.name || kind || 'item')
        .replace(/[^a-z0-9._-]+/gi, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '') || kind || 'item';
      const ext = format === 'html' ? 'html' : format === 'json' ? 'json' : 'md';
      return `${{slug}}.${{ext}}`;
    }}
    async function shareRegistryItem(kind, id, format) {{
      const response = await fetch(`/api/ai/${{kind}}`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'share', id, format }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || `${{kind}} share failed`);
      }}
      const data = await response.json();
      const payload = data.data || {{}};
      return {{
        content: String(payload.content || ''),
        name: String(payload.name || payload.id || id || kind || 'item'),
      }};
    }}
    async function downloadSharedItem(kind, item, format) {{
      const shared = await shareRegistryItem(kind, item.id, format);
      const blob = new Blob([shared.content], {{
        type: format === 'html'
          ? 'text/html;charset=utf-8'
          : format === 'json'
            ? 'application/json;charset=utf-8'
            : 'text/markdown;charset=utf-8',
      }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = sharedFilename(kind, item, format);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }}
    function memorySummary(memory) {{
      const parts = [];
      if (memory.scope) parts.push(memory.scope);
      if (Array.isArray(memory.tags) && memory.tags.length) parts.push(memory.tags.join(', '));
      if (memory.source) parts.push(memory.source);
      return parts.join(' · ');
    }}
    function skillEditorValues() {{
      const existing = editingSkillId ? (state.skills || []).find((item) => String(item.id || '') === String(editingSkillId || '')) || null : null;
      return {{
        ...(existing || {{}}),
        name: (els.skillEditorName.value || existing?.name || '').trim(),
        content: els.skillEditorContent.value || existing?.content || '',
        tags: textToList(els.skillEditorTags.value || listToText(existing?.tags || [])),
      }};
    }}
    function openSkillEditor(skill) {{
      editingSkillId = skill && skill.id ? skill.id : null;
      els.skillEditorName.value = skill?.name || (els.conversationTitle.value || els.title.textContent || 'Skill').trim() || '';
      els.skillEditorContent.value = skill?.content || els.systemPrompt.value || els.prompt.value || '';
      els.skillEditorTags.value = listToText(skill?.tags || []);
      els.skillEditorHint.textContent = skill
        ? `Editing ${{skill.name || skill.id}}.`
        : 'Create a reusable skill without dialogs.';
    }}
    async function saveSkillEditor() {{
      const values = skillEditorValues();
      if (!values.name) throw new Error('Skill name is required');
      if (!values.content) throw new Error('Skill content is required');
      const saved = await saveSkill(values);
      if (saved && saved.id) {{
        editingSkillId = saved.id;
        state.selectedSkillId = saved.id;
        els.skillEditorHint.textContent = `Saved ${{saved.name || saved.id}}.`;
      }}
    }}
    function clearSkillEditor() {{
      editingSkillId = null;
      els.skillEditorName.value = '';
      els.skillEditorContent.value = '';
      els.skillEditorTags.value = '';
      els.skillEditorHint.textContent = 'Create a reusable skill without dialogs.';
    }}
    function memoryEditorValues() {{
      const existing = editingMemoryId ? (state.memories || []).find((item) => String(item.id || '') === String(editingMemoryId || '')) || null : null;
      return {{
        ...(existing || {{}}),
        title: (els.memoryEditorTitle.value || existing?.title || '').trim(),
        content: els.memoryEditorContent.value || existing?.content || '',
        scope: els.memoryEditorScope.value || existing?.scope || 'user',
      }};
    }}
    function openMemoryEditor(memory) {{
      editingMemoryId = memory && memory.id ? memory.id : null;
      els.memoryEditorTitle.value = memory?.title || (els.conversationTitle.value || els.title.textContent || 'Memory').trim() || '';
      els.memoryEditorContent.value = memory?.content || els.systemPrompt.value || els.prompt.value || '';
      els.memoryEditorScope.value = memory?.scope || 'user';
      els.memoryEditorHint.textContent = memory
        ? `Editing ${{memory.title || memory.id}}.`
        : 'Create a memory without dialogs.';
    }}
    async function saveMemoryEditor() {{
      const values = memoryEditorValues();
      if (!values.title) throw new Error('Memory title is required');
      if (!values.content) throw new Error('Memory content is required');
      const saved = await saveMemory(values);
      if (saved && saved.id) {{
        editingMemoryId = saved.id;
        state.selectedMemoryId = saved.id;
        els.memoryEditorHint.textContent = `Saved ${{saved.title || saved.id}}.`;
      }}
    }}
    function clearMemoryEditor() {{
      editingMemoryId = null;
      els.memoryEditorTitle.value = '';
      els.memoryEditorContent.value = '';
      els.memoryEditorScope.value = 'user';
      els.memoryEditorHint.textContent = 'Create a memory without dialogs.';
    }}
    function noteEditorValues() {{
      const existing = editingNoteId ? (state.notes || []).find((item) => String(item.id || '') === String(editingNoteId || '')) || null : null;
      return {{
        ...(existing || {{}}),
        title: (els.noteEditorTitle.value || existing?.title || '').trim(),
        body: els.noteEditorBody.value || existing?.body || '',
      }};
    }}
    function openNoteEditor(note) {{
      editingNoteId = note && note.id ? note.id : null;
      els.noteEditorTitle.value = note?.title || (els.conversationTitle.value || els.title.textContent || 'Note').trim() || '';
      els.noteEditorBody.value = note?.body || els.systemPrompt.value || els.prompt.value || '';
      els.noteEditorHint.textContent = note
        ? `Editing ${{note.title || note.id}}.`
        : 'Create a note without dialogs.';
    }}
    async function saveNoteEditor() {{
      const values = noteEditorValues();
      if (!values.title) throw new Error('Note title is required');
      if (!values.body) throw new Error('Note body is required');
      const saved = await saveNote(values);
      if (saved && saved.id) {{
        editingNoteId = saved.id;
        state.selectedNoteId = saved.id;
        els.noteEditorHint.textContent = `Saved ${{saved.title || saved.id}}.`;
      }}
    }}
    function clearNoteEditor() {{
      editingNoteId = null;
      els.noteEditorTitle.value = '';
      els.noteEditorBody.value = '';
      els.noteEditorHint.textContent = 'Create a note without dialogs.';
    }}
    function renderSkills() {{
      els.skillChips.innerHTML = '';
      const skills = state.skills || [];
      if (!skills.length) {{
        els.skillChips.innerHTML = '<span class=\"muted\">No skills registered.</span>';
        els.skillPreview.textContent = 'Select a skill to preview it here.';
        return;
      }}
      const selected = skills.find((item) => String(item.id || '') === String(state.selectedSkillId || '')) || skills[0];
      state.selectedSkillId = selected && selected.id ? selected.id : '';
      for (const skill of skills) {{
        const row = document.createElement('div');
        row.className = 'resource-item';
        const chipRow = document.createElement('div');
        chipRow.className = 'row';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = skill.name || skill.id;
        chip.title = skillSummary(skill) || skill.content || skill.id;
        chip.addEventListener('click', () => {{
          state.selectedSkillId = skill.id || '';
          els.skillPreview.textContent = [skill.name || skill.id, skillSummary(skill), skill.content || ''].filter(Boolean).join('\\n\\n');
          renderAll();
        }});
        const use = document.createElement('button');
        use.type = 'button';
        use.className = 'secondary';
        use.textContent = 'Use';
        use.addEventListener('click', () => {{
          setSystemPromptFromContent(skill.content || '');
        }});
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'secondary';
        copy.textContent = 'Copy';
        copy.addEventListener('click', async () => {{
          await copyText(skill.content || '');
        }});
        const shareMd = document.createElement('button');
        shareMd.type = 'button';
        shareMd.className = 'secondary';
        shareMd.textContent = 'Share MD';
        shareMd.addEventListener('click', async () => {{
          await downloadSharedItem('skills', skill, 'md');
        }});
        const shareHtml = document.createElement('button');
        shareHtml.type = 'button';
        shareHtml.className = 'secondary';
        shareHtml.textContent = 'Share HTML';
        shareHtml.addEventListener('click', async () => {{
          await downloadSharedItem('skills', skill, 'html');
        }});
        const shareJson = document.createElement('button');
        shareJson.type = 'button';
        shareJson.className = 'secondary';
        shareJson.textContent = 'Share JSON';
        shareJson.addEventListener('click', async () => {{
          await downloadSharedItem('skills', skill, 'json');
        }});
        chipRow.appendChild(chip);
        chipRow.appendChild(use);
        chipRow.appendChild(copy);
        chipRow.appendChild(shareMd);
        chipRow.appendChild(shareHtml);
        chipRow.appendChild(shareJson);
        row.appendChild(chipRow);
        row.appendChild(document.createElement('div')).textContent = skillSummary(skill) || 'Skill';
        els.skillChips.appendChild(row);
      }}
      els.skillPreview.textContent = [selected.name || selected.id, skillSummary(selected), selected.content || ''].filter(Boolean).join('\\n\\n');
    }}
    function renderMemories() {{
      els.memoryChips.innerHTML = '';
      const memories = state.memories || [];
      if (!memories.length) {{
        els.memoryChips.innerHTML = '<span class=\"muted\">No memories registered.</span>';
        els.memoryPreview.textContent = 'Select a memory to preview it here.';
        return;
      }}
      const selected = memories.find((item) => String(item.id || '') === String(state.selectedMemoryId || '')) || memories[0];
      state.selectedMemoryId = selected && selected.id ? selected.id : '';
      for (const memory of memories) {{
        const row = document.createElement('div');
        row.className = 'resource-item';
        const chipRow = document.createElement('div');
        chipRow.className = 'row';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = memory.title || memory.id;
        chip.title = memorySummary(memory) || memory.content || memory.id;
        chip.addEventListener('click', () => {{
          state.selectedMemoryId = memory.id || '';
          els.memoryPreview.textContent = [memory.title || memory.id, memorySummary(memory), memory.content || ''].filter(Boolean).join('\\n\\n');
          renderAll();
        }});
        const use = document.createElement('button');
        use.type = 'button';
        use.className = 'secondary';
        use.textContent = 'Use';
        use.addEventListener('click', () => {{
          setSystemPromptFromContent(memory.content || '');
        }});
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'secondary';
        copy.textContent = 'Copy';
        copy.addEventListener('click', async () => {{
          await copyText(memory.content || '');
        }});
        chipRow.appendChild(chip);
        chipRow.appendChild(use);
        chipRow.appendChild(copy);
        row.appendChild(chipRow);
        row.appendChild(document.createElement('div')).textContent = memorySummary(memory) || 'Memory';
        els.memoryChips.appendChild(row);
      }}
      els.memoryPreview.textContent = [selected.title || selected.id, memorySummary(selected), selected.content || ''].filter(Boolean).join('\\n\\n');
    }}
    function applyAgentToConversation(agent) {{
      const convo = activeConversation();
      if (!convo || !agent) return;
      convo.agentId = agent.id || '';
      convo.model = agent.baseModel || convo.model || state.currentModel || bootstrap.selectedModel || '';
      convo.systemPrompt = agent.systemPrompt || convo.systemPrompt || '';
      if (agent.folderId) {{
        convo.folderId = agent.folderId;
        els.folderSelect.value = agent.folderId;
      }}
      state.currentAgentId = agent.id || '';
      state.currentModel = convo.model;
      els.modelSelect.value = convo.model || els.modelSelect.value;
      els.systemPrompt.value = convo.systemPrompt || '';
      save();
      void saveConversation(convo);
      syncFields();
      renderAll();
    }}
    async function refreshNotes() {{
      try {{
        const response = await fetch('/api/ai/notes');
        if (!response.ok) return;
        const data = await response.json();
        state.notes = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function refreshArtifacts() {{
      try {{
        const response = await fetch('/api/ai/artifacts');
        if (!response.ok) return;
        const data = await response.json();
        state.artifacts = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function refreshTools() {{
      try {{
        const response = await fetch('/api/ai/tools');
        if (!response.ok) return;
        const data = await response.json();
        state.toolServers = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function refreshWebhooks() {{
      try {{
        const response = await fetch('/api/ai/webhooks');
        if (!response.ok) return;
        const data = await response.json();
        state.webhooks = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function refreshWebSearchProviders() {{
      try {{
        const response = await fetch('/api/ai/web-search');
        if (!response.ok) return;
        const data = await response.json();
        state.webSearchProviders = Array.isArray(data.data && data.data.providers) ? data.data.providers : [];
        if (!state.webSearchProviders.some((item) => String(item.id || '') === String(state.webSearchProvider || ''))) {{
          state.webSearchProvider = data.data && data.data.defaultProvider ? String(data.data.defaultProvider) : 'duckduckgo';
        }}
      }} catch (err) {{
        return;
      }}
    }}
    async function saveNote(note) {{
      const response = await fetch('/api/ai/notes', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(note),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Note save failed');
      }}
      const data = await response.json();
      await refreshNotes();
      renderAll();
      return data.data || null;
    }}
    async function deleteNote(noteId) {{
      const response = await fetch('/api/ai/notes', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: noteId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Note delete failed');
      }}
      state.selectedNoteId = '';
      await refreshNotes();
      renderAll();
    }}
    async function saveArtifact(artifact) {{
      const response = await fetch('/api/ai/artifacts', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(artifact),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Artifact save failed');
      }}
      const data = await response.json();
      await refreshArtifacts();
      renderAll();
      return data.data || null;
    }}
    async function deleteArtifact(artifactId) {{
      const response = await fetch('/api/ai/artifacts', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: artifactId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Artifact delete failed');
      }}
      state.selectedArtifactId = '';
      await refreshArtifacts();
      renderAll();
    }}
    async function saveTool(tool) {{
      const response = await fetch('/api/ai/tools', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(tool),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Tool save failed');
      }}
      const data = await response.json();
      await refreshTools();
      renderAll();
      return data.data || null;
    }}
    async function deleteTool(toolId) {{
      const response = await fetch('/api/ai/tools', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: toolId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Tool delete failed');
      }}
      state.selectedToolId = '';
      await refreshTools();
      renderAll();
    }}
    async function saveWebhook(webhook) {{
      const response = await fetch('/api/ai/webhooks', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(webhook),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Webhook save failed');
      }}
      const data = await response.json();
      await refreshWebhooks();
      renderAll();
      return data.data || null;
    }}
    async function deleteWebhook(webhookId) {{
      const response = await fetch('/api/ai/webhooks', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: webhookId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Webhook delete failed');
      }}
      state.selectedWebhookId = '';
      await refreshWebhooks();
      renderAll();
    }}
    function webSearchProviderLabel(provider) {{
      const item = (state.webSearchProviders || []).find((entry) => String(entry.id || '') === String(provider || ''));
      if (!item) return provider || 'duckduckgo';
      return `${{item.name || item.id}}${{item.requiresApiKey ? ' · API key' : ''}}`;
    }}
    function webSearchValues() {{
      return {{
        query: (els.webSearchQuery.value || '').trim(),
        provider: els.webSearchProvider.value || 'duckduckgo',
        fallbackProviders: textToList(els.webSearchFallback.value || ''),
        engineUrl: (els.webSearchEngineUrl.value || '').trim(),
        apiKey: (els.webSearchApiKey.value || '').trim(),
        baseId: (els.webSearchBaseId.value || '').trim(),
        knowledgeName: (els.webSearchName.value || '').trim(),
        description: (els.webSearchDescription.value || '').trim(),
        saveLimit: Number(els.webSearchSaveLimit.value || '5') || 5,
      }};
    }}
    function renderWebSearch() {{
      if (els.webSearchQuery && els.webSearchQuery.value !== state.webSearchQuery) {{
        els.webSearchQuery.value = state.webSearchQuery || '';
      }}
      if (els.webSearchProvider) {{
        const providers = state.webSearchProviders || [];
        els.webSearchProvider.innerHTML = '';
        for (const provider of providers) {{
          const option = document.createElement('option');
          option.value = provider.id || '';
          option.textContent = webSearchProviderLabel(provider.id || '');
          els.webSearchProvider.appendChild(option);
        }}
        if (!providers.length) {{
          const option = document.createElement('option');
          option.value = 'duckduckgo';
          option.textContent = 'DuckDuckGo HTML';
          els.webSearchProvider.appendChild(option);
        }}
        els.webSearchProvider.value = state.webSearchProvider || 'duckduckgo';
      }}
      if (els.webSearchFallback) els.webSearchFallback.value = state.webSearchFallback || '';
      if (els.webSearchEngineUrl) els.webSearchEngineUrl.value = state.webSearchEngineUrl || '';
      if (els.webSearchBaseId) els.webSearchBaseId.value = state.webSearchBaseId || '';
      if (els.webSearchName) els.webSearchName.value = state.webSearchName || '';
      if (els.webSearchDescription) els.webSearchDescription.value = state.webSearchDescription || '';
      if (els.webSearchSaveLimit) els.webSearchSaveLimit.value = String(state.webSearchSaveLimit || 5);
      els.webSearchResults.innerHTML = '';
      const results = state.webSearchResults || [];
      if (!results.length) {{
        els.webSearchResults.innerHTML = '<span class=\"muted\">No web search results yet.</span>';
        return;
      }}
      results.forEach((item, index) => {{
        const card = document.createElement('article');
        card.className = 'panel stack';
        card.innerHTML = `
          <strong>${{escapeHtml(String(item.title || item.url || 'Result'))}}</strong>
          <div class=\"muted\">${{escapeHtml(String(item.url || ''))}}</div>
          <div class=\"muted\">${{escapeHtml(String(item.snippet || ''))}}</div>
        `;
        const footer = document.createElement('div');
        footer.className = 'toolbar';
        const open = document.createElement('button');
        open.type = 'button';
        open.className = 'secondary';
        open.textContent = 'Open';
        open.addEventListener('click', () => {{
          window.open(String(item.url || ''), '_blank', 'noopener,noreferrer');
        }});
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'secondary';
        copy.textContent = 'Copy URL';
        copy.addEventListener('click', async () => {{
          await copyText(String(item.url || ''));
        }});
        footer.appendChild(open);
        footer.appendChild(copy);
        card.appendChild(footer);
        if (index === 0) {{
          const marker = document.createElement('div');
          marker.className = 'hint';
          marker.textContent = 'Top result';
          card.insertBefore(marker, card.firstChild);
        }}
        els.webSearchResults.appendChild(card);
      }});
    }}
    async function runWebSearch(action = 'search') {{
      const values = webSearchValues();
      if (!values.query) {{
        window.alert('Enter a web search query first.');
        return;
      }}
      const response = await fetch('/api/ai/web-search', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          action,
          query: values.query,
          provider: values.provider,
          fallbackProviders: values.fallbackProviders,
          engineUrl: values.engineUrl,
          apiKey: values.apiKey,
          baseId: values.baseId,
          knowledgeName: values.knowledgeName,
          description: values.description,
          saveLimit: values.saveLimit,
        }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Web search failed');
      }}
      const data = await response.json();
      if (action === 'save') {{
        state.webSearchResults = state.webSearchResults || [];
        await refreshKnowledgeBases();
      }} else {{
        state.webSearchResults = Array.isArray(data.data) ? data.data : [];
      }}
      renderAll();
      return data.data || null;
    }}
    function noteSummary(note) {{
      const parts = [];
      if (Array.isArray(note.files) && note.files.length) parts.push(`${{note.files.length}} file(s)`);
      if (Array.isArray(note.images) && note.images.length) parts.push(`${{note.images.length}} image(s)`);
      if (Array.isArray(note.tags) && note.tags.length) parts.push(note.tags.join(', '));
      return parts.join(' · ');
    }}
    function artifactSummary(artifact) {{
      const parts = [];
      if (artifact.kind) parts.push(artifact.kind);
      if (Array.isArray(artifact.tags) && artifact.tags.length) parts.push(artifact.tags.join(', '));
      return parts.join(' · ');
    }}
    function artifactEditorValues() {{
      const existing = editingArtifactId ? (state.artifacts || []).find((item) => String(item.id || '') === String(editingArtifactId || '')) || null : null;
      return {{
        ...(existing || {{}}),
        title: (els.artifactEditorTitle.value || existing?.title || '').trim(),
        content: els.artifactEditorContent.value || existing?.content || '',
        kind: (els.artifactEditorKind.value || existing?.kind || '').trim(),
        tags: textToList(els.artifactEditorTags.value || listToText(existing?.tags || [])),
      }};
    }}
    function openArtifactEditor(artifact) {{
      editingArtifactId = artifact && artifact.id ? artifact.id : null;
      els.artifactEditorTitle.value = artifact?.title || (els.conversationTitle.value || els.title.textContent || 'Artifact').trim() || '';
      els.artifactEditorContent.value = artifact?.content || els.prompt.value || els.systemPrompt.value || '';
      els.artifactEditorKind.value = artifact?.kind || '';
      els.artifactEditorTags.value = listToText(artifact?.tags || []);
      els.artifactEditorHint.textContent = artifact
        ? `Editing ${{artifact.title || artifact.id}}.`
        : 'Create an artifact without dialogs.';
    }}
    async function saveArtifactEditor() {{
      const values = artifactEditorValues();
      if (!values.title) throw new Error('Artifact title is required');
      if (!values.content) throw new Error('Artifact content is required');
      const saved = await saveArtifact(values);
      if (saved && saved.id) {{
        editingArtifactId = saved.id;
        state.selectedArtifactId = saved.id;
        els.artifactEditorHint.textContent = `Saved ${{saved.title || saved.id}}.`;
      }}
    }}
    function clearArtifactEditor() {{
      editingArtifactId = null;
      els.artifactEditorTitle.value = '';
      els.artifactEditorContent.value = '';
      els.artifactEditorKind.value = '';
      els.artifactEditorTags.value = '';
      els.artifactEditorHint.textContent = 'Create an artifact without dialogs.';
    }}
    function toolSummary(tool) {{
      const parts = [];
      if (tool.type) parts.push(tool.type);
      if (tool.endpoint || tool.url) parts.push(tool.endpoint || tool.url);
      if (Array.isArray(tool.tags) && tool.tags.length) parts.push(tool.tags.join(', '));
      if (tool.enabled === false) parts.push('disabled');
      return parts.join(' · ');
    }}
    function kbSummary(base) {{
      const parts = [];
      if (base.sourceDir) parts.push(base.sourceDir);
      if (Array.isArray(base.sources) && base.sources.length) parts.push(`${{base.sources.length}} source(s)`);
      if (Array.isArray(base.tags) && base.tags.length) parts.push(base.tags.join(', '));
      if (base.enabled === false) parts.push('disabled');
      return parts.join(' · ');
    }}
    function webhookSummary(webhook) {{
      const parts = [];
      if (Array.isArray(webhook.events) && webhook.events.length) parts.push(webhook.events.join(', '));
      if (webhook.enabled === false) parts.push('disabled');
      if (Array.isArray(webhook.tags) && webhook.tags.length) parts.push(webhook.tags.join(', '));
      return parts.join(' · ');
    }}
    function knowledgeBaseEditorValues() {{
      const existing = editingKnowledgeBaseId ? (state.knowledgeBases || []).find((item) => String(item.id || '') === String(editingKnowledgeBaseId || '')) || null : null;
      return {{
        ...(existing || {{}}),
        name: (els.kbEditorName.value || existing?.name || '').trim(),
        sourceDir: els.kbEditorSourceDir.value || existing?.sourceDir || '',
        description: els.kbEditorDescription.value || existing?.description || '',
        tags: textToList(els.kbEditorTags.value || listToText(existing?.tags || [])),
      }};
    }}
    function openKnowledgeBaseEditor(base) {{
      editingKnowledgeBaseId = base && base.id ? base.id : null;
      els.kbEditorName.value = base?.name || (els.conversationTitle.value || els.title.textContent || 'Knowledge base').trim() || '';
      els.kbEditorSourceDir.value = base?.sourceDir || '';
      els.kbEditorDescription.value = base?.description || '';
      els.kbEditorTags.value = listToText(base?.tags || []);
      els.kbEditorHint.textContent = base
        ? `Editing ${{base.name || base.id}}.`
        : 'Create a knowledge base without dialogs.';
    }}
    async function saveKnowledgeBaseEditor() {{
      const values = knowledgeBaseEditorValues();
      if (!values.name) throw new Error('Knowledge base name is required');
      if (!values.sourceDir) throw new Error('Knowledge base source is required');
      const saved = await saveKnowledgeBase(values);
      if (saved && saved.id) {{
        editingKnowledgeBaseId = saved.id;
        state.selectedKnowledgeBaseId = saved.id;
        els.kbEditorHint.textContent = `Saved ${{saved.name || saved.id}}.`;
      }}
    }}
    function clearKnowledgeBaseEditor() {{
      editingKnowledgeBaseId = null;
      els.kbEditorName.value = '';
      els.kbEditorSourceDir.value = '';
      els.kbEditorDescription.value = '';
      els.kbEditorTags.value = '';
      els.kbEditorHint.textContent = 'Create a knowledge base without dialogs.';
    }}
    function toolEditorValues() {{
      const existing = editingToolId ? (state.toolServers || []).find((item) => String(item.id || '') === String(editingToolId || '')) || null : null;
      return {{
        ...(existing || {{}}),
        name: (els.toolEditorName.value || existing?.name || '').trim(),
        endpoint: els.toolEditorEndpoint.value || existing?.endpoint || existing?.url || '',
        type: els.toolEditorType.value || existing?.type || 'mcp',
        description: els.toolEditorDescription.value || existing?.description || '',
        auth: (els.toolEditorAuth.value || '').trim(),
      }};
    }}
    function openToolEditor(tool) {{
      editingToolId = tool && tool.id ? tool.id : null;
      els.toolEditorName.value = tool?.name || (els.conversationTitle.value || els.title.textContent || 'Tool server').trim() || '';
      els.toolEditorEndpoint.value = tool?.endpoint || tool?.url || '';
      els.toolEditorType.value = tool?.type || 'mcp';
      els.toolEditorDescription.value = tool?.description || '';
      els.toolEditorAuth.value = typeof tool?.auth === 'string' ? tool.auth : tool?.auth ? JSON.stringify(tool.auth) : '';
      els.toolEditorHint.textContent = tool
        ? `Editing ${{tool.name || tool.id}}.`
        : 'Create a tool server without dialogs.';
    }}
    async function saveToolEditor() {{
      const values = toolEditorValues();
      if (!values.name) throw new Error('Tool server name is required');
      if (!values.endpoint) throw new Error('Tool server endpoint is required');
      let auth = values.auth;
      if (auth) {{
        try {{
          auth = JSON.parse(auth);
        }} catch (err) {{
          // Keep raw token/string when it is not JSON.
        }}
      }} else {{
        auth = '';
      }}
      const saved = await saveTool({{
        ...values,
        auth,
      }});
      if (saved && saved.id) {{
        editingToolId = saved.id;
        state.selectedToolId = saved.id;
        els.toolEditorHint.textContent = `Saved ${{saved.name || saved.id}}.`;
      }}
    }}
    function clearToolEditor() {{
      editingToolId = null;
      els.toolEditorName.value = '';
      els.toolEditorEndpoint.value = '';
      els.toolEditorType.value = 'mcp';
      els.toolEditorDescription.value = '';
      els.toolEditorAuth.value = '';
      els.toolEditorHint.textContent = 'Create a tool server without dialogs.';
    }}
    function webhookEditorValues() {{
      const existing = editingWebhookId ? (state.webhooks || []).find((item) => String(item.id || '') === String(editingWebhookId || '')) || null : null;
      return {{
        ...(existing || {{}}),
        name: (els.webhookEditorName.value || existing?.name || '').trim(),
        url: els.webhookEditorUrl.value || existing?.url || '',
        events: textToList(els.webhookEditorEvents.value || listToText(existing?.events || [])),
        description: els.webhookEditorDescription.value || existing?.description || '',
        secret: els.webhookEditorSecret.value || existing?.secret || '',
      }};
    }}
    function openWebhookEditor(webhook) {{
      editingWebhookId = webhook && webhook.id ? webhook.id : null;
      els.webhookEditorName.value = webhook?.name || (els.conversationTitle.value || els.title.textContent || 'Webhook').trim() || '';
      els.webhookEditorUrl.value = webhook?.url || '';
      els.webhookEditorEvents.value = listToText(webhook?.events || []);
      els.webhookEditorDescription.value = webhook?.description || '';
      els.webhookEditorSecret.value = webhook?.secret || '';
      els.webhookEditorHint.textContent = webhook
        ? `Editing ${{webhook.name || webhook.id}}.`
        : 'Create a webhook without dialogs.';
    }}
    async function saveWebhookEditor() {{
      const values = webhookEditorValues();
      if (!values.name) throw new Error('Webhook name is required');
      if (!values.url) throw new Error('Webhook URL is required');
      const saved = await saveWebhook(values);
      if (saved && saved.id) {{
        editingWebhookId = saved.id;
        state.selectedWebhookId = saved.id;
        els.webhookEditorHint.textContent = `Saved ${{saved.name || saved.id}}.`;
      }}
    }}
    function clearWebhookEditor() {{
      editingWebhookId = null;
      els.webhookEditorName.value = '';
      els.webhookEditorUrl.value = '';
      els.webhookEditorEvents.value = '';
      els.webhookEditorDescription.value = '';
      els.webhookEditorSecret.value = '';
      els.webhookEditorHint.textContent = 'Create a webhook without dialogs.';
    }}
    function setSystemPromptFromContent(content) {{
      els.systemPrompt.value = String(content || '');
      persistActiveFields();
      renderAll();
      els.systemPrompt.focus();
    }}
    function setPromptFromContent(content) {{
      els.prompt.value = String(content || '');
      els.prompt.focus();
    }}
    function renderNotes() {{
      els.noteChips.innerHTML = '';
      const notes = state.notes || [];
      if (!notes.length) {{
        els.noteChips.innerHTML = '<span class=\"muted\">No notes registered.</span>';
        els.notePreview.textContent = 'Select a note to preview it here.';
        return;
      }}
      const selected = notes.find((item) => String(item.id || '') === String(state.selectedNoteId || '')) || notes[0];
      state.selectedNoteId = selected && selected.id ? selected.id : '';
      for (const note of notes) {{
        const row = document.createElement('div');
        row.className = 'resource-item';
        const chipRow = document.createElement('div');
        chipRow.className = 'row';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = note.title || note.id;
        chip.title = noteSummary(note) || note.body || note.id;
        chip.addEventListener('click', () => {{
          state.selectedNoteId = note.id || '';
          els.notePreview.textContent = [note.title || note.id, noteSummary(note), note.body || ''].filter(Boolean).join('\\n\\n');
          renderAll();
        }});
        const use = document.createElement('button');
        use.type = 'button';
        use.className = 'secondary';
        use.textContent = 'Use';
        use.addEventListener('click', () => {{
          setSystemPromptFromContent(note.body || '');
        }});
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'secondary';
        copy.textContent = 'Copy';
        copy.addEventListener('click', async () => {{
          await copyText(note.body || '');
        }});
        chipRow.appendChild(chip);
        chipRow.appendChild(use);
        chipRow.appendChild(copy);
        row.appendChild(chipRow);
        row.appendChild(document.createElement('div')).textContent = noteSummary(note) || 'Note';
        els.noteChips.appendChild(row);
      }}
      els.notePreview.textContent = [selected.title || selected.id, noteSummary(selected), selected.body || ''].filter(Boolean).join('\\n\\n');
    }}
    function renderArtifacts() {{
      els.artifactChips.innerHTML = '';
      const artifacts = state.artifacts || [];
      if (!artifacts.length) {{
        els.artifactChips.innerHTML = '<span class=\"muted\">No artifacts registered.</span>';
        els.artifactPreview.textContent = 'Select an artifact to preview it here.';
        return;
      }}
      const selected = artifacts.find((item) => String(item.id || '') === String(state.selectedArtifactId || '')) || artifacts[0];
      state.selectedArtifactId = selected && selected.id ? selected.id : '';
      for (const artifact of artifacts) {{
        const row = document.createElement('div');
        row.className = 'resource-item';
        const chipRow = document.createElement('div');
        chipRow.className = 'row';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = artifact.title || artifact.id;
        chip.title = artifactSummary(artifact) || artifact.content || artifact.id;
        chip.addEventListener('click', () => {{
          state.selectedArtifactId = artifact.id || '';
          els.artifactPreview.textContent = [artifact.title || artifact.id, artifactSummary(artifact), artifact.content || ''].filter(Boolean).join('\\n\\n');
          renderAll();
        }});
        const use = document.createElement('button');
        use.type = 'button';
        use.className = 'secondary';
        use.textContent = 'Use';
        use.addEventListener('click', () => {{
          setPromptFromContent(artifact.content || '');
        }});
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'secondary';
        copy.textContent = 'Copy';
        copy.addEventListener('click', async () => {{
          await copyText(artifact.content || '');
        }});
        chipRow.appendChild(chip);
        chipRow.appendChild(use);
        chipRow.appendChild(copy);
        row.appendChild(chipRow);
        row.appendChild(document.createElement('div')).textContent = artifactSummary(artifact) || 'Artifact';
        els.artifactChips.appendChild(row);
      }}
      els.artifactPreview.textContent = [selected.title || selected.id, artifactSummary(selected), selected.content || ''].filter(Boolean).join('\\n\\n');
    }}
    function renderTools() {{
      els.toolChips.innerHTML = '';
      const toolServers = state.toolServers || [];
      if (!toolServers.length) {{
        els.toolChips.innerHTML = '<span class=\"muted\">No tool servers registered.</span>';
        els.toolPreview.textContent = 'Select a tool server to preview it here.';
        return;
      }}
      const selected = toolServers.find((item) => String(item.id || '') === String(state.selectedToolId || '')) || toolServers[0];
      state.selectedToolId = selected && selected.id ? selected.id : '';
      for (const tool of toolServers) {{
        const row = document.createElement('div');
        row.className = 'resource-item';
        const chipRow = document.createElement('div');
        chipRow.className = 'row';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = tool.name || tool.id;
        chip.title = toolSummary(tool) || tool.endpoint || tool.url || tool.id;
        chip.addEventListener('click', () => {{
          state.selectedToolId = tool.id || '';
          els.toolPreview.textContent = [
            tool.name || tool.id,
            toolSummary(tool),
            tool.endpoint || tool.url || '',
            tool.description || '',
            tool.auth ? JSON.stringify(tool.auth, null, 2) : '',
          ].filter(Boolean).join('\\n\\n');
          renderAll();
        }});
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'secondary';
        copy.textContent = 'Copy URL';
        copy.addEventListener('click', async () => {{
          await copyText(tool.endpoint || tool.url || '');
        }});
        chipRow.appendChild(chip);
        chipRow.appendChild(copy);
        row.appendChild(chipRow);
        row.appendChild(document.createElement('div')).textContent = toolSummary(tool) || 'Tool server';
        els.toolChips.appendChild(row);
      }}
      els.toolPreview.textContent = [
        selected.name || selected.id,
        toolSummary(selected),
        selected.endpoint || selected.url || '',
        selected.description || '',
        selected.auth ? JSON.stringify(selected.auth, null, 2) : '',
      ].filter(Boolean).join('\\n\\n');
    }}
    function renderWebhooks() {{
      els.webhookChips.innerHTML = '';
      const webhooks = state.webhooks || [];
      if (!webhooks.length) {{
        els.webhookChips.innerHTML = '<span class=\"muted\">No webhooks registered.</span>';
        els.webhookPreview.textContent = 'Select a webhook to preview it here.';
        return;
      }}
      const selected = webhooks.find((item) => String(item.id || '') === String(state.selectedWebhookId || '')) || webhooks[0];
      state.selectedWebhookId = selected && selected.id ? selected.id : '';
      for (const webhook of webhooks) {{
        const row = document.createElement('div');
        row.className = 'resource-item';
        const chipRow = document.createElement('div');
        chipRow.className = 'row';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = webhook.name || webhook.id;
        chip.title = webhookSummary(webhook) || webhook.url || webhook.id;
        chip.addEventListener('click', () => {{
          state.selectedWebhookId = webhook.id || '';
          els.webhookPreview.textContent = [
            webhook.name || webhook.id,
            webhookSummary(webhook),
            webhook.url || '',
            webhook.description || '',
            Array.isArray(webhook.events) ? webhook.events.join('\\n') : '',
          ].filter(Boolean).join('\\n\\n');
          renderAll();
        }});
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'secondary';
        copy.textContent = 'Copy URL';
        copy.addEventListener('click', async () => {{
          await copyText(webhook.url || '');
        }});
        chipRow.appendChild(chip);
        chipRow.appendChild(copy);
        row.appendChild(chipRow);
        row.appendChild(document.createElement('div')).textContent = webhookSummary(webhook) || 'Webhook';
        els.webhookChips.appendChild(row);
      }}
      els.webhookPreview.textContent = [
        selected.name || selected.id,
        webhookSummary(selected),
        selected.url || '',
        selected.description || '',
        Array.isArray(selected.events) ? selected.events.join('\\n') : '',
      ].filter(Boolean).join('\\n\\n');
    }}
    function renderStatusPills() {{
      els.statusPills.innerHTML = '';
      const convo = activeConversation();
      const pills = [];
      if (activeAbortController) {{
        pills.push({{ label: 'Stream', value: 'live' }});
      }}
      pills.push({{ label: 'Model', value: convo?.model || state.currentModel || bootstrap.selectedModel || 'not set' }});
      if (convo) {{
        pills.push({{ label: 'Pinned', value: convo.pinned ? 'yes' : 'no' }});
        pills.push({{ label: 'Archived', value: convo.archived ? 'yes' : 'no' }});
      }}
      if (convo && convo.folderId) pills.push({{ label: 'Workspace', value: folderLabel(convo.folderId) }});
      if (convo && convo.agentId) {{
        const agent = (state.agents || []).find((item) => String(item.id || '') === String(convo.agentId || ''));
        pills.push({{ label: 'Agent', value: agent ? (agent.name || agent.id) : convo.agentId }});
      }} else if (state.currentAgentId) {{
        const agent = (state.agents || []).find((item) => String(item.id || '') === String(state.currentAgentId || ''));
        pills.push({{ label: 'Agent', value: agent ? (agent.name || agent.id) : state.currentAgentId }});
      }}
      if (state.compareEnabled) {{
        pills.push({{ label: 'Compare', value: state.compareModel || 'enabled' }});
      }}
      pills.push({{ label: 'Files', value: String(selectedFiles().length) }});
      for (const pill of pills) {{
        const item = document.createElement('span');
        item.className = 'pill';
        item.innerHTML = '<strong>' + escapeHtml(pill.label) + ':</strong> ' + escapeHtml(String(pill.value || ''));
        els.statusPills.appendChild(item);
      }}
    }}
    async function queryKnowledgeBases() {{
      const query = (els.kbQuery.value || '').trim();
      if (!query) {{
        window.alert('Enter a knowledge search query first.');
        return;
      }}
      const response = await fetch('/api/ai/kb/query', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ query }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Knowledge query failed');
      }}
      const data = await response.json();
      state.kbResults = Array.isArray(data.data) ? data.data : [];
      renderAll();
    }}
    function renderKnowledgeBases() {{
      els.kbChips.innerHTML = '';
      const bases = state.knowledgeBases || [];
      if (!bases.length) {{
        els.kbChips.innerHTML = '<span class=\"muted\">No knowledge bases registered.</span>';
        els.kbPreview.textContent = 'Select a knowledge base to preview it here.';
      }} else {{
        const selected = bases.find((item) => String(item.id || '') === String(state.selectedKnowledgeBaseId || '')) || bases[0];
        state.selectedKnowledgeBaseId = selected && selected.id ? selected.id : '';
        for (const base of bases) {{
          const row = document.createElement('div');
          row.className = 'kb-item';
          const chipRow = document.createElement('div');
          chipRow.className = 'row';
          const chip = document.createElement('button');
          chip.type = 'button';
          chip.className = 'chip';
          chip.textContent = `${{base.name || base.id}}`;
          chip.title = kbSummary(base) || base.sourceDir || base.description || base.id;
          chip.addEventListener('click', () => {{
            state.selectedKnowledgeBaseId = base.id || '';
            els.kbPreview.textContent = [
              base.name || base.id,
              kbSummary(base),
              base.description || '',
              base.sourceDir || '',
              Array.isArray(base.sources) ? base.sources.join('\\n') : '',
            ].filter(Boolean).join('\\n\\n');
            renderAll();
          }});
          const query = document.createElement('button');
          query.type = 'button';
          query.className = 'secondary';
          query.textContent = 'Query';
          query.addEventListener('click', () => {{
            els.kbQuery.value = base.id || '';
            renderAll();
          }});
          chipRow.appendChild(chip);
          chipRow.appendChild(query);
          row.appendChild(chipRow);
          row.appendChild(document.createElement('div')).textContent = kbSummary(base) || 'Knowledge base';
          els.kbChips.appendChild(row);
        }}
        els.kbPreview.textContent = [
          selected.name || selected.id,
          kbSummary(selected),
          selected.description || '',
          selected.sourceDir || '',
          Array.isArray(selected.sources) ? selected.sources.join('\\n') : '',
        ].filter(Boolean).join('\\n\\n');
      }}
      els.kbResults.innerHTML = '';
      const results = state.kbResults || [];
      if (!results.length) return;
      for (const item of results.slice(0, 10)) {{
        const card = document.createElement('article');
        card.className = 'panel stack';
        card.innerHTML = `
          <strong>${{escapeHtml(item.title || item.documentId || 'Match')}}</strong>
          <div class=\"muted\">${{escapeHtml(item.baseId || '')}} · ${{escapeHtml(item.indexId || '')}}</div>
          <div class=\"muted\">${{escapeHtml(item.snippet || '')}}</div>
        `;
        els.kbResults.appendChild(card);
      }}
    }}
    function activeConversation() {{
      return state.conversations.find((item) => item.id === state.activeId) || null;
    }}
    function currentMessageSearchQuery() {{
      return (els.messageSearch.value || '').trim().toLowerCase();
    }}
    function computeMessageSearchMatches(convo) {{
      const query = currentMessageSearchQuery();
      if (!query || !convo || !Array.isArray(convo.messages)) return [];
      const matches = [];
      convo.messages.forEach((message, index) => {{
        const content = String(message && message.content ? message.content : '').toLowerCase();
        if (content.includes(query)) {{
          matches.push(index);
        }}
      }});
      return matches;
    }}
    function folderLabel(folderId) {{
      if (!folderId) return '';
      const folder = state.folders.find((item) => item.id === folderId);
      return folder ? (folder.name || folder.id || folderId) : folderId;
    }}
    function suggestConversationTitle(text) {{
      const source = String(text || '').replace(/\\s+/g, ' ').trim();
      if (!source) return 'New chat';
      const clean = source.replace(/^[\\s\\-_,.:;]+|[\\s\\-_,.:;]+$/g, '');
      if (!clean) return 'New chat';
      const words = clean.split(/\\s+/).slice(0, 8);
      const title = words.join(' ').slice(0, 48).trim();
      if (!title) return 'New chat';
      return title.charAt(0).toUpperCase() + title.slice(1);
    }}
    function duplicateConversation(convo, options = {{}}) {{
      const baseId = convo.id ? `${{convo.id}}-copy` : `chat-copy`;
      const id = state.conversations.some((item) => item.id === baseId)
        ? `chat-${{Date.now()}}`
        : baseId;
      const suffix = options.suffix || 'Copy';
      const title = `${{convo.title || convo.id || 'Conversation'}} ${{suffix}}`.trim();
      const messages = Array.isArray(options.messages)
        ? options.messages.map((message) => ({{ ...message }}))
        : Array.isArray(convo.messages)
          ? convo.messages.map((message) => ({{ ...message }}))
          : [];
      const clone = {{
        ...convo,
        id,
        title,
        messages,
      }};
      state.conversations.unshift(clone);
      state.activeId = clone.id;
      state.currentModel = clone.model || state.currentModel || bootstrap.selectedModel || '';
      save();
      void saveConversation(clone);
      syncFields();
      renderAll();
      return clone;
    }}
    function cloneConversation(convo) {{
      return duplicateConversation(convo, {{ suffix: 'Copy' }});
    }}
    function branchConversation(convo, index) {{
      const messages = Array.isArray(convo.messages) ? convo.messages.slice(0, index + 1) : [];
      const clone = duplicateConversation(convo, {{ suffix: 'Branch', messages }});
      clone.messages = messages.map((message) => ({{ ...message }}));
      void saveConversation(clone);
      syncFields();
      renderAll();
      return clone;
    }}
    function deleteConversation(convo) {{
      const index = state.conversations.findIndex((item) => item.id === convo.id);
      if (index === -1) return;
      state.conversations.splice(index, 1);
      if (state.activeId === convo.id) {{
        state.activeId = state.conversations[0]?.id || '';
      }}
      save();
      void fetch('/api/ai/conversations', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: convo.id }}),
      }});
      if (state.activeId) {{
        syncFields();
      }}
      renderAll();
    }}
    function updateConversationState(convo, patch) {{
      const current = activeConversation() && activeConversation().id === convo.id ? activeConversation() : convo;
      Object.assign(current, patch);
      save();
      void saveConversation(current);
      renderAll();
    }}
    function newConversation() {{
      const id = `chat-${{Date.now()}}`;
      const model = state.currentModel || bootstrap.selectedModel || '';
      const agent = activeAgent();
      const convo = {{
        id,
        title: 'New chat',
        model,
        messages: [],
        systemPrompt: '',
        files: [],
        folderId: '',
        compareModels: [],
        agentId: agent ? agent.id : '',
      }};
      state.conversations.unshift(convo);
      state.activeId = id;
      save();
      void saveConversation(convo);
      syncFields();
      renderAll();
      els.prompt.focus();
      return convo;
    }}
    function syncFields() {{
      const convo = activeConversation() || newConversation();
      els.title.textContent = convo.title || 'New chat';
      els.conversationTitle.value = convo.title || '';
      els.systemPrompt.value = convo.systemPrompt || '';
      setSelectedFiles(convo.files || []);
      els.folderSelect.value = convo.folderId || '';
      els.modelSelect.value = convo.model || state.currentModel || bootstrap.selectedModel || '';
      if (convo.agentId) {{
        state.currentAgentId = convo.agentId;
      }}
      const compareModels = Array.isArray(convo.compareModels) ? convo.compareModels : [];
      if (compareModels.length) {{
        state.compareEnabled = true;
        state.compareModel = compareModels.find((model) => model && model !== convo.model) || compareModels[0] || state.compareModel;
      }}
      els.compareToggle.checked = state.compareEnabled;
      els.compareModelSelect.value = state.compareModel || '';
    }}
    function setSelectedFiles(fileIds) {{
      const values = new Set((fileIds || []).map(String));
      for (const option of els.fileSelect.options) {{
        option.selected = values.has(option.value);
      }}
    }}
    function selectedFiles() {{
      return Array.from(els.fileSelect.selectedOptions).map((option) => option.value);
    }}
    function extensionForFile(name) {{
      const parts = String(name || '').split('.');
      return parts.length > 1 ? parts.pop().toLowerCase() : '';
    }}
    function inferFileKind(file) {{
      if (file.type) return file.type;
      const ext = extensionForFile(file.name);
      if (ext) return ext;
      return 'file';
    }}
    function readLocalFile(file) {{
      return new Promise((resolve, reject) => {{
        const reader = new FileReader();
        reader.onerror = () => reject(new Error(`Unable to read ${{file.name}}`));
        reader.onload = () => resolve(reader.result);
        if (file.type.startsWith('text/') || file.type === 'application/json' || file.type === 'application/xml') {{
          reader.readAsText(file);
        }} else {{
          reader.readAsDataURL(file);
        }}
      }});
    }}
    async function uploadFilesCollection(fileCollection) {{
      const files = Array.from(fileCollection || []);
      if (!files.length) {{
        window.alert('Choose one or more files to upload first.');
        return;
      }}
      const attached = new Set(selectedFiles());
      const uploaded = [];
      for (const file of files) {{
        const content = await readLocalFile(file);
        const response = await fetch('/api/ai/files', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            name: file.name,
            content: typeof content === 'string' ? content : String(content),
            kind: inferFileKind(file),
            size: file.size,
            path: file.webkitRelativePath || file.name,
            description: `Uploaded from browser: ${{file.name}}`,
          }}),
        }});
        if (!response.ok) {{
          const data = await response.json().catch(() => ({{}}));
          throw new Error(data.error || response.statusText || `Upload failed for ${{file.name}}`);
        }}
        const data = await response.json();
        const fileItem = data.data || {{}};
        if (fileItem.id) {{
          uploaded.push(fileItem.id);
        }}
        state.files = [
          ...state.files.filter((item) => item.id !== fileItem.id),
          fileItem,
        ].sort((a, b) => String(a.id || '').localeCompare(String(b.id || '')));
      }}
      for (const fileId of uploaded) {{
        attached.add(fileId);
      }}
      setSelectedFiles(Array.from(attached));
      els.fileUpload.value = '';
      persistActiveFields();
      renderAll();
    }}
    async function uploadLocalFiles() {{
      await uploadFilesCollection(els.fileUpload.files || []);
    }}
    async function deleteFile(fileId) {{
      const response = await fetch('/api/ai/files', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: fileId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'File delete failed');
      }}
      state.files = state.files.filter((item) => item.id !== fileId);
      if (String(state.selectedFileId || '') === String(fileId || '')) {{
        state.selectedFileId = state.files[0]?.id || '';
      }}
      for (const convo of state.conversations) {{
        if (Array.isArray(convo.files)) {{
          convo.files = convo.files.filter((item) => item !== fileId);
        }}
      }}
      renderAll();
    }}
    async function deleteFolder(folderId) {{
      const response = await fetch('/api/ai/folders', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: folderId }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Workspace delete failed');
      }}
      state.folders = state.folders.filter((item) => item.id !== folderId);
      for (const convo of state.conversations) {{
        if (convo.folderId === folderId) {{
          convo.folderId = '';
        }}
      }}
      renderAll();
    }}
    function closeFilePreview() {{
      previewFile = null;
      els.filePreviewBackdrop.classList.remove('open');
      els.filePreviewBackdrop.setAttribute('aria-hidden', 'true');
    }}
    function openShortcutsHelp() {{
      els.shortcutsBackdrop.classList.add('open');
      els.shortcutsBackdrop.setAttribute('aria-hidden', 'false');
    }}
    function closeShortcutsHelp() {{
      els.shortcutsBackdrop.classList.remove('open');
      els.shortcutsBackdrop.setAttribute('aria-hidden', 'true');
    }}
    function openFilePreview(fileId) {{
      const file = state.files.find((item) => item.id === fileId) || null;
      if (!file) return;
      previewFile = file;
      const content = String(file.content || '').trim();
      const display = content
        ? (content.length > 12000 ? content.slice(0, 12000).trimEnd() + '\\n[truncated]' : content)
        : '(empty)';
      els.filePreviewTitle.textContent = file.name || file.id || 'File preview';
      els.filePreviewMeta.textContent = [
        file.id ? `ID: ${{file.id}}` : '',
        file.kind ? `Kind: ${{file.kind}}` : '',
        file.size ? `Size: ${{file.size}}` : '',
        file.path ? `Path: ${{file.path}}` : '',
        file.description ? `Description: ${{file.description}}` : '',
      ].filter(Boolean).join(' · ');
      if (String(file.kind || '').startsWith('image/') || /\\.(png|jpe?g|gif|webp|svg)$/i.test(String(file.path || file.name || ''))) {{
        const src = /^data:|^https?:|^blob:/.test(content) ? content : `data:${{file.kind || 'image/*'}};base64,${{content}}`;
        els.filePreviewBody.innerHTML = `
          <figure class="file-preview-figure">
            <img src="${{escapeHtml(src)}}" alt="${{escapeHtml(file.name || file.id || 'file preview')}}" />
            <figcaption>${{escapeHtml(file.name || file.id || 'Image preview')}}</figcaption>
          </figure>
          <pre>${{escapeHtml(display)}}</pre>
        `;
      }} else {{
        els.filePreviewBody.innerHTML = `<pre>${{escapeHtml(display)}}</pre>`;
      }}
      els.filePreviewBackdrop.classList.add('open');
      els.filePreviewBackdrop.setAttribute('aria-hidden', 'false');
    }}
    function persistActiveFields() {{
      const convo = activeConversation();
      if (!convo) return;
      convo.title = els.conversationTitle.value.trim() || 'New chat';
      convo.systemPrompt = els.systemPrompt.value;
      convo.model = els.modelSelect.value;
      convo.files = selectedFiles();
      convo.folderId = els.folderSelect.value || '';
      convo.agentId = els.agentSelect.value || convo.agentId || '';
      state.currentAgentId = convo.agentId || '';
      state.compareEnabled = !!els.compareToggle.checked;
      state.compareModel = els.compareModelSelect.value || '';
      convo.compareModels = state.compareEnabled && state.compareModel && state.compareModel !== convo.model
        ? [state.compareModel]
        : [];
      state.currentModel = convo.model;
      save();
      void saveConversation(convo);
    }}
    async function createFolderFromInput() {{
      const name = (els.folderName.value || '').trim();
      if (!name) {{
        window.alert('Enter a workspace name first.');
        return;
      }}
      const created = await saveFolder({{ name }});
      if (!created) {{
        throw new Error('Workspace save failed');
      }}
      state.folders = [
        ...state.folders.filter((item) => item.id !== created.id),
        created,
      ].sort((a, b) => String(a.id || '').localeCompare(String(b.id || '')));
      els.folderName.value = '';
      renderAll();
    }}
    function renderFolders() {{
      els.folderSelect.innerHTML = '';
      els.folderChips.innerHTML = '';
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No workspace';
      els.folderSelect.appendChild(option);
      for (const folder of state.folders) {{
        const opt = document.createElement('option');
        opt.value = folder.id;
        opt.textContent = `${{folder.name || folder.id}}${{folder.parentId ? ` · ${{folder.parentId}}` : ''}}`;
        els.folderSelect.appendChild(opt);
      }}
      const convo = activeConversation();
      els.folderSelect.value = convo && convo.folderId ? convo.folderId : '';
      if (!state.folders.length) {{
        els.folderChips.innerHTML = '<span class=\"muted\">No workspaces saved.</span>';
        return;
      }}
      for (const folder of state.folders) {{
        const row = document.createElement('div');
        row.className = 'folder-item';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = folder.name || folder.id;
        chip.title = folder.description || folder.systemPrompt || folder.id;
        chip.addEventListener('click', () => {{
          els.folderSelect.value = folder.id;
          persistActiveFields();
          renderAll();
        }});
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'danger';
        remove.title = 'Delete workspace';
        remove.textContent = '×';
        remove.addEventListener('click', async (event) => {{
          event.stopPropagation();
          if (window.confirm(`Delete ${{folder.name || folder.id}}?`)) {{
            try {{
              await deleteFolder(folder.id);
            }} catch (err) {{
              window.alert(String(err.message || err));
            }}
          }}
        }});
        row.appendChild(chip);
        row.appendChild(remove);
        els.folderChips.appendChild(row);
      }}
    }}
    function renderModels() {{
      els.modelSelect.innerHTML = '';
      els.compareModelSelect.innerHTML = '';
      for (const model of state.models) {{
        const opt = document.createElement('option');
        opt.value = model.id;
        opt.textContent = `${{model.id}} — ${{model.providerName || model.provider}}`;
        if (model.selected) opt.selected = true;
        els.modelSelect.appendChild(opt);

        const compareOpt = document.createElement('option');
        compareOpt.value = model.id;
        compareOpt.textContent = `${{model.id}} — ${{model.providerName || model.provider}}`;
        els.compareModelSelect.appendChild(compareOpt);
      }}
      if (!els.modelSelect.value && state.models.length) {{
        els.modelSelect.value = state.models[0].id;
      }}
      state.currentModel = els.modelSelect.value || state.currentModel;
      if (!els.compareModelSelect.value && state.models.length) {{
        const fallback = state.models.find((model) => model.id !== els.modelSelect.value)?.id || state.models[1]?.id || state.models[0]?.id || '';
        els.compareModelSelect.value = state.compareModel || fallback || '';
      }}
      state.compareModel = els.compareModelSelect.value || state.compareModel;
    }}
    function renderProviders() {{
      els.providerChips.innerHTML = '';
      if (!state.models.length) {{
        els.providerChips.innerHTML = '<span class=\"muted\">No provider models configured.</span>';
        return;
      }}
      for (const model of state.models) {{
        const row = document.createElement('div');
        row.className = 'provider-item';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = `${{model.providerName || model.provider || 'provider'}} · ${{model.id}}`;
        chip.title = model.baseUrl || model.provider || model.id;
        chip.addEventListener('click', () => {{
          els.modelSelect.value = model.id;
          state.currentModel = model.id;
          persistActiveFields();
          renderAll();
        }});
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'danger';
        remove.title = 'Delete provider model';
        remove.textContent = '×';
        remove.addEventListener('click', async (event) => {{
          event.stopPropagation();
          if (window.confirm(`Delete provider model ${{model.id}}?`)) {{
            try {{
              await deleteProviderModel(model.id);
            }} catch (err) {{
              window.alert(String(err.message || err));
            }}
          }}
        }});
        row.appendChild(chip);
        row.appendChild(remove);
        els.providerChips.appendChild(row);
      }}
    }}
    function combinedPromptTemplates() {{
      return [
        ...starterPromptTemplates.map((template) => ({{ ...template, starter: true }})),
        ...state.promptTemplates.map((template) => ({{ ...template, starter: false }})),
      ];
    }}
    function templateSearchValue() {{
      return String(state.templateSearch || els.templateSearch?.value || '').trim().toLowerCase();
    }}
    function templateMatchesFilter(template) {{
      const filter = String(state.templateFilter || 'all');
      if (filter === 'starters') return !!template.starter;
      if (filter === 'saved') return !template.starter;
      if (filter.startsWith('tag:')) {{
        const tag = filter.slice(4);
        return Array.isArray(template.tags) && template.tags.map((entry) => String(entry).toLowerCase()).includes(tag);
      }}
      return true;
    }}
    function templateMatchesSearch(template) {{
      const query = templateSearchValue();
      if (!query) return true;
      const haystack = [
        template.name,
        template.id,
        template.description,
        template.content,
        Array.isArray(template.tags) ? template.tags.join(' ') : '',
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(query);
    }}
    function templateCategoryList() {{
      const tags = new Set();
      for (const template of combinedPromptTemplates()) {{
        for (const tag of Array.isArray(template.tags) ? template.tags : []) {{
          if (tag) tags.add(String(tag).toLowerCase());
        }}
      }}
      return [
        {{ id: 'all', label: 'All' }},
        {{ id: 'starters', label: 'Starters' }},
        {{ id: 'saved', label: 'Saved' }},
        ...Array.from(tags).sort().map((tag) => ({{ id: `tag:${{tag}}`, label: `#${{tag}}` }})),
      ];
    }}
    function templatePreviewText(template) {{
      const source = String(template.description || template.content || '').trim();
      if (!source) return 'No preview available.';
      return source.length > 140 ? `${{source.slice(0, 137).trimEnd()}}...` : source;
    }}
    function copyCurrentSystemPrompt() {{
      return copyText(els.systemPrompt.value || '');
    }}
    function compareTemplateDiff(template) {{
      const current = String(els.systemPrompt.value || '').trim();
      const candidate = String(template.content || '').trim();
      if (!current && !candidate) return 'No prompt content to compare.';
      const currentLines = current.split(/\n+/).map((line) => line.trim()).filter(Boolean);
      const candidateLines = candidate.split(/\n+/).map((line) => line.trim()).filter(Boolean);
      const added = candidateLines.filter((line) => !currentLines.includes(line));
      const removed = currentLines.filter((line) => !candidateLines.includes(line));
      const shared = candidateLines.filter((line) => currentLines.includes(line));
      const parts = [];
      parts.push(`Shared lines: ${{shared.length}}`);
      if (added.length) parts.push(`Added preview:\n${{added.slice(0, 6).map((line) => `+ ${{line}}`).join('\n')}}`);
      if (removed.length) parts.push(`Removed preview:\n${{removed.slice(0, 6).map((line) => `- ${{line}}`).join('\n')}}`);
      if (!added.length && !removed.length) parts.push('The selected template matches the current prompt.');
      return parts.join('\n\n');
    }}
    function setTemplateDrawerOpen(open) {{
      state.templateDrawerOpen = Boolean(open);
      if (els.templateDrawer) {{
        els.templateDrawer.classList.toggle('open', state.templateDrawerOpen);
        els.templateDrawer.setAttribute('aria-hidden', state.templateDrawerOpen ? 'false' : 'true');
      }}
      renderTemplateGallery();
    }}
    function setTemplateFilter(filter) {{
      state.templateFilter = filter;
      save();
      renderTemplateGallery();
    }}
    function renderTemplateGallery() {{
      if (!els.templateGalleryList || !els.templateGalleryTabs) return;
      if (els.templateSearch && els.templateSearch.value !== state.templateSearch) {{
        els.templateSearch.value = state.templateSearch || '';
      }}
      const templates = combinedPromptTemplates()
        .filter(templateMatchesFilter)
        .filter(templateMatchesSearch);
      const categories = templateCategoryList();
      els.templateGalleryTabs.innerHTML = '';
      for (const category of categories) {{
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'secondary' + (String(state.templateFilter || 'all') === category.id ? ' active' : '');
        button.textContent = category.label;
        button.addEventListener('click', () => {{
          state.templateFilter = category.id;
          save();
          renderTemplateGallery();
        }});
        els.templateGalleryTabs.appendChild(button);
      }}
      els.templateGalleryList.innerHTML = '';
      if (!templates.length) {{
        els.templateGalleryList.innerHTML = '<div class=\"muted\">No templates match the current search or category.</div>';
      }} else {{
        for (const template of templates) {{
          const card = document.createElement('article');
          card.className = 'template-gallery-card' + (state.templateCompareId === template.id ? ' active' : '');
          const head = document.createElement('div');
          head.className = 'template-head';
          const heading = document.createElement('div');
          heading.className = 'stack';
          heading.style.gap = '4px';
          const title = document.createElement('h4');
          title.textContent = template.name || template.id;
          const meta = document.createElement('div');
          meta.className = 'meta';
          meta.textContent = [
            template.starter ? 'Starter' : 'Saved',
            template.id,
            Array.isArray(template.tags) && template.tags.length ? template.tags.map((tag) => `#${{tag}}`).join(' ') : '',
          ]
            .filter(Boolean)
            .join(' · ');
          heading.appendChild(title);
          heading.appendChild(meta);
          const badge = document.createElement('span');
          badge.className = 'pill';
          badge.textContent = template.starter ? 'Starter' : 'Saved';
          head.appendChild(heading);
          head.appendChild(badge);
          const preview = document.createElement('div');
          preview.className = 'preview';
          preview.textContent = templatePreviewText(template);
          const actions = document.createElement('div');
          actions.className = 'actions';
          const use = document.createElement('button');
          use.type = 'button';
          use.className = 'secondary';
          use.textContent = 'Use';
          use.addEventListener('click', () => {{
            applyTemplateContent(template);
            renderAll();
          }});
          const append = document.createElement('button');
          append.type = 'button';
          append.className = 'secondary';
          append.textContent = 'Append';
          append.addEventListener('click', () => {{
            applyTemplateContent(template, 'prompt');
            renderAll();
          }});
          const copy = document.createElement('button');
          copy.type = 'button';
          copy.className = 'secondary';
          copy.textContent = 'Copy';
          copy.addEventListener('click', async () => {{
            await copyText(template.content || '');
          }});
          const compare = document.createElement('button');
          compare.type = 'button';
          compare.className = 'secondary';
          compare.textContent = 'Compare';
          compare.addEventListener('click', () => {{
            state.templateCompareId = template.id;
            save();
            renderTemplateGallery();
          }});
          actions.appendChild(use);
          actions.appendChild(append);
          actions.appendChild(copy);
          actions.appendChild(compare);
          if (!template.starter) {{
            const edit = document.createElement('button');
            edit.type = 'button';
            edit.className = 'secondary';
            edit.textContent = 'Edit';
            edit.addEventListener('click', () => {{
              editingTemplateId = template.id;
              els.templateName.value = template.name || template.id || '';
              els.systemPrompt.value = template.content || '';
              renderAll();
            }});
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'danger';
            remove.textContent = 'Delete';
            remove.addEventListener('click', async () => {{
              if (window.confirm(`Delete ${{template.name || template.id}}?`)) {{
                await deletePromptTemplate(template);
              }}
            }});
            actions.appendChild(edit);
            actions.appendChild(remove);
          }}
          card.appendChild(head);
          card.appendChild(preview);
          card.appendChild(actions);
          els.templateGalleryList.appendChild(card);
        }}
      }}
      const current = String(els.systemPrompt.value || '').trim();
      const selected = combinedPromptTemplates().find((template) => template.id === state.templateCompareId) || templates[0] || combinedPromptTemplates()[0] || null;
      els.templateCompareCurrent.textContent = current || 'No system prompt set.';
      els.templateCompareSelected.textContent = selected
        ? `${{selected.name || selected.id}}\\n\\n${{selected.content || 'No template content.'}}`
        : 'Select a template to compare it here.';
      els.templateCompareDiff.textContent = selected
        ? compareTemplateDiff(selected)
        : 'Select a template to see a summary.';
      els.templateCompareCopyCurrent.disabled = !current;
      els.templateCompareCopySelected.disabled = !selected;
      els.templateCompareApplySelected.disabled = !selected;
    }}
    const starterPromptTemplates = [
      {{
        id: 'starter-coding-assistant',
        name: 'Coding assistant',
        description: 'Sharp debugging, refactoring, and implementation help.',
        content: 'You are a precise coding assistant. Explain tradeoffs, surface risks, and keep changes practical and testable.',
        tags: ['starter', 'code'],
      }},
      {{
        id: 'starter-research-analyst',
        name: 'Research analyst',
        description: 'Structured synthesis with evidence and next steps.',
        content: 'You are a research analyst. Summarize findings, cite assumptions, and separate facts from inference.',
        tags: ['starter', 'research'],
      }},
      {{
        id: 'starter-product-planner',
        name: 'Product planner',
        description: 'Turn rough ideas into clear, sequenced delivery plans.',
        content: 'You are a product planner. Break work into phases, highlight dependencies, and keep the response grounded in execution.',
        tags: ['starter', 'planning'],
      }},
    ];
    function applyTemplateContent(template, mode = 'system') {{
      if (!template) return;
      if (mode === 'prompt') {{
        const content = String(template.content || '').trim();
        const current = String(els.prompt.value || '').trim();
        els.prompt.value = current ? `${{current}}\\n\\n${{content}}` : content;
        els.prompt.focus();
        return;
      }}
      setSystemPromptFromContent(template.content || '');
      els.templateName.value = template.name || template.id || '';
    }}
    function renderTemplates() {{
      const templates = combinedPromptTemplates();
      els.templateChips.innerHTML = '';
      if (!templates.length) {{
        els.templateChips.innerHTML = '<span class=\"muted\">No prompt templates saved.</span>';
        return;
      }}
      for (const template of templates.slice(0, 4)) {{
        const item = document.createElement('div');
        item.className = `template-item ${{template.starter ? 'starter' : 'saved'}}`;
        const titleRow = document.createElement('div');
        titleRow.className = 'template-title';
        const left = document.createElement('div');
        left.className = 'stack';
        left.style.gap = '4px';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = template.name || template.id;
        chip.title = template.content || '';
        chip.addEventListener('click', () => {{
          applyTemplateContent(template);
          renderAll();
        }});
        const meta = document.createElement('div');
        meta.className = 'hint';
        meta.textContent = template.starter ? 'Starter template' : `Saved template · ${{template.id}}`;
        left.appendChild(chip);
        left.appendChild(meta);
        const badge = document.createElement('span');
        badge.className = 'pill';
        badge.textContent = template.starter ? 'Starter' : 'Saved';
        titleRow.appendChild(left);
        titleRow.appendChild(badge);
        const preview = document.createElement('div');
        preview.className = 'template-preview';
        preview.textContent = templatePreviewText(template);
        const actions = document.createElement('div');
        actions.className = 'template-actions';
        const use = document.createElement('button');
        use.type = 'button';
        use.className = 'secondary';
        use.textContent = 'Use';
        use.title = 'Load into the system prompt';
        use.addEventListener('click', () => {{
          applyTemplateContent(template);
          renderAll();
        }});
        const append = document.createElement('button');
        append.type = 'button';
        append.className = 'secondary';
        append.textContent = 'Insert';
        append.title = 'Append to the prompt composer';
        append.addEventListener('click', () => {{
          applyTemplateContent(template, 'prompt');
          renderAll();
        }});
        actions.appendChild(use);
        actions.appendChild(append);
        if (!template.starter) {{
          const edit = document.createElement('button');
          edit.type = 'button';
          edit.className = 'secondary';
          edit.title = 'Edit template';
          edit.textContent = 'Edit';
          edit.addEventListener('click', () => {{
            editingTemplateId = template.id;
            els.templateName.value = template.name || template.id || '';
            els.systemPrompt.value = template.content || '';
            renderAll();
          }});
          const remove = document.createElement('button');
          remove.type = 'button';
          remove.className = 'danger';
          remove.title = 'Delete template';
          remove.textContent = 'Delete';
          remove.addEventListener('click', async (event) => {{
            event.stopPropagation();
            if (window.confirm(`Delete ${{template.name || template.id}}?`)) {{
              await deletePromptTemplate(template);
            }}
          }});
          actions.appendChild(edit);
          actions.appendChild(remove);
        }}
        item.appendChild(titleRow);
        item.appendChild(preview);
        item.appendChild(actions);
        els.templateChips.appendChild(item);
      }}
      renderTemplateGallery();
    }}
    function fileSummary(file) {{
      const parts = [];
      if (file.kind) parts.push(file.kind);
      if (file.size) parts.push(`${{file.size}} byte(s)`);
      if (file.path) parts.push(file.path);
      if (Array.isArray(file.tags) && file.tags.length) parts.push(file.tags.join(', '));
      return parts.join(' · ');
    }}
    function selectedFileRecord() {{
      return (state.files || []).find((item) => String(item.id || '') === String(state.selectedFileId || '')) || null;
    }}
    function filesExportPayload() {{
      return JSON.stringify({{ files: state.files || [] }}, null, 2) + '\\n';
    }}
    async function importFilesFromFile() {{
      const file = els.fileImportFile && els.fileImportFile.files ? els.fileImportFile.files[0] : null;
      if (!file) {{
        window.alert('Select a file registry JSON file first.');
        return;
      }}
      const content = await file.text();
      const response = await fetch('/api/ai/files', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'import', content }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'File import failed');
      }}
      await response.json();
      await refreshFiles();
      if (!state.selectedFileId && state.files.length) {{
        state.selectedFileId = state.files[0].id || '';
      }}
      renderAll();
    }}
    async function exportFilesToFile() {{
      const response = await fetch('/api/ai/files', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'export' }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'File export failed');
      }}
      const data = await response.json();
      downloadText('files.json', String(data.data && data.data.content || filesExportPayload()), 'application/json;charset=utf-8');
    }}
    async function refreshFiles() {{
      try {{
        const response = await fetch('/api/ai/files');
        if (!response.ok) return;
        const data = await response.json();
        state.files = Array.isArray(data.data) ? data.data : [];
      }} catch (err) {{
        return;
      }}
    }}
    async function cloneFileFromSelection() {{
      const file = selectedFileRecord();
      if (!file) {{
        window.alert('Select a file first.');
        return;
      }}
      const response = await fetch('/api/ai/files', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'clone', id: file.id }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'File clone failed');
      }}
      const data = await response.json();
      await refreshFiles();
      state.selectedFileId = data.data && data.data.file && data.data.file.id ? data.data.file.id : state.selectedFileId;
      renderAll();
    }}
    function renderFiles() {{
      els.fileSelect.innerHTML = '';
      els.fileChips.innerHTML = '';
      els.selectedFileChips.innerHTML = '';
      if (els.fileSearch && els.fileSearch.value !== state.fileSearch) {{
        els.fileSearch.value = state.fileSearch || '';
      }}
      const query = String(state.fileSearch || '').trim().toLowerCase();
      const visibleFiles = (state.files || []).filter((file) => {{
        if (!query) return true;
        return [file.id, file.name, file.kind, file.path, file.description, file.content]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(query))
          || (Array.isArray(file.tags) && file.tags.some((tag) => String(tag).toLowerCase().includes(query)));
      }});
      if (!visibleFiles.length) {{
        els.fileChips.innerHTML = '<span class=\"muted\">No files in registry.</span>';
        els.selectedFileMeta.textContent = 'No attachments selected.';
        return;
      }}
      const selectedFile = visibleFiles.find((file) => String(file.id || '') === String(state.selectedFileId || '')) || visibleFiles[0];
      state.selectedFileId = selectedFile && selectedFile.id ? selectedFile.id : state.selectedFileId;
      const convo = activeConversation();
      const activeFiles = new Set((convo && convo.files) || []);
      const activeCount = activeFiles.size;
      els.selectedFileMeta.textContent = activeCount
        ? `${{activeCount}} attachment(s) selected.`
        : 'No attachments selected.';
      for (const file of visibleFiles) {{
        const option = document.createElement('option');
        option.value = file.id;
        option.textContent = `${{file.name || file.id}}${{file.kind ? ` · ${{file.kind}}` : ''}}`;
        if (activeFiles.has(file.id)) option.selected = true;
        els.fileSelect.appendChild(option);
      }}
      for (const fileId of activeFiles) {{
        const file = state.files.find((item) => item.id === fileId);
        if (!file) continue;
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = file.name || file.id;
        chip.title = `${{fileSummary(file) || file.description || file.kind || file.id}}. Click to remove from attachments.`;
        chip.addEventListener('click', () => {{
          const next = new Set(selectedFiles());
          next.delete(file.id);
          setSelectedFiles(Array.from(next));
          persistActiveFields();
          renderAll();
        }});
        els.selectedFileChips.appendChild(chip);
      }}
      for (const file of visibleFiles) {{
        const row = document.createElement('div');
        row.className = 'file-item';
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip' + (String(file.id || '') === String(selectedFile.id || '') ? ' active' : '');
        chip.textContent = file.name || file.id;
        chip.title = fileSummary(file) || file.description || file.kind || file.id;
        chip.addEventListener('click', () => {{
          state.selectedFileId = file.id || '';
          const next = new Set(selectedFiles());
          if (next.has(file.id)) {{
            next.delete(file.id);
          }} else {{
            next.add(file.id);
          }}
          setSelectedFiles(Array.from(next));
          persistActiveFields();
          renderAll();
        }});
        const preview = document.createElement('button');
        preview.type = 'button';
        preview.className = 'secondary';
        preview.title = 'Preview file';
        preview.textContent = 'Preview';
        preview.addEventListener('click', (event) => {{
          event.stopPropagation();
          state.selectedFileId = file.id || '';
          openFilePreview(file.id);
        }});
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'danger';
        remove.title = 'Delete file';
        remove.textContent = '×';
        remove.addEventListener('click', async (event) => {{
          event.stopPropagation();
          if (window.confirm(`Delete ${{file.name || file.id}}?`)) {{
            try {{
              await deleteFile(file.id);
            }} catch (err) {{
              window.alert(String(err.message || err));
            }}
          }}
        }});
        const shareMd = document.createElement('button');
        shareMd.type = 'button';
        shareMd.className = 'secondary';
        shareMd.textContent = 'Share MD';
        shareMd.addEventListener('click', async (event) => {{
          event.stopPropagation();
          await downloadSharedItem('files', file, 'md');
        }});
        const shareHtml = document.createElement('button');
        shareHtml.type = 'button';
        shareHtml.className = 'secondary';
        shareHtml.textContent = 'Share HTML';
        shareHtml.addEventListener('click', async (event) => {{
          event.stopPropagation();
          await downloadSharedItem('files', file, 'html');
        }});
        const shareJson = document.createElement('button');
        shareJson.type = 'button';
        shareJson.className = 'secondary';
        shareJson.textContent = 'Share JSON';
        shareJson.addEventListener('click', async (event) => {{
          event.stopPropagation();
          await downloadSharedItem('files', file, 'json');
        }});
        row.appendChild(chip);
        row.appendChild(preview);
        row.appendChild(remove);
        row.appendChild(shareMd);
        row.appendChild(shareHtml);
        row.appendChild(shareJson);
        const clone = document.createElement('button');
        clone.type = 'button';
        clone.className = 'secondary';
        clone.textContent = 'Clone';
        clone.title = 'Clone file';
        clone.addEventListener('click', async (event) => {{
          event.stopPropagation();
          state.selectedFileId = file.id || '';
          try {{
            const response = await fetch('/api/ai/files', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ action: 'clone', id: file.id }}),
            }});
            if (!response.ok) {{
              const data = await response.json().catch(() => ({{}}));
              throw new Error(data.error || response.statusText || 'File clone failed');
            }}
            const data = await response.json();
            await refreshFiles();
            state.selectedFileId = data.data && data.data.file && data.data.file.id ? data.data.file.id : state.selectedFileId;
            renderAll();
          }} catch (err) {{
            window.alert(String(err.message || err));
          }}
        }});
        row.appendChild(clone);
        row.appendChild(document.createElement('div')).textContent = fileSummary(file) || file.description || 'File';
        els.fileChips.appendChild(row);
      }}
    }}
    function renderConversationList() {{
      els.conversationList.innerHTML = '';
      const query = (els.conversationSearch.value || '').trim().toLowerCase();
      const visible = state.conversations
        .filter((item) => {{
          if (!query) return true;
          return [item.title, item.id, item.model]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(query));
        }})
        .filter((item) => {{
          if (state.conversationFilter === 'pinned') return !!item.pinned;
          if (state.conversationFilter === 'archived') return !!item.archived;
          return true;
        }});
      visible.sort((a, b) => {{
        const rank = (item) => {{
          if (item.id === state.activeId) return 0;
          if (item.pinned) return 1;
          if (item.archived) return 3;
          return 2;
        }};
        const diff = rank(a) - rank(b);
        if (diff) return diff;
        return String(a.title || a.id || '').localeCompare(String(b.title || b.id || ''));
      }});
      if (!visible.length) {{
        els.conversationList.innerHTML = `<span class=\"muted\">${{query ? 'No chats match your search.' : 'No saved chats yet.'}}</span>`;
        return;
      }}
      for (const convo of visible) {{
        const item = document.createElement('div');
        item.className = 'conversation-item' + (convo.id === state.activeId ? ' active' : '');
        const summary = [
          convo.folderId ? `workspace: ${{folderLabel(convo.folderId)}}` : '',
          convo.pinned ? 'pinned' : '',
          convo.archived ? 'archived' : '',
          convo.model || bootstrap.selectedModel || '',
          convo.systemPrompt ? 'prompt' : '',
          convo.files && convo.files.length ? `${{convo.files.length}} file(s)` : '',
        ]
          .filter(Boolean)
          .join(' · ');
        item.innerHTML = `
          <div class=\"conversation-item-body\">
            <div>
              <button type=\"button\" class=\"conversation-item-select\">
                <strong>${{escapeHtml(convo.title || convo.id)}}</strong>
              </button>
              <small>${{escapeHtml(summary || convo.id)}}</small>
            </div>
            <div class=\"conversation-item-actions\">
              <button type=\"button\" data-action=\"pin\">${{convo.pinned ? 'Unpin' : 'Pin'}}</button>
              <button type=\"button\" data-action=\"archive\">${{convo.archived ? 'Unarchive' : 'Archive'}}</button>
              <button type=\"button\" data-action=\"clone\">Clone</button>
              <button type=\"button\" class=\"danger\" data-action=\"delete\">Delete</button>
            </div>
          </div>
        `;
        item.querySelector('.conversation-item-select')?.addEventListener('click', (event) => {{
          event.stopPropagation();
          state.activeId = convo.id;
          if (convo.model) state.currentModel = convo.model;
          save();
          syncFields();
          renderAll();
        }});
        item.querySelector('[data-action=\"clone\"]')?.addEventListener('click', (event) => {{
          event.stopPropagation();
          cloneConversation(convo);
        }});
        item.querySelector('[data-action=\"pin\"]')?.addEventListener('click', (event) => {{
          event.stopPropagation();
          updateConversationState(convo, {{ pinned: !convo.pinned }});
        }});
        item.querySelector('[data-action=\"archive\"]')?.addEventListener('click', (event) => {{
          event.stopPropagation();
          updateConversationState(convo, {{ archived: !convo.archived }});
        }});
        item.querySelector('[data-action=\"delete\"]')?.addEventListener('click', (event) => {{
          event.stopPropagation();
          if (window.confirm(`Delete ${{convo.title || convo.id}}?`)) {{
            deleteConversation(convo);
          }}
        }});
        els.conversationList.appendChild(item);
      }}
    }}
    function setConversationFilter(filter) {{
      state.conversationFilter = filter;
      els.conversationFilterAll.classList.toggle('active', filter === 'all');
      els.conversationFilterPinned.classList.toggle('active', filter === 'pinned');
      els.conversationFilterArchived.classList.toggle('active', filter === 'archived');
      save();
      renderAll();
    }}
    function escapeHtml(value) {{
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('\"', '&quot;')
        .replaceAll(\"'\", '&#39;');
    }}
    function renderInline(text) {{
      return escapeHtml(text)
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>')
        .replace(/\\*([^*]+)\\*/g, '<em>$1</em>')
        .replace(/~~([^~]+)~~/g, '<del>$1</del>')
        .replace(/\\$(?!\\s)([^$\\n]+?)\\$(?!\\d)/g, '<span class=\"math\">$1</span>')
        .replace(
          /\\[([^\\]]+)\\]\\(([^)]+)\\)/g,
          (_, label, href) =>
            '<a href=\"' +
            escapeHtml(href) +
            '\" target=\"_blank\" rel=\"noreferrer\">' +
            label +
            '</a>'
        );
    }}
    function renderMarkdown(value) {{
      const source = String(value || '').replace(/\\r\\n/g, '\\n');
      const lines = source.split('\\n');
      const blocks = [];
      let paragraph = [];
      let listType = '';
      let listItems = [];
      let inCode = false;
      let codeLang = '';
      let codeLines = [];
      let inTable = false;
      let tableHeader = [];
      let tableRows = [];
      const flushTable = () => {{
        if (!inTable) return;
        const headerHtml = tableHeader.map((cell) => '<th>' + renderInline(cell.trim()) + '</th>').join('');
        const rowsHtml = tableRows
          .map((row) => '<tr>' + row.map((cell) => '<td>' + renderInline(cell.trim()) + '</td>').join('') + '</tr>')
          .join('');
        blocks.push('<table><thead><tr>' + headerHtml + '</tr></thead><tbody>' + rowsHtml + '</tbody></table>');
        inTable = false;
        tableHeader = [];
        tableRows = [];
      }};
      const flushParagraph = () => {{
        if (!paragraph.length) return;
        blocks.push('<p>' + renderInline(paragraph.join(' ').trim()) + '</p>');
        paragraph = [];
      }};
      const flushList = () => {{
        if (!listItems.length) return;
        const tag = listType === 'ol' ? 'ol' : 'ul';
        blocks.push('<' + tag + '>' + listItems.join('') + '</' + tag + '>');
        listType = '';
        listItems = [];
      }};
      const flushCode = () => {{
        const encoded = encodeURIComponent(codeLines.join('\\n'));
        blocks.push(
          '<div class=\"code-block\">' +
            '<button type=\"button\" class=\"secondary code-copy\" data-code-copy=\"' + encoded + '\">Copy code</button>' +
            '<pre><code' +
              (codeLang ? ' class=\"language-' + escapeHtml(codeLang) + '\"' : '') +
              '>' +
              escapeHtml(codeLines.join('\\n')) +
            '</code></pre>' +
          '</div>'
        );
          codeLang = '';
          codeLines = [];
      }};
      const flushBlockState = () => {{
        flushParagraph();
        flushList();
        flushTable();
      }};
      for (const rawLine of lines) {{
        const line = rawLine.trimEnd();
        const fence = line.match(/^```(.*)$/);
        if (fence) {{
          if (inCode) {{
            flushCode();
            inCode = false;
          }} else {{
            flushBlockState();
            inCode = true;
            codeLang = fence[1].trim();
          }}
          continue;
        }}
        if (inCode) {{
          codeLines.push(rawLine);
          continue;
        }}
        if (!line.trim()) {{
          flushBlockState();
          continue;
        }}
        if (/^(?:---|\\*\\*\\*|___)$/.test(line.trim())) {{
          flushBlockState();
          blocks.push('<hr>');
          continue;
        }}
        const tableDivider = /^[|]?(?:\\s*:?-{3,}:?\\s*[|])+\\s*:?-{3,}:?\\s*[|]?$/.test(line);
        const tableRow = /^\\s*[|].*[|]\\s*$/.test(line);
        if (tableRow) {{
          const cells = line.trim().replace(/^[|]/, '').replace(/[|]$/, '').split('|');
          if (!inTable) {{
            flushBlockState();
            inTable = true;
            tableHeader = cells;
            tableRows = [];
          }} else if (!tableHeader.length) {{
            tableHeader = cells;
          }} else if (tableDivider) {{
            continue;
          }} else {{
            tableRows.push(cells);
          }}
          continue;
        }}
        if (inTable && !tableDivider && !tableRow) {{
          flushTable();
        }}
        const heading = line.match(/^(#{1,4})\\s+(.*)$/);
        if (heading) {{
          flushBlockState();
          const level = heading[1].length;
          blocks.push('<h' + level + '>' + renderInline(heading[2].trim()) + '</h' + level + '>');
          continue;
        }}
        const quote = line.match(/^>\\s?(.*)$/);
        if (quote) {{
          flushBlockState();
          blocks.push('<blockquote>' + renderInline(quote[1].trim()) + '</blockquote>');
          continue;
        }}
        const unordered = line.match(/^[-*+]\\s+(.*)$/);
        if (unordered) {{
          flushParagraph();
          if (listType && listType !== 'ul') {{
            flushList();
          }}
          listType = 'ul';
          const task = unordered[1].match(/^\\[( |x|X)\\]\\s+(.*)$/);
          if (task) {{
            const checked = task[1].toLowerCase() === 'x';
            listItems.push(
              '<li class=\"task-item\"><span class=\"task-box\">' +
                (checked ? '☑' : '☐') +
                '</span> ' +
                renderInline(task[2].trim()) +
                '</li>'
            );
          }} else {{
            listItems.push('<li>' + renderInline(unordered[1].trim()) + '</li>');
          }}
          continue;
        }}
        const ordered = line.match(/^\\d+[.)]\\s+(.*)$/);
        if (ordered) {{
          flushParagraph();
          if (listType && listType !== 'ol') {{
            flushList();
          }}
          listType = 'ol';
          listItems.push('<li>' + renderInline(ordered[1].trim()) + '</li>');
          continue;
        }}
        flushList();
        paragraph.push(line.trim());
      }}
      if (inCode) {{
        flushCode();
      }}
      flushBlockState();
      return blocks.join('');
    }}
    function applySearchHighlights(root, query) {{
      const normalized = String(query || '').trim().toLowerCase();
      if (!normalized || !root) return;
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const textNodes = [];
      while (walker.nextNode()) {{
        const node = walker.currentNode;
        const parent = node.parentElement;
        if (!parent) continue;
        if (parent.closest('code, pre, a, button, textarea')) continue;
        if (!node.nodeValue || !node.nodeValue.trim()) continue;
        textNodes.push(node);
      }}
      for (const node of textNodes) {{
        const value = node.nodeValue || '';
        const lower = value.toLowerCase();
        const index = lower.indexOf(normalized);
        if (index === -1) continue;
        const frag = document.createDocumentFragment();
        let offset = 0;
        while (offset < value.length) {{
          const found = value.toLowerCase().indexOf(normalized, offset);
          if (found === -1) {{
            frag.appendChild(document.createTextNode(value.slice(offset)));
            break;
          }}
          if (found > offset) {{
            frag.appendChild(document.createTextNode(value.slice(offset, found)));
          }}
          const mark = document.createElement('span');
          mark.className = 'search-hit';
          mark.textContent = value.slice(found, found + normalized.length);
          frag.appendChild(mark);
          offset = found + normalized.length;
        }}
        node.parentNode.replaceChild(frag, node);
      }}
    }}
    function renderMessages() {{
      const convo = activeConversation();
      els.chat.innerHTML = '';
        if (!convo || !convo.messages || !convo.messages.length) {{
          const starterChips = starterPromptTemplates.map((template) => `
          <button type=\"button\" class=\"chip\" data-starter-template=\"${{escapeHtml(template.id)}}\">${{escapeHtml(template.name)}}</button>
        `).join('');
        els.chat.innerHTML = `
          <div class=\"chat-empty\">
            <div class=\"chat-empty-card\">
              <div class=\"eyebrow\">Ready for use</div>
              <h3>Open a model, load a template, or start a new conversation.</h3>
              <p>This workspace is already wired for prompts, files, agents, and history. Use the quick actions below to begin with one click.</p>
              <div class=\"chat-empty-actions\">
                <button type=\"button\" class=\"secondary\" id=\"chat-empty-focus\">Focus prompt</button>
                <button type=\"button\" class=\"secondary\" id=\"chat-empty-new\">New chat</button>
                <button type=\"button\" class=\"secondary\" id=\"chat-empty-shortcuts\">Shortcuts</button>
              </div>
              <div class=\"stack\">
                <div class=\"hint\">Starter templates</div>
                <div class=\"chips\" id=\"chat-empty-starters\">${{starterChips}}</div>
              </div>
              <div class=\"chat-empty-actions\">
                <button type=\"button\" class=\"secondary\" id=\"chat-empty-presets\">Add presets</button>
                <button type=\"button\" class=\"secondary\" id=\"chat-empty-templates\">Templates</button>
                <button type=\"button\" class=\"secondary\" id=\"chat-empty-files\">Upload files</button>
              </div>
            </div>
          </div>
        `;
        els.chat.querySelector('#chat-empty-focus')?.addEventListener('click', () => {{
          els.prompt.focus();
        }});
        els.chat.querySelector('#chat-empty-new')?.addEventListener('click', () => {{
          newConversation();
          renderAll();
        }});
        els.chat.querySelector('#chat-empty-shortcuts')?.addEventListener('click', () => {{
          openShortcutsHelp();
        }});
        els.chat.querySelector('#chat-empty-presets')?.addEventListener('click', async () => {{
          try {{
            await addProviderPresets();
          }} catch (err) {{
            window.alert(String(err.message || err));
          }}
        }});
        els.chat.querySelector('#chat-empty-templates')?.addEventListener('click', () => {{
          setTemplateDrawerOpen(true);
        }});
        els.chat.querySelector('#chat-empty-files')?.addEventListener('click', () => {{
          els.fileUpload?.click();
        }});
        els.chat.querySelectorAll('[data-starter-template]').forEach((button) => {{
          button.addEventListener('click', () => {{
            const template = starterPromptTemplates.find((item) => item.id === button.dataset.starterTemplate);
            if (!template) return;
            applyTemplateContent(template);
            renderAll();
          }});
        }});
        return;
      }}
      const searchQuery = currentMessageSearchQuery();
      messageSearchMatches = computeMessageSearchMatches(convo);
      const activeSearchIndex = messageSearchMatches.length
        ? Math.max(0, Math.min(messageSearchMatches.length - 1, state.messageSearchIndex || 0))
        : -1;
      convo.messages.forEach((message, index) => {{
        const block = document.createElement('article');
        block.className = `message ${{message.role || 'assistant'}}`;
        if (editingMessageIndex === index) {{
          block.classList.add('editing');
        }}
        if (messageSearchMatches.includes(index)) {{
          block.classList.add('search-hit');
          if (messageSearchMatches[activeSearchIndex] === index) {{
            block.classList.add('current');
          }}
        }}
        const role = message.role || 'assistant';
        const content = message.content || '';
        const header = document.createElement('div');
        header.className = 'message-header';
        const roleLabel = document.createElement('span');
        roleLabel.className = 'role';
        roleLabel.textContent = role;
        header.appendChild(roleLabel);
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        const copyButton = document.createElement('button');
        copyButton.type = 'button';
        copyButton.className = 'secondary';
        copyButton.textContent = 'Copy';
        copyButton.addEventListener('click', async () => {{
          await copyText(content);
        }});
        actions.appendChild(copyButton);
        if (role === 'assistant' && String(content || '').trim()) {{
          const speakButton = document.createElement('button');
          speakButton.type = 'button';
          speakButton.className = 'secondary';
          speakButton.textContent = 'Read aloud';
          speakButton.addEventListener('click', () => {{
            speakMessage(content);
          }});
          actions.appendChild(speakButton);
        }}
        if (convo.messages.length > 1) {{
          const forkButton = document.createElement('button');
          forkButton.type = 'button';
          forkButton.className = 'secondary';
          forkButton.textContent = 'Fork';
          forkButton.title = 'Fork conversation from this message';
          forkButton.addEventListener('click', () => {{
            branchConversation(convo, index);
          }});
          actions.appendChild(forkButton);
        }}
        if (role === 'user' && editingMessageIndex !== index) {{
          const editButton = document.createElement('button');
          editButton.type = 'button';
          editButton.className = 'secondary';
          editButton.textContent = 'Edit';
          editButton.addEventListener('click', () => {{
            beginEditMessage(index);
          }});
          actions.appendChild(editButton);
        }}
        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.className = 'danger';
        deleteButton.textContent = 'Delete';
        deleteButton.addEventListener('click', () => {{
          void deleteMessage(index);
        }});
        actions.appendChild(deleteButton);
        const retryButton = document.createElement('button');
        retryButton.type = 'button';
        retryButton.className = 'secondary';
        retryButton.textContent = 'Retry';
        retryButton.addEventListener('click', () => {{
          void retryFromMessage(index);
        }});
        actions.appendChild(retryButton);
        header.appendChild(actions);
        block.appendChild(header);
        if (editingMessageIndex === index) {{
          const editor = document.createElement('div');
          editor.className = 'message-editor';
          const textarea = document.createElement('textarea');
          textarea.value = editingMessageDraft;
          textarea.rows = 6;
          textarea.addEventListener('input', (event) => {{
            editingMessageDraft = event.target.value;
          }});
          const controls = document.createElement('div');
          controls.className = 'toolbar';
          const saveButton = document.createElement('button');
          saveButton.type = 'button';
          saveButton.textContent = 'Save';
          saveButton.addEventListener('click', () => {{
            saveEditedMessage(index);
          }});
          const cancelButton = document.createElement('button');
          cancelButton.type = 'button';
          cancelButton.className = 'secondary';
          cancelButton.textContent = 'Cancel';
          cancelButton.addEventListener('click', () => {{
            cancelEditMessage();
          }});
          controls.appendChild(saveButton);
          controls.appendChild(cancelButton);
          editor.appendChild(textarea);
          editor.appendChild(controls);
          block.appendChild(editor);
        }} else {{
          const isTyping = role === 'assistant' && message.streaming && index === convo.messages.length - 1;
          const body = isTyping
            ? '<div class=\"typing-indicator\" aria-live=\"polite\" aria-label=\"Assistant is typing\"><span>Assistant is typing</span><span class=\"typing-dots\" aria-hidden=\"true\"><span></span><span></span><span></span></span></div>'
            : role === 'user'
              ? `<p>${{escapeHtml(content).replace(/\\n/g, '<br>')}}</p>`
              : `<div class=\"message-content\">${{renderMarkdown(content)}}</div>`;
          const contentWrap = document.createElement('div');
          contentWrap.innerHTML = body;
          contentWrap.querySelectorAll('.code-copy').forEach((button) => {{
            button.addEventListener('click', async () => {{
              await copyText(decodeURIComponent(button.dataset.codeCopy || ''));
            }});
          }});
          applySearchHighlights(contentWrap, searchQuery);
          block.appendChild(contentWrap);
        }}
        els.chat.appendChild(block);
      }});
      if (searchQuery && activeSearchIndex !== -1) {{
        const targetIndex = messageSearchMatches[activeSearchIndex];
        const target = els.chat.querySelectorAll('article.message')[targetIndex];
        target?.scrollIntoView({{ block: 'nearest' }});
      }}
      els.chat.scrollTop = els.chat.scrollHeight;
      updateScrollLatestButton();
    }}
    function updateScrollLatestButton() {{
      if (!els.scrollLatest || !els.chat) return;
      const distanceFromBottom = els.chat.scrollHeight - els.chat.scrollTop - els.chat.clientHeight;
      els.scrollLatest.classList.toggle('visible', distanceFromBottom > 120);
    }}
    function estimateTokenCount(text) {{
      const value = String(text || '').trim();
      if (!value) return 0;
      return Math.max(1, Math.ceil(value.length / 4));
    }}
    function conversationUsageText(convo) {{
      if (!convo) return 'Token estimate: ~0';
      const usage = convo.usage;
      if (usage && typeof usage === 'object' && !Array.isArray(usage)) {{
        const promptTokens = Number(
          usage.prompt_tokens ?? usage.promptTokens ?? usage.input_tokens ?? usage.inputTokens
        );
        const completionTokens = Number(
          usage.completion_tokens ?? usage.completionTokens ?? usage.output_tokens ?? usage.outputTokens
        );
        const totalTokens = Number(usage.total_tokens ?? usage.totalTokens);
        const parts = [];
        if (Number.isFinite(promptTokens)) parts.push(`prompt ${{promptTokens}}`);
        if (Number.isFinite(completionTokens)) parts.push(`completion ${{completionTokens}}`);
        if (Number.isFinite(totalTokens)) parts.push(`total ${{totalTokens}}`);
        if (parts.length) {{
          return `Tokens: ${{parts.join(' · ')}}`;
        }}
      }}
      const transcriptParts = [];
      if (convo.systemPrompt) transcriptParts.push(String(convo.systemPrompt));
      for (const message of convo.messages || []) {{
        transcriptParts.push(String(message && message.content ? message.content : ''));
      }}
      const estimated = estimateTokenCount(transcriptParts.join('\n'));
      return `Token estimate: ~${{estimated}}`;
    }}
    function renderAll() {{
      persistActiveFields();
      applyTheme();
      setSidebarCollapsed(state.sidebarCollapsed);
      renderVoiceControls();
      renderFolders();
      renderConversationList();
      renderMessages();
      renderProviders();
      renderKnowledgeBases();
      renderAgentEditor(editingAgentId ? (els.agentEditorFolder.value || '') : (activeAgent() && activeAgent().folderId ? activeAgent().folderId : ''));
      renderAgents();
      renderSkills();
      renderMemories();
      renderNotes();
      renderArtifacts();
      renderWebSearch();
      renderTools();
      renderWebhooks();
      renderStatusPills();
      updateQueueStatus();
      const convo = activeConversation();
      if (els.workspaceModelCount) {{
        els.workspaceModelCount.textContent = `${{state.models.length}} model${{state.models.length === 1 ? '' : 's'}}`;
      }}
      if (els.workspaceTemplateCount) {{
        const totalTemplates = (state.promptTemplates || []).length + starterPromptTemplates.length;
        els.workspaceTemplateCount.textContent = `${{totalTemplates}} template${{totalTemplates === 1 ? '' : 's'}}`;
      }}
      if (els.workspaceChatCount) {{
        els.workspaceChatCount.textContent = `${{state.conversations.length}} chat${{state.conversations.length === 1 ? '' : 's'}}`;
      }}
      els.title.textContent = convo ? convo.title || 'New chat' : 'New chat';
      const searchSummary = messageSearchMatches.length
        ? `${{messageSearchMatches.length}} match(es)`
        : currentMessageSearchQuery()
          ? 'No matches'
          : 'No transcript search';
      els.meta.textContent = convo && convo.messages
        ? `${{convo.messages.length}} message(s) · ${{searchSummary}}`
        : `Ready. · ${{searchSummary}}`;
      els.usage.textContent = conversationUsageText(convo);
      els.messageSearchMeta.textContent = searchSummary;
      els.messageSearchPrev.disabled = !messageSearchMatches.length;
      els.messageSearchNext.disabled = !messageSearchMatches.length;
      setStreaming(Boolean(activeAbortController));
      updateScrollLatestButton();
    }}
    function downloadText(filename, content, mimeType) {{
      const blob = new Blob([content], {{ type: mimeType }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }}
    function downloadBlob(filename, blob) {{
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }}
    async function copyText(value) {{
      const text = String(value || '');
      try {{
        await navigator.clipboard.writeText(text);
      }} catch (err) {{
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', 'readonly');
        ta.style.position = 'absolute';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
      }}
    }}
    function beginEditMessage(index) {{
      const convo = activeConversation();
      if (!convo || !convo.messages || !convo.messages[index]) return;
      editingMessageIndex = index;
      editingMessageDraft = String(convo.messages[index].content || '');
      renderAll();
    }}
    function cancelEditMessage() {{
      editingMessageIndex = null;
      editingMessageDraft = '';
      renderAll();
    }}
    function saveEditedMessage(index) {{
      const convo = activeConversation();
      if (!convo || !convo.messages || !convo.messages[index]) return;
      const content = editingMessageDraft.trim();
      if (!content) {{
        window.alert('Message content cannot be empty.');
        return;
      }}
      convo.messages[index].content = content;
      convo.messages = convo.messages.slice(0, index + 1);
      editingMessageIndex = null;
      editingMessageDraft = '';
      void saveConversation(convo);
      renderAll();
    }}
    async function deleteMessage(index) {{
      const convo = activeConversation();
      if (!convo || !convo.messages || !convo.messages[index]) return;
      convo.messages.splice(index, 1);
      if (editingMessageIndex !== null) {{
        if (editingMessageIndex === index) {{
          editingMessageIndex = null;
          editingMessageDraft = '';
        }} else if (editingMessageIndex > index) {{
          editingMessageIndex -= 1;
        }}
      }}
      void saveConversation(convo);
      renderAll();
    }}
    async function retryFromMessage(index) {{
      const convo = activeConversation();
      if (!convo || !convo.messages || !convo.messages[index]) return;
      const message = convo.messages[index];
      const role = message.role || 'assistant';
      const text = String(message.content || '');
      convo.messages = convo.messages.slice(0, index);
      editingMessageIndex = null;
      editingMessageDraft = '';
      void saveConversation(convo);
      renderAll();
      if (role === 'assistant') {{
        const lastUser = [...convo.messages].reverse().find((item) => item && item.role === 'user');
        if (!lastUser) return;
        await sendMessage(String(lastUser.content || ''), {{ appendUser: false }});
        return;
      }}
      if (text) {{
        await sendMessage(text);
      }}
    }}
    function conversationTranscript(convo) {{
      const lines = [];
      lines.push(`# ${{convo.title || convo.id || 'Conversation'}}`);
      lines.push('');
      if (convo.model) lines.push(`- Model: ${{convo.model}}`);
      if (convo.systemPrompt) {{
        lines.push('- System prompt:');
        lines.push('');
        lines.push('```text');
        lines.push(convo.systemPrompt);
        lines.push('```');
      }}
      if (convo.files && convo.files.length) {{
        lines.push(`- Files: ${{convo.files.join(', ')}}`);
      }}
      lines.push('');
      for (const message of convo.messages || []) {{
        if (!message || !message.role) continue;
        lines.push(`## ${{message.role}}`);
        lines.push('');
        lines.push(String(message.content || '').trim() || '_empty_');
        lines.push('');
      }}
      return lines.join('\n').trim() + '\n';
    }}
    function conversationShareGPT(convo) {{
      const messages = [];
      if (convo.systemPrompt) {{
        messages.push({{ from: 'system', value: String(convo.systemPrompt) }});
      }}
      for (const message of convo.messages || []) {{
        if (!message || !message.role) continue;
        const from = message.role === 'user' ? 'human' : 'assistant';
        messages.push({{ from, value: String(message.content || '') }});
      }}
      return {{
        id: convo.id || 'chat',
        title: convo.title || convo.id || 'Conversation',
        model: convo.model || '',
        messages,
      }};
    }}
    function conversationShareSummary(convo) {{
      const parts = [];
      parts.push(convo.title || convo.id || 'Conversation');
      if (convo.model) parts.push(`Model: ${{convo.model}}`);
      if (convo.systemPrompt) parts.push(`System prompt: ${{convo.systemPrompt}}`);
      if (convo.files && convo.files.length) parts.push(`Files: ${{convo.files.join(', ')}}`);
      for (const message of convo.messages || []) {{
        if (!message || !message.role) continue;
        parts.push(`${{message.role}}: ${{String(message.content || '').trim()}}`);
      }}
      return parts.join('\n\n').trim();
    }}
    function wrapCanvasText(ctx, text, maxWidth) {{
      const source = String(text || '').replace(/\r\n/g, '\n');
      const paragraphs = source.split('\n');
      const lines = [];
      for (const paragraph of paragraphs) {{
        if (!paragraph.trim()) {{
          lines.push('');
          continue;
        }}
        const words = paragraph.split(/\\s+/);
        let line = '';
        for (const word of words) {{
          const next = line ? `${{line}} ${{word}}` : word;
          if (ctx.measureText(next).width <= maxWidth || !line) {{
            line = next;
          }} else {{
            lines.push(line);
            line = word;
          }}
        }}
        if (line) lines.push(line);
      }}
      return lines;
    }}
    function roundRect(ctx, x, y, width, height, radius) {{
      const r = Math.min(radius, width / 2, height / 2);
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + width, y, x + width, y + height, r);
      ctx.arcTo(x + width, y + height, x, y + height, r);
      ctx.arcTo(x, y + height, x, y, r);
      ctx.arcTo(x, y, x + width, y, r);
      ctx.closePath();
    }}
    async function copyConversation() {{
      const convo = activeConversation();
      if (!convo) return;
      await copyText(conversationTranscript(convo));
    }}
    async function shareConversationImage() {{
      const convo = activeConversation();
      if (!convo) return;
      const title = convo.title || convo.id || 'Conversation';
      const summary = conversationShareSummary(convo);
      const width = 1200;
      const padding = 48;
      const gutter = 24;
      const boxWidth = width - padding * 2;
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      if (!ctx) {{
        throw new Error('Canvas is not available in this browser.');
      }}
      const scale = Math.max(1, Math.floor(window.devicePixelRatio || 1));
      ctx.font = '700 34px Inter, system-ui, sans-serif';
      const titleLines = wrapCanvasText(ctx, title, boxWidth);
      ctx.font = '500 18px Inter, system-ui, sans-serif';
      const summaryLines = wrapCanvasText(ctx, summary, boxWidth);
      const messageBlocks = [];
      for (const message of convo.messages || []) {{
        const role = String(message.role || 'assistant');
        const content = String(message.content || '').trim() || '_empty_';
        ctx.font = '500 16px Inter, system-ui, sans-serif';
        const lines = wrapCanvasText(ctx, content, boxWidth - 48);
        messageBlocks.push({{
          role,
          lines: lines.length ? lines : [''],
          height: 44 + lines.length * 24 + 24,
        }});
      }}
      const titleHeight = titleLines.length * 38 + 8;
      const summaryHeight = summaryLines.length * 28 + (summaryLines.length ? 18 : 0);
      const messagesHeight = messageBlocks.reduce((total, block) => total + block.height + gutter, 0);
      const height = padding * 2 + titleHeight + summaryHeight + messagesHeight + 20;
      canvas.width = width * scale;
      canvas.height = height * scale;
      ctx.scale(scale, scale);
      ctx.fillStyle = '#0b1020';
      ctx.fillRect(0, 0, width, height);
      const gradient = ctx.createLinearGradient(0, 0, width, height);
      gradient.addColorStop(0, 'rgba(102, 227, 196, 0.18)');
      gradient.addColorStop(1, 'rgba(124, 156, 255, 0.12)');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = 'rgba(255,255,255,0.08)';
      ctx.lineWidth = 1;
      ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
      let y = padding;
      ctx.fillStyle = '#e5eefc';
      ctx.font = '700 34px Inter, system-ui, sans-serif';
      for (const line of titleLines) {{
        ctx.fillText(line, padding, y + 30);
        y += 38;
      }}
      y += 8;
      ctx.fillStyle = '#94a3b8';
      ctx.font = '500 18px Inter, system-ui, sans-serif';
      for (const line of summaryLines) {{
        ctx.fillText(line, padding, y + 22);
        y += 28;
      }}
      y += 12;
      for (const block of messageBlocks) {{
        const boxHeight = block.height;
        const bg = block.role === 'user' ? 'rgba(28, 44, 74, 0.96)' : 'rgba(22, 37, 58, 0.96)';
        ctx.fillStyle = bg;
        roundRect(ctx, padding, y, boxWidth, boxHeight, 22);
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.08)';
        ctx.stroke();
        ctx.fillStyle = '#94a3b8';
        ctx.font = '700 12px Inter, system-ui, sans-serif';
        ctx.fillText(block.role.toUpperCase(), padding + 18, y + 26);
        ctx.fillStyle = '#e5eefc';
        ctx.font = '500 16px Inter, system-ui, sans-serif';
        let textY = y + 52;
        for (const line of block.lines) {{
          ctx.fillText(line, padding + 18, textY);
          textY += 24;
        }}
        y += boxHeight + gutter;
      }}
      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      const blob = await new Promise((resolve, reject) => {{
        canvas.toBlob((result) => {{
          if (!result) {{
            reject(new Error('Image export failed.'));
            return;
          }}
          resolve(result);
        }}, 'image/png');
      }});
      downloadBlob(`${{convo.id || 'chat'}}-${{stamp}}.png`, blob);
    }}
    function exportConversation(format) {{
      const convo = activeConversation();
      if (!convo) return;
      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      if (format === 'json') {{
        downloadText(
          `${{convo.id || 'chat'}}-${{stamp}}.json`,
          JSON.stringify(convo, null, 2) + '\n',
          'application/json'
        );
        return;
      }}
      if (format === 'sharegpt') {{
        const payload = conversationShareGPT(convo);
        downloadText(
          `${{convo.id || 'chat'}}-${{stamp}}.sharegpt.json`,
          JSON.stringify(payload, null, 2) + '\n',
          'application/json'
        );
        return;
      }}
      if (format === 'html') {{
        const renderedMessages = (convo.messages || [])
          .map((message) => {{
            const role = message.role || 'assistant';
            const content = message.content || '';
            const body = role === 'user'
              ? `<div class=\"message-content\"><p>${{escapeHtml(content).replace(/\\n/g, '<br>')}}</p></div>`
              : `<div class=\"message-content\">${{renderMarkdown(content)}}</div>`;
            return `<article class=\"message ${{escapeHtml(role)}}\"><span class=\"role\">${{escapeHtml(role)}}</span>${{body}}</article>`;
          }})
          .join('');
        const html = `<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>${{escapeHtml(convo.title || convo.id || 'Conversation')}}</title>
  <style>
    body {{ font-family: Inter, ui-sans-serif, system-ui, sans-serif; margin: 0; padding: 24px; background: #0b1020; color: #e5eefc; }}
    .card {{ max-width: 960px; margin: 0 auto; background: #11172b; border: 1px solid rgba(255,255,255,0.08); border-radius: 20px; padding: 24px; }}
    .meta {{ color: #94a3b8; }}
    .message {{ margin-top: 16px; padding: 16px 18px; border-radius: 18px; border: 1px solid rgba(255,255,255,0.08); }}
    .message.user {{ background: #1c2c4a; }}
    .message.assistant {{ background: #16253a; }}
    .role {{ display: block; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.78rem; color: #94a3b8; }}
    .message-content {{ display: grid; gap: 0.75rem; line-height: 1.65; }}
    .message-content pre {{ margin: 0; padding: 14px; border-radius: 14px; background: #0b1020; white-space: pre-wrap; word-break: break-word; }}
    .message-content code {{ background: rgba(255,255,255,0.08); border-radius: 8px; padding: 0.1rem 0.35rem; }}
    .message-content a {{ color: #90cdf4; }}
  </style>
</head>
<body>
  <article class=\"card\">
    <h1>${{escapeHtml(convo.title || convo.id || 'Conversation')}}</h1>
    <p class=\"meta\">Model: ${{escapeHtml(convo.model || '')}}</p>
    ${{convo.systemPrompt ? `<pre class=\"meta\">${{escapeHtml(convo.systemPrompt)}}</pre>` : ''}}
    ${{renderedMessages}}
  </article>
</body>
</html>`;
        downloadText(`${{convo.id || 'chat'}}-${{stamp}}.html`, html, 'text/html');
        return;
      }}
      const markdown = conversationTranscript(convo);
      downloadText(`${{convo.id || 'chat'}}-${{stamp}}.md`, markdown, 'text/markdown');
    }}
    function templateDraftName() {{
      const typed = (els.templateName.value || '').trim();
      if (typed) return typed;
      const source = (els.systemPrompt.value || els.prompt.value || '').trim();
      if (source) {{
        return source.split('\\n').find((line) => line.trim())?.slice(0, 40) || 'Prompt template';
      }}
      return `Template ${{new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}}`;
    }}
    async function savePromptTemplate() {{
      const content = (els.systemPrompt.value || els.prompt.value || '').trim();
      if (!content) {{
        window.alert('Enter a system prompt or draft prompt first.');
        return;
      }}
      const templateId = editingTemplateId || undefined;
      const response = await fetch('/api/ai/prompt-templates', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          ...(templateId ? {{ id: templateId }} : {{}}),
          name: templateDraftName(),
          content,
        }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Template save failed');
      }}
      const data = await response.json();
      const saved = data.data || {{}};
      if (!saved.id) {{
        saved.id = `template-${{Date.now()}}`;
      }}
      if (!saved.name) {{
        saved.name = templateDraftName();
      }}
      if (!saved.content) {{
        saved.content = content;
      }}
      state.promptTemplates = [
        ...state.promptTemplates.filter((item) => item.id !== saved.id),
        saved,
      ].sort((a, b) => String(a.id || '').localeCompare(String(b.id || '')));
      els.templateName.value = '';
      editingTemplateId = null;
      renderTemplates();
    }}
    async function deletePromptTemplate(template) {{
      const response = await fetch('/api/ai/prompt-templates', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action: 'delete', id: template.id }}),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(() => ({{}}));
        throw new Error(data.error || response.statusText || 'Template delete failed');
      }}
      state.promptTemplates = state.promptTemplates.filter((item) => item.id !== template.id);
      if (editingTemplateId === template.id) {{
        editingTemplateId = null;
        els.templateName.value = '';
      }}
      renderTemplates();
    }}
    async function consumeStreamResponse(response, onDelta) {{
      const reader = response.body ? response.body.getReader() : null;
      if (!reader) {{
        return null;
      }}
      const decoder = new TextDecoder();
      let buffer = '';
      let finalPayload = null;
      while (true) {{
        const {{ done, value }} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {{ stream: true }});
        buffer = buffer.replace(/\r\n/g, '\\n');
        let separator = buffer.indexOf('\\n\\n');
        while (separator !== -1) {{
          const eventText = buffer.slice(0, separator);
          buffer = buffer.slice(separator + 2);
          separator = buffer.indexOf('\\n\\n');
          if (!eventText.trim()) continue;
          const dataLines = [];
          for (const line of eventText.split('\\n')) {{
            if (line.startsWith('data:')) {{
              dataLines.push(line.slice(5).trimStart());
            }}
          }}
          const dataText = dataLines.length ? dataLines.join('\\n') : eventText.trim();
          if (dataText === '[DONE]') {{
            return finalPayload;
          }}
          try {{
            const event = JSON.parse(dataText);
            if (event && event.type === 'delta') {{
              if (typeof event.content === 'string' && event.content) {{
                onDelta(event.content);
              }}
            }} else if (event && event.type === 'done') {{
              finalPayload = event.response || event;
            }} else if (event && event.type === 'error') {{
              throw new Error(event.error || 'Request failed');
            }} else if (event && event.choices) {{
              finalPayload = event;
            }}
          }} catch (err) {{
            if (dataText) {{
              onDelta(dataText);
            }}
          }}
        }}
      }}
      return finalPayload;
    }}
    async function sendMessage(text, options = {{}}) {{
      const appendUser = options.appendUser !== false;
      const convo = activeConversation() || newConversation();
      const model = options.model || els.modelSelect.value || state.currentModel || bootstrap.selectedModel || '';
      const systemPrompt = Object.prototype.hasOwnProperty.call(options, 'systemPrompt')
        ? String(options.systemPrompt || '').trim()
        : els.systemPrompt.value.trim();
      const files = Array.isArray(options.files) ? options.files : selectedFiles();
      const compareEnabled = Object.prototype.hasOwnProperty.call(options, 'compareEnabled')
        ? !!options.compareEnabled
        : !!els.compareToggle.checked;
      const compareModel = Object.prototype.hasOwnProperty.call(options, 'compareModel')
        ? String(options.compareModel || '')
        : (els.compareModelSelect.value || '');
      const requestedModels = compareEnabled && compareModel && compareModel !== model
        ? [model, compareModel]
        : [model];
      if (activeAbortController && options.queueIfBusy !== false) {{
        pendingMessageQueue.push({{
          text,
          options: {{
            appendUser,
            model,
            systemPrompt,
            files,
            compareEnabled,
            compareModel,
            queueIfBusy: false,
          }},
        }});
        updateQueueStatus();
        renderAll();
        return;
      }}
      convo.model = model;
      convo.systemPrompt = systemPrompt;
      convo.files = files;
      convo.compareModels = requestedModels.length > 1 ? requestedModels.slice(1) : [];
      state.compareEnabled = compareEnabled;
      state.compareModel = compareModel;
      if (!convo.messages) convo.messages = [];
      if (systemPrompt && (!convo.messages.length || convo.messages[0].role !== 'system')) {{
        convo.messages.unshift({{ role: 'system', content: systemPrompt }});
      }} else if (systemPrompt && convo.messages.length && convo.messages[0].role === 'system') {{
        convo.messages[0].content = systemPrompt;
      }}
      const hasUserMessage = convo.messages.some((message) => message.role === 'user');
      if (appendUser) {{
        convo.messages.push({{ role: 'user', content: text }});
      }} else if (!convo.messages.length || convo.messages[convo.messages.length - 1].role !== 'user') {{
        convo.messages.push({{ role: 'user', content: text }});
      }}
      if (appendUser && !hasUserMessage && (!convo.title || convo.title === 'New chat')) {{
        convo.title = suggestConversationTitle(text);
        els.conversationTitle.value = convo.title;
        els.title.textContent = convo.title;
      }}
      const assistant = {{ role: 'assistant', content: '', streaming: true }};
      convo.messages.push(assistant);
      if (activeAbortController) {{
        activeAbortController.abort();
      }}
      activeAbortController = new AbortController();
      renderAll();
      try {{
        const response = await fetch('/api/chat', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          signal: activeAbortController.signal,
          body: JSON.stringify({{
            conversationId: convo.id,
            title: convo.title || 'New chat',
            systemPrompt,
            files,
            model,
            models: requestedModels.length > 1 ? requestedModels : undefined,
            stream: true,
            messages: convo.messages.filter((msg) => msg.role !== 'assistant' || !msg.streaming),
          }}),
        }});
        if (!response.ok) {{
          let errorText = response.statusText;
          const type = response.headers.get('content-type') || '';
          if (type.includes('application/json')) {{
            const data = await response.json();
            errorText = data.error || data.message || errorText;
          }}
          throw new Error(errorText || 'Request failed');
        }}
        const type = response.headers.get('content-type') || '';
        if (type.includes('text/event-stream') && response.body) {{
          let started = false;
          const finalPayload = await consumeStreamResponse(response, (delta) => {{
            if (!started) {{
              assistant.content = '';
              started = true;
            }}
            assistant.streaming = true;
            assistant.content += delta;
            renderMessages();
          }});
          if (finalPayload && finalPayload.choices && finalPayload.choices[0] && finalPayload.choices[0].message) {{
            assistant.content = finalPayload.choices[0].message.content || assistant.content;
          }} else if (finalPayload && typeof finalPayload.content === 'string') {{
            assistant.content = finalPayload.content;
          }}
          assistant.streaming = false;
          }} else {{
          const data = await response.json();
          const content = data.choices && data.choices[0] && data.choices[0].message ? data.choices[0].message.content : (data.content || '');
          assistant.content = content || '';
          assistant.streaming = false;
        }}
      }} catch (err) {{
        if (err && err.name === 'AbortError') {{
          assistant.role = 'error';
          assistant.content = 'Cancelled.';
        }} else {{
          assistant.role = 'error';
          assistant.content = String(err.message || err);
        }}
        assistant.streaming = false;
      }} finally {{
        activeAbortController = null;
      }}
      assistant.streaming = false;
      void saveConversation(convo);
      save();
      renderAll();
      if (pendingMessageQueue.length) {{
        const next = pendingMessageQueue.shift();
        updateQueueStatus();
        void sendMessage(next.text, next.options);
      }}
    }}
    els.modelSelect.addEventListener('change', () => {{
      state.currentModel = els.modelSelect.value;
      persistActiveFields();
      renderAll();
    }});
    els.compareToggle.addEventListener('change', () => {{
      state.compareEnabled = !!els.compareToggle.checked;
      persistActiveFields();
      renderAll();
    }});
    els.compareModelSelect.addEventListener('change', () => {{
      state.compareModel = els.compareModelSelect.value || '';
      persistActiveFields();
      renderAll();
    }});
    els.addProviderPresets.addEventListener('click', async () => {{
      try {{
        await addProviderPresets();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.refreshProviders.addEventListener('click', async () => {{
      await refreshProviders();
      renderAll();
    }});
    els.toggleSidebar.addEventListener('click', () => {{
      setSidebarCollapsed(!state.sidebarCollapsed);
      renderAll();
    }});
    els.themeToggle.addEventListener('click', () => {{
      toggleTheme();
      renderAll();
    }});
    els.dictateButton.addEventListener('click', () => {{
      toggleVoiceInput();
      renderAll();
    }});
    els.refreshKb.addEventListener('click', async () => {{
      await refreshKnowledgeBases();
      renderAll();
    }});
    els.newKb.addEventListener('click', () => {{
      openKnowledgeBaseEditor(null);
    }});
    els.editKb.addEventListener('click', () => {{
      const base = (state.knowledgeBases || []).find((item) => String(item.id || '') === String(state.selectedKnowledgeBaseId || '')) || (state.knowledgeBases || [])[0];
      if (!base) {{
        window.alert('Select a knowledge base first.');
        return;
      }}
      openKnowledgeBaseEditor(base);
    }});
    els.kbSave.addEventListener('click', async () => {{
      try {{
        await saveKnowledgeBaseEditor();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.kbCancel.addEventListener('click', () => {{
      const base = editingKnowledgeBaseId ? (state.knowledgeBases || []).find((item) => String(item.id || '') === String(editingKnowledgeBaseId || '')) || null : null;
      if (base) {{
        openKnowledgeBaseEditor(base);
        return;
      }}
      clearKnowledgeBaseEditor();
    }});
    els.deleteKb.addEventListener('click', async () => {{
      const base = (state.knowledgeBases || []).find((item) => String(item.id || '') === String(state.selectedKnowledgeBaseId || '')) || null;
      if (!base) {{
        window.alert('Select a knowledge base first.');
        return;
      }}
      if (!window.confirm(`Delete knowledge base ${{base.name || base.id}}?`)) return;
      try {{
        await deleteKnowledgeBase(base.id);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.refreshSkills.addEventListener('click', async () => {{
      await refreshSkills();
      renderAll();
    }});
    els.newSkill.addEventListener('click', () => {{
      openSkillEditor(null);
    }});
    els.editSkill.addEventListener('click', () => {{
      const skill = (state.skills || []).find((item) => String(item.id || '') === String(state.selectedSkillId || '')) || (state.skills || [])[0];
      if (!skill) {{
        window.alert('Select a skill first.');
        return;
      }}
      openSkillEditor(skill);
    }});
    els.skillSave.addEventListener('click', async () => {{
      try {{
        await saveSkillEditor();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.skillCancel.addEventListener('click', () => {{
      const skill = editingSkillId ? (state.skills || []).find((item) => String(item.id || '') === String(editingSkillId || '')) || null : null;
      if (skill) {{
        openSkillEditor(skill);
        return;
      }}
      clearSkillEditor();
    }});
    els.deleteSkill.addEventListener('click', async () => {{
      const skill = (state.skills || []).find((item) => String(item.id || '') === String(state.selectedSkillId || '')) || null;
      if (!skill) {{
        window.alert('Select a skill first.');
        return;
      }}
      if (!window.confirm(`Delete skill ${{skill.name || skill.id}}?`)) return;
      try {{
        await deleteSkill(skill.id);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.skillUse.addEventListener('click', () => {{
      const skill = (state.skills || []).find((item) => String(item.id || '') === String(state.selectedSkillId || '')) || (state.skills || [])[0];
      if (!skill) {{
        window.alert('No skill selected.');
        return;
      }}
      setSystemPromptFromContent(skill.content || '');
    }});
    els.refreshMemories.addEventListener('click', async () => {{
      await refreshMemories();
      renderAll();
    }});
    els.newMemory.addEventListener('click', () => {{
      openMemoryEditor(null);
    }});
    els.editMemory.addEventListener('click', () => {{
      const memory = (state.memories || []).find((item) => String(item.id || '') === String(state.selectedMemoryId || '')) || (state.memories || [])[0];
      if (!memory) {{
        window.alert('Select a memory first.');
        return;
      }}
      openMemoryEditor(memory);
    }});
    els.memorySave.addEventListener('click', async () => {{
      try {{
        await saveMemoryEditor();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.memoryCancel.addEventListener('click', () => {{
      const memory = editingMemoryId ? (state.memories || []).find((item) => String(item.id || '') === String(editingMemoryId || '')) || null : null;
      if (memory) {{
        openMemoryEditor(memory);
        return;
      }}
      clearMemoryEditor();
    }});
    els.deleteMemory.addEventListener('click', async () => {{
      const memory = (state.memories || []).find((item) => String(item.id || '') === String(state.selectedMemoryId || '')) || null;
      if (!memory) {{
        window.alert('Select a memory first.');
        return;
      }}
      if (!window.confirm(`Delete memory ${{memory.title || memory.id}}?`)) return;
      try {{
        await deleteMemory(memory.id);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.memoryUse.addEventListener('click', () => {{
      const memory = (state.memories || []).find((item) => String(item.id || '') === String(state.selectedMemoryId || '')) || (state.memories || [])[0];
      if (!memory) {{
        window.alert('No memory selected.');
        return;
      }}
      setSystemPromptFromContent(memory.content || '');
    }});
    els.refreshNotes.addEventListener('click', async () => {{
      await refreshNotes();
      renderAll();
    }});
    els.newNote.addEventListener('click', () => {{
      openNoteEditor(null);
    }});
    els.editNote.addEventListener('click', () => {{
      const note = (state.notes || []).find((item) => String(item.id || '') === String(state.selectedNoteId || '')) || (state.notes || [])[0];
      if (!note) {{
        window.alert('Select a note first.');
        return;
      }}
      openNoteEditor(note);
    }});
    els.noteSave.addEventListener('click', async () => {{
      try {{
        await saveNoteEditor();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.noteCancel.addEventListener('click', () => {{
      const note = editingNoteId ? (state.notes || []).find((item) => String(item.id || '') === String(editingNoteId || '')) || null : null;
      if (note) {{
        openNoteEditor(note);
        return;
      }}
      clearNoteEditor();
    }});
    els.deleteNote.addEventListener('click', async () => {{
      const note = (state.notes || []).find((item) => String(item.id || '') === String(state.selectedNoteId || '')) || null;
      if (!note) {{
        window.alert('Select a note first.');
        return;
      }}
      if (!window.confirm(`Delete note ${{note.title || note.id}}?`)) return;
      try {{
        await deleteNote(note.id);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.notesUse.addEventListener('click', () => {{
      const note = (state.notes || []).find((item) => String(item.id || '') === String(state.selectedNoteId || '')) || (state.notes || [])[0];
      if (!note) {{
        window.alert('No note selected.');
        return;
      }}
      setSystemPromptFromContent(note.body || '');
    }});
    els.refreshArtifacts.addEventListener('click', async () => {{
      await refreshArtifacts();
      renderAll();
    }});
    els.newArtifact.addEventListener('click', () => {{
      openArtifactEditor(null);
    }});
    els.editArtifact.addEventListener('click', () => {{
      const artifact = (state.artifacts || []).find((item) => String(item.id || '') === String(state.selectedArtifactId || '')) || (state.artifacts || [])[0];
      if (!artifact) {{
        window.alert('Select an artifact first.');
        return;
      }}
      openArtifactEditor(artifact);
    }});
    els.artifactSave.addEventListener('click', async () => {{
      try {{
        await saveArtifactEditor();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.artifactCancel.addEventListener('click', () => {{
      const artifact = editingArtifactId ? (state.artifacts || []).find((item) => String(item.id || '') === String(editingArtifactId || '')) || null : null;
      if (artifact) {{
        openArtifactEditor(artifact);
        return;
      }}
      clearArtifactEditor();
    }});
    els.deleteArtifact.addEventListener('click', async () => {{
      const artifact = (state.artifacts || []).find((item) => String(item.id || '') === String(state.selectedArtifactId || '')) || null;
      if (!artifact) {{
        window.alert('Select an artifact first.');
        return;
      }}
      if (!window.confirm(`Delete artifact ${{artifact.title || artifact.id}}?`)) return;
      try {{
        await deleteArtifact(artifact.id);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.artifactUse.addEventListener('click', () => {{
      const artifact = (state.artifacts || []).find((item) => String(item.id || '') === String(state.selectedArtifactId || '')) || (state.artifacts || [])[0];
      if (!artifact) {{
        window.alert('No artifact selected.');
        return;
      }}
      setPromptFromContent(artifact.content || '');
    }});
    els.refreshTools.addEventListener('click', async () => {{
      await refreshTools();
      renderAll();
    }});
    els.newTool.addEventListener('click', () => {{
      openToolEditor(null);
    }});
    els.editTool.addEventListener('click', () => {{
      const tool = (state.toolServers || []).find((item) => String(item.id || '') === String(state.selectedToolId || '')) || (state.toolServers || [])[0];
      if (!tool) {{
        window.alert('Select a tool server first.');
        return;
      }}
      openToolEditor(tool);
    }});
    els.toolSave.addEventListener('click', async () => {{
      try {{
        await saveToolEditor();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.toolCancel.addEventListener('click', () => {{
      const tool = editingToolId ? (state.toolServers || []).find((item) => String(item.id || '') === String(editingToolId || '')) || null : null;
      if (tool) {{
        openToolEditor(tool);
        return;
      }}
      clearToolEditor();
    }});
    els.deleteTool.addEventListener('click', async () => {{
      const tool = (state.toolServers || []).find((item) => String(item.id || '') === String(state.selectedToolId || '')) || null;
      if (!tool) {{
        window.alert('Select a tool server first.');
        return;
      }}
      if (!window.confirm(`Delete tool server ${{tool.name || tool.id}}?`)) return;
      try {{
        await deleteTool(tool.id);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.refreshWebhooks.addEventListener('click', async () => {{
      await refreshWebhooks();
      renderAll();
    }});
    els.newWebhook.addEventListener('click', () => {{
      openWebhookEditor(null);
    }});
    els.editWebhook.addEventListener('click', () => {{
      const webhook = (state.webhooks || []).find((item) => String(item.id || '') === String(state.selectedWebhookId || '')) || (state.webhooks || [])[0];
      if (!webhook) {{
        window.alert('Select a webhook first.');
        return;
      }}
      openWebhookEditor(webhook);
    }});
    els.webhookSave.addEventListener('click', async () => {{
      try {{
        await saveWebhookEditor();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.webhookCancel.addEventListener('click', () => {{
      const webhook = editingWebhookId ? (state.webhooks || []).find((item) => String(item.id || '') === String(editingWebhookId || '')) || null : null;
      if (webhook) {{
        openWebhookEditor(webhook);
        return;
      }}
      clearWebhookEditor();
    }});
    els.deleteWebhook.addEventListener('click', async () => {{
      const webhook = (state.webhooks || []).find((item) => String(item.id || '') === String(state.selectedWebhookId || '')) || null;
      if (!webhook) {{
        window.alert('Select a webhook first.');
        return;
      }}
      if (!window.confirm(`Delete webhook ${{webhook.name || webhook.id}}?`)) return;
      try {{
        await deleteWebhook(webhook.id);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.agentSelect.addEventListener('change', () => {{
      state.currentAgentId = els.agentSelect.value || '';
      renderAll();
    }});
    els.agentApply.addEventListener('click', () => {{
      const agent = state.agents.find((item) => String(item.id || '') === String(els.agentSelect.value || ''));
      if (!agent) {{
        window.alert('Select an agent preset first.');
        return;
      }}
      applyAgentToConversation(agent);
    }});
    els.newAgent.addEventListener('click', () => {{
      openAgentEditor(null);
    }});
    els.editAgent.addEventListener('click', () => {{
      const agent = (state.agents || []).find((item) => String(item.id || '') === String(els.agentSelect.value || '')) || null;
      if (!agent) {{
        window.alert('Select an agent first.');
        return;
      }}
      openAgentEditor(agent);
    }});
    els.agentSave.addEventListener('click', async () => {{
      try {{
        await saveAgentEditor();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.agentCancel.addEventListener('click', () => {{
      const agent = editingAgentId ? (state.agents || []).find((item) => String(item.id || '') === String(editingAgentId || '')) || null : null;
      if (agent) {{
        openAgentEditor(agent);
        return;
      }}
      clearAgentEditor();
    }});
    els.deleteAgent.addEventListener('click', async () => {{
      const agent = (state.agents || []).find((item) => String(item.id || '') === String(els.agentSelect.value || '')) || null;
      if (!agent) {{
        window.alert('Select an agent first.');
        return;
      }}
      if (!window.confirm(`Delete agent ${{agent.name || agent.id}}?`)) return;
      try {{
        await deleteAgent(agent.id);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.refreshAgents.addEventListener('click', async () => {{
      await refreshAgents();
      renderAll();
    }});
    els.newAgentChat.addEventListener('click', () => {{
      const agent = state.agents.find((item) => String(item.id || '') === String(els.agentSelect.value || ''));
      const convo = newConversation();
      if (agent) applyAgentToConversation(agent);
      els.prompt.focus();
      if (!agent && convo) renderAll();
    }});
    els.kbRunQuery.addEventListener('click', async () => {{
      try {{
        await queryKnowledgeBases();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.addKb.addEventListener('click', async () => {{
      openKnowledgeBaseEditor(null);
      renderAll();
      els.kbEditorName.focus();
    }});
    els.refreshKb.addEventListener('click', async () => {{
      const selected = (state.knowledgeBases || []).find((item) => String(item.id || '') === String(state.selectedKnowledgeBaseId || '')) || null;
      if (!selected || !selected.id) {{
        await refreshKnowledgeBases();
        renderAll();
        return;
      }}
      try {{
        await refreshKnowledgeBaseIndex(selected.id);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.kbImport.addEventListener('click', async () => {{
      try {{
        await importKnowledgeBasesFromFile();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.kbExport.addEventListener('click', () => {{
      downloadText('knowledgeBases.json', knowledgeBasesExportPayload(), 'application/json;charset=utf-8');
    }});
    els.kbSync.addEventListener('click', async () => {{
      try {{
        await syncKnowledgeBases('sync');
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.kbWatch.addEventListener('click', async () => {{
      try {{
        await syncKnowledgeBases('watch');
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.conversationImport.addEventListener('click', async () => {{
      try {{
        await importConversationsFromFile();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.conversationExport.addEventListener('click', async () => {{
      try {{
        await exportConversationsToFile();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.conversationShareMd.addEventListener('click', async () => {{
      try {{
        await shareConversation('md');
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.conversationShareHtml.addEventListener('click', async () => {{
      try {{
        await shareConversation('html');
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.conversationClone.addEventListener('click', async () => {{
      try {{
        await cloneConversationFromSelection();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.agentImport.addEventListener('click', async () => {{
      try {{
        await importAgentsFromFile();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.agentExport.addEventListener('click', async () => {{
      try {{
        await exportAgentsToFile();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.agentShareMd.addEventListener('click', async () => {{
      try {{
        await shareAgent('md');
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.agentShareHtml.addEventListener('click', async () => {{
      try {{
        await shareAgent('html');
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.agentShareJson.addEventListener('click', async () => {{
      try {{
        await shareAgent('json');
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.agentClone.addEventListener('click', async () => {{
      try {{
        await cloneAgentFromSelection();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.webSearchQuery.addEventListener('input', () => {{
      state.webSearchQuery = els.webSearchQuery.value || '';
      save();
    }});
    els.webSearchProvider.addEventListener('change', () => {{
      state.webSearchProvider = els.webSearchProvider.value || 'duckduckgo';
      save();
    }});
    els.webSearchFallback.addEventListener('input', () => {{
      state.webSearchFallback = els.webSearchFallback.value || '';
      save();
    }});
    els.webSearchEngineUrl.addEventListener('input', () => {{
      state.webSearchEngineUrl = els.webSearchEngineUrl.value || '';
      save();
    }});
    els.webSearchBaseId.addEventListener('input', () => {{
      state.webSearchBaseId = els.webSearchBaseId.value || '';
      save();
    }});
    els.webSearchName.addEventListener('input', () => {{
      state.webSearchName = els.webSearchName.value || '';
      save();
    }});
    els.webSearchDescription.addEventListener('input', () => {{
      state.webSearchDescription = els.webSearchDescription.value || '';
      save();
    }});
    els.webSearchSaveLimit.addEventListener('input', () => {{
      state.webSearchSaveLimit = Number(els.webSearchSaveLimit.value || '5') || 5;
      save();
    }});
    els.webSearchRun.addEventListener('click', async () => {{
      try {{
        await runWebSearch('search');
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.webSearchSave.addEventListener('click', async () => {{
      try {{
        await runWebSearch('save');
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.webSearchClear.addEventListener('click', () => {{
      state.webSearchResults = [];
      renderAll();
    }});
    els.conversationTitle.addEventListener('input', () => {{
      persistActiveFields();
      renderAll();
    }});
    els.folderSelect.addEventListener('change', () => {{
      persistActiveFields();
      renderAll();
    }});
    els.createFolder.addEventListener('click', async () => {{
      try {{
        await createFolderFromInput();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.folderName.addEventListener('keydown', async (event) => {{
      if (event.key !== 'Enter') return;
      event.preventDefault();
      try {{
        await createFolderFromInput();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.conversationSearch.addEventListener('input', () => {{
      renderConversationList();
    }});
    els.conversationFilterAll.addEventListener('click', () => {{
      setConversationFilter('all');
    }});
    els.conversationFilterPinned.addEventListener('click', () => {{
      setConversationFilter('pinned');
    }});
    els.conversationFilterArchived.addEventListener('click', () => {{
      setConversationFilter('archived');
    }});
    els.messageSearch.addEventListener('input', () => {{
      state.messageSearchIndex = 0;
      renderAll();
    }});
    els.messageSearchPrev.addEventListener('click', () => {{
      if (!messageSearchMatches.length) return;
      state.messageSearchIndex = (state.messageSearchIndex - 1 + messageSearchMatches.length) % messageSearchMatches.length;
      renderAll();
    }});
    els.messageSearchNext.addEventListener('click', () => {{
      if (!messageSearchMatches.length) return;
      state.messageSearchIndex = (state.messageSearchIndex + 1) % messageSearchMatches.length;
      renderAll();
    }});
    els.systemPrompt.addEventListener('input', () => {{
      persistActiveFields();
      renderAll();
    }});
    els.fileSelect.addEventListener('change', () => {{
      persistActiveFields();
      renderAll();
    }});
    els.fileImport.addEventListener('click', async () => {{
      try {{
        await importFilesFromFile();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.fileExport.addEventListener('click', async () => {{
      try {{
        await exportFilesToFile();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.fileClone.addEventListener('click', async () => {{
      try {{
        await cloneFileFromSelection();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.uploadFiles.addEventListener('click', async () => {{
      try {{
        await uploadLocalFiles();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.fileSearch.addEventListener('input', () => {{
      state.fileSearch = els.fileSearch.value || '';
      save();
      renderFiles();
    }});
    els.clearFileSearch.addEventListener('click', () => {{
      state.fileSearch = '';
      els.fileSearch.value = '';
      save();
      renderFiles();
    }});
    els.scrollLatest.addEventListener('click', () => {{
      els.chat.scrollTop = els.chat.scrollHeight;
      updateScrollLatestButton();
    }});
    els.clearFileAttachments.addEventListener('click', () => {{
      setSelectedFiles([]);
      persistActiveFields();
      renderAll();
    }});
    els.composer.addEventListener('dragenter', (event) => {{
      event.preventDefault();
      dragDepth += 1;
      els.composer.classList.add('drag-over');
    }});
    els.composer.addEventListener('dragover', (event) => {{
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
      els.composer.classList.add('drag-over');
    }});
    els.composer.addEventListener('dragleave', (event) => {{
      event.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) {{
        els.composer.classList.remove('drag-over');
      }}
    }});
    els.composer.addEventListener('drop', async (event) => {{
      event.preventDefault();
      dragDepth = 0;
      els.composer.classList.remove('drag-over');
      const files = event.dataTransfer ? event.dataTransfer.files : [];
      if (!files || !files.length) return;
      try {{
        await uploadFilesCollection(files);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.chat.addEventListener('scroll', () => {{
      updateScrollLatestButton();
    }});
    els.prompt.addEventListener('paste', async (event) => {{
      const files = event.clipboardData ? Array.from(event.clipboardData.files || []) : [];
      if (!files.length) return;
      event.preventDefault();
      pasteDepth += 1;
      els.composer.classList.add('paste-over');
      try {{
        await uploadFilesCollection(files);
      }} catch (err) {{
        window.alert(String(err.message || err));
      }} finally {{
        pasteDepth = Math.max(0, pasteDepth - 1);
        if (pasteDepth === 0) {{
          els.composer.classList.remove('paste-over');
        }}
      }}
    }});
    els.closeFilePreview.addEventListener('click', () => {{
      closeFilePreview();
    }});
    els.shortcutsHelp.addEventListener('click', () => {{
      openShortcutsHelp();
    }});
    els.closeShortcuts.addEventListener('click', () => {{
      closeShortcutsHelp();
    }});
    els.copyFilePreview.addEventListener('click', async () => {{
      if (!previewFile) return;
      await copyText(String(previewFile.content || ''));
    }});
    els.filePreviewBackdrop.addEventListener('click', (event) => {{
      if (event.target === els.filePreviewBackdrop) {{
        closeFilePreview();
      }}
    }});
    els.shortcutsBackdrop.addEventListener('click', (event) => {{
      if (event.target === els.shortcutsBackdrop) {{
        closeShortcutsHelp();
      }}
    }});
    els.newChat.addEventListener('click', () => {{
      newConversation();
      renderAll();
    }});
    els.clearChat.addEventListener('click', () => {{
      const convo = activeConversation();
      if (!convo) return;
      convo.messages = [];
      save();
      void saveConversation(convo);
      renderAll();
    }});
    els.exportChatMd.addEventListener('click', () => {{
      exportConversation('md');
    }});
    els.exportChatJson.addEventListener('click', () => {{
      exportConversation('json');
    }});
    els.exportChatHtml.addEventListener('click', () => {{
      exportConversation('html');
    }});
    els.exportChatSharegpt.addEventListener('click', () => {{
      exportConversation('sharegpt');
    }});
    els.copyChat.addEventListener('click', async () => {{
      await copyConversation();
    }});
    els.shareChatImage.addEventListener('click', async () => {{
      try {{
        await shareConversationImage();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.renameChat.addEventListener('click', () => {{
      setSidebarCollapsed(false);
      els.conversationTitle.focus();
      els.conversationTitle.select();
    }});
    els.duplicateChat.addEventListener('click', () => {{
      const convo = activeConversation();
      if (!convo) return;
      cloneConversation(convo);
    }});
    els.newChatHeader.addEventListener('click', () => {{
      newConversation();
      renderAll();
    }});
    els.toggleChatPin.addEventListener('click', () => {{
      const convo = activeConversation();
      if (!convo) return;
      updateConversationState(convo, {{ pinned: !convo.pinned }});
    }});
    els.toggleChatArchive.addEventListener('click', () => {{
      const convo = activeConversation();
      if (!convo) return;
      updateConversationState(convo, {{ archived: !convo.archived }});
    }});
    els.deleteChat.addEventListener('click', () => {{
      const convo = activeConversation();
      if (!convo) return;
      if (window.confirm(`Delete ${{convo.title || convo.id}}?`)) {{
        deleteConversation(convo);
      }}
    }});
    els.regenerateChat.addEventListener('click', async () => {{
      const convo = activeConversation();
      if (!convo || !convo.messages || !convo.messages.length) return;
      const userMessages = convo.messages.filter((message) => message.role === 'user');
      const lastUser = userMessages[userMessages.length - 1];
      if (!lastUser) return;
      convo.messages = convo.messages.filter((message) => message.role !== 'assistant');
      const question = String(lastUser.content || '');
      void saveConversation(convo);
      renderAll();
      await sendMessage(question, {{ appendUser: false }});
    }});
    els.stopChat.addEventListener('click', () => {{
      if (activeAbortController) {{
        activeAbortController.abort();
      }}
    }});
    els.saveTemplate.addEventListener('click', async () => {{
      try {{
        await savePromptTemplate();
      }} catch (err) {{
        window.alert(String(err.message || err));
      }}
    }});
    els.openTemplateDrawer.addEventListener('click', () => {{
      setTemplateDrawerOpen(true);
    }});
    els.closeTemplateDrawer.addEventListener('click', () => {{
      setTemplateDrawerOpen(false);
    }});
    els.templateDrawer.querySelector('.template-drawer-backdrop')?.addEventListener('click', () => {{
      setTemplateDrawerOpen(false);
    }});
    els.templateSearch.addEventListener('input', () => {{
      state.templateSearch = els.templateSearch.value || '';
      save();
      renderTemplateGallery();
    }});
    els.templateGalleryClear.addEventListener('click', () => {{
      state.templateSearch = '';
      els.templateSearch.value = '';
      save();
      renderTemplateGallery();
    }});
    els.copySystemPrompt.addEventListener('click', async () => {{
      await copyCurrentSystemPrompt();
    }});
    els.templateCompareCopyCurrent.addEventListener('click', async () => {{
      await copyCurrentSystemPrompt();
    }});
    els.templateCompareCopySelected.addEventListener('click', async () => {{
      const template = combinedPromptTemplates().find((item) => item.id === state.templateCompareId) || null;
      if (!template) return;
      await copyText(template.content || '');
    }});
    els.templateCompareApplySelected.addEventListener('click', () => {{
      const template = combinedPromptTemplates().find((item) => item.id === state.templateCompareId) || null;
      if (!template) return;
      applyTemplateContent(template);
      setTemplateDrawerOpen(true);
      renderAll();
    }});
    els.resetTemplate.addEventListener('click', () => {{
      editingTemplateId = null;
      els.templateName.value = '';
      els.systemPrompt.value = '';
      renderAll();
    }});
    els.form.addEventListener('submit', async (event) => {{
      event.preventDefault();
      const text = els.prompt.value.trim();
      if (!text) return;
      els.prompt.value = '';
      await sendMessage(text);
    }});
    els.prompt.addEventListener('keydown', async (event) => {{
      if (event.key === 'Enter' && !event.shiftKey) {{
        event.preventDefault();
        els.form.requestSubmit();
      }}
    }});
    document.addEventListener('keydown', (event) => {{
      const activeTag = document.activeElement && document.activeElement.tagName ? document.activeElement.tagName.toLowerCase() : '';
      const isEditingInput = activeTag === 'textarea' || activeTag === 'input' || activeTag === 'select';
      const mod = event.metaKey || event.ctrlKey;
      if (event.key === 'Escape') {{
        if (els.shortcutsBackdrop.classList.contains('open')) {{
          event.preventDefault();
          closeShortcutsHelp();
          return;
        }}
        if (els.filePreviewBackdrop.classList.contains('open')) {{
          event.preventDefault();
          closeFilePreview();
          return;
        }}
      }}
      if (!mod) return;
      const key = String(event.key || '').toLowerCase();
      if (key === 'k' && !event.shiftKey && !event.altKey) {{
        event.preventDefault();
        els.prompt.focus();
        els.prompt.select?.();
        return;
      }}
      if (key === 'f' && event.shiftKey) {{
        event.preventDefault();
        els.messageSearch.focus();
        els.messageSearch.select?.();
        return;
      }}
      if (key === '/') {{
        event.preventDefault();
        openShortcutsHelp();
        return;
      }}
      if (!isEditingInput && key === 'enter' && event.shiftKey) {{
        event.preventDefault();
        els.form.requestSubmit();
      }}
    }});
    renderModels();
    renderTemplates();
    renderFiles();
    if (!state.conversations.length) {{
      newConversation();
    }}
    if (!state.activeId && state.conversations.length) {{
      state.activeId = state.conversations[0].id;
    }}
    void refreshWebSearchProviders().then(() => renderAll());
    if ('serviceWorker' in navigator) {{
      window.addEventListener('load', () => {{
        navigator.serviceWorker.register('/sw.js').catch(() => {{}});
      }});
    }}
    syncFields();
    applyTheme();
    renderVoiceControls();
    renderAll();
  </script>
</body>
</html>
"""


class QwenChatHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True


def _chat_manifest() -> dict[str, Any]:
    return {
        "name": "Qwen Gen Chat",
        "short_name": "Qwen Gen",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0b1020",
        "theme_color": "#0b1020",
        "icons": [
            {
                "src": "/qwen-gen-icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            }
        ],
    }


def _chat_service_worker_script() -> str:
    return """const CACHE_NAME = 'qwen-gen-chat-v1';
const SHELL = ['/', '/ai.html', '/platform/ai.html', '/manifest.webmanifest', '/qwen-gen-icon.svg', '/api/health'];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(SHELL);
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => (key === CACHE_NAME ? Promise.resolve() : caches.delete(key))));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const response = await fetch(event.request);
        const cache = await caches.open(CACHE_NAME);
        cache.put('/', response.clone());
        return response;
      } catch (err) {
        const cache = await caches.open(CACHE_NAME);
        return (await cache.match(event.request)) || (await cache.match('/')) || Response.error();
      }
    })());
    return;
  }
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(event.request);
    if (cached) return cached;
    try {
      const response = await fetch(event.request);
      if (response && response.ok) {
        cache.put(event.request, response.clone());
      }
      return response;
    } catch (err) {
      return cached || Response.error();
    }
  })());
});
"""


def _chat_icon_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="Qwen Gen">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#66e3c4"/>
      <stop offset="100%" stop-color="#7c9cff"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="128" fill="#0b1020"/>
  <path d="M112 160c0-26.5 21.5-48 48-48h192c26.5 0 48 21.5 48 48v112c0 26.5-21.5 48-48 48H232l-72 64v-64h-0c-26.5 0-48-21.5-48-48V160z" fill="url(#g)"/>
  <path d="M176 190h160M176 242h136" stroke="#0b1020" stroke-width="28" stroke-linecap="round"/>
</svg>
"""


class QwenChatRequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = f"QwenOmega/{VERSION}"

    def log_message(self, fmt: str, *args: object) -> None:
        eprint(f"[serve] {self.address_string()} - {fmt % args}")

    @property
    def state(self) -> Any:
        return getattr(self.server, "state")

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_stream_headers(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _send_stream_event(self, payload: Any) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            die("request body must be valid JSON")
        if not isinstance(payload, dict):
            die("request body must be a JSON object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        settings = self.state.settings
        if self.path in ("/", "/index.html", "/chat", "/ai.html", "/platform/ai.html"):
            self._send_html(200, render_chat_ui_html(settings))
            return
        if self.path == "/api/health":
            self._send_json(200, {"ok": True, "version": VERSION})
            return
        if self.path in ("/api/bootstrap", "/api/ai/bootstrap"):
            self._send_json(200, _settings_bootstrap(settings))
            return
        if self.path in ("/api/models", "/api/ai/models"):
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": entry.get("id"),
                            "object": "model",
                            "created": 0,
                            "owned_by": entry.get("provider"),
                            "provider": entry.get("provider"),
                            "providerName": entry.get("providerName"),
                            "baseUrl": entry.get("baseUrl"),
                            "selected": entry.get("selected", False),
                        }
                        for entry in _iter_model_entries(settings)
                    ],
                },
            )
            return
        if self.path in ("/api/providers", "/api/ai/providers"):
            self._send_json(200, {"data": settings.get("modelProviders", {})})
            return
        if self.path in ("/api/prompt-templates", "/api/ai/prompt-templates"):
            self._send_json(200, {"data": _settings_prompt_templates(settings)})
            return
        if self.path in ("/api/folders", "/api/ai/folders"):
            self._send_json(200, {"data": _settings_folders(settings)})
            return
        if self.path in ("/api/conversations", "/api/ai/conversations"):
            self._send_json(200, {"data": _settings_conversations(settings)})
            return
        if self.path in ("/api/files", "/api/ai/files"):
            self._send_json(
                200,
                {
                    "data": [
                        {
                            "id": file_item.get("id"),
                            "name": file_item.get("name"),
                            "kind": file_item.get("kind", ""),
                            "size": file_item.get("size"),
                            "description": file_item.get("description", ""),
                            "path": file_item.get("path", ""),
                        }
                        for file_item in _settings_files(settings)
                    ]
                },
            )
            return
        if self.path in ("/api/kb", "/api/ai/kb"):
            self._send_json(
                200,
                {
                    "data": {
                        "knowledgeBases": _settings_knowledge_bases(settings),
                        "knowledgeIndexes": _settings_knowledge_indexes(settings),
                    }
                },
            )
            return
        if self.path in ("/api/skills", "/api/ai/skills"):
            self._send_json(200, {"data": _settings_skills(settings)})
            return
        if self.path in ("/api/memories", "/api/ai/memories"):
            self._send_json(200, {"data": _settings_memories(settings)})
            return
        if self.path in ("/api/notes", "/api/ai/notes"):
            self._send_json(200, {"data": _settings_notes(settings)})
            return
        if self.path in ("/api/artifacts", "/api/ai/artifacts"):
            self._send_json(200, {"data": _settings_artifacts(settings)})
            return
        if self.path in ("/api/tools", "/api/ai/tools"):
            self._send_json(200, {"data": _settings_tool_servers(settings)})
            return
        if self.path in ("/api/agents", "/api/ai/agents"):
            self._send_json(200, {"data": _settings_agents(settings)})
            return
        if self.path in ("/api/webhooks", "/api/ai/webhooks"):
            self._send_json(200, {"data": _settings_webhooks(settings)})
            return
        if self.path in ("/api/web-search", "/api/ai/web-search"):
            self._send_json(
                200,
                {
                    "data": {
                        "providers": [
                            {
                                "id": key,
                                "name": info.get("name", key),
                                "description": info.get("description", ""),
                                "requiresApiKey": bool(info.get("env_key")),
                            }
                            for key, info in sorted(WEB_SEARCH_PROVIDERS.items())
                        ],
                        "defaultProvider": "duckduckgo",
                    }
                },
            )
            return
        if self.path == "/manifest.webmanifest":
            body = json.dumps(_chat_manifest(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/sw.js":
            body = _chat_service_worker_script().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/qwen-gen-icon.svg":
            body = _chat_icon_svg().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "Not Found")

    def do_HEAD(self) -> None:  # noqa: N802
        settings = self.state.settings
        if self.path in ("/", "/index.html", "/chat", "/ai.html", "/platform/ai.html"):
            body = render_chat_ui_html(settings).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path == "/api/health":
            body = json.dumps({"ok": True, "version": VERSION}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/bootstrap", "/api/ai/bootstrap"):
            body = json.dumps(_settings_bootstrap(settings), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/models", "/api/ai/models"):
            body = json.dumps(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": entry.get("id"),
                            "object": "model",
                            "created": 0,
                            "owned_by": entry.get("provider"),
                            "provider": entry.get("provider"),
                            "providerName": entry.get("providerName"),
                            "baseUrl": entry.get("baseUrl"),
                            "selected": entry.get("selected", False),
                        }
                        for entry in _iter_model_entries(settings)
                    ],
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/providers", "/api/ai/providers"):
            body = json.dumps({"data": self.state.settings.get("modelProviders", {})}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/prompt-templates", "/api/ai/prompt-templates"):
            body = json.dumps({"data": _settings_prompt_templates(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/folders", "/api/ai/folders"):
            body = json.dumps({"data": _settings_folders(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/conversations", "/api/ai/conversations"):
            body = json.dumps({"data": _settings_conversations(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/files", "/api/ai/files"):
            body = json.dumps(
                {
                    "data": [
                        {
                            "id": file_item.get("id"),
                            "name": file_item.get("name"),
                            "kind": file_item.get("kind", ""),
                            "size": file_item.get("size"),
                            "description": file_item.get("description", ""),
                            "path": file_item.get("path", ""),
                        }
                        for file_item in _settings_files(settings)
                    ]
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/kb", "/api/ai/kb"):
            body = json.dumps(
                {
                    "data": {
                        "knowledgeBases": _settings_knowledge_bases(settings),
                        "knowledgeIndexes": _settings_knowledge_indexes(settings),
                    }
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/skills", "/api/ai/skills"):
            body = json.dumps({"data": _settings_skills(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/memories", "/api/ai/memories"):
            body = json.dumps({"data": _settings_memories(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/notes", "/api/ai/notes"):
            body = json.dumps({"data": _settings_notes(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/artifacts", "/api/ai/artifacts"):
            body = json.dumps({"data": _settings_artifacts(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/tools", "/api/ai/tools"):
            body = json.dumps({"data": _settings_tool_servers(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/agents", "/api/ai/agents"):
            body = json.dumps({"data": _settings_agents(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path in ("/api/webhooks", "/api/ai/webhooks"):
            body = json.dumps({"data": _settings_webhooks(settings)}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path == "/manifest.webmanifest":
            body = json.dumps(_chat_manifest(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path == "/sw.js":
            body = _chat_service_worker_script().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path == "/qwen-gen-icon.svg":
            body = _chat_icon_svg().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        try:
            settings = self.state.settings
            payload = self._read_body()
            if self.path in ("/api/prompt-templates", "/api/ai/prompt-templates"):
                if str(payload.get("action") or "").strip() == "delete":
                    template_id = str(
                        payload.get("id") or payload.get("templateId") or ""
                    ).strip()
                    self.state.delete_prompt_template(template_id)
                    self._send_json(200, {"ok": True, "deleted": template_id})
                    return
                template = self.state.upsert_prompt_template(payload)
                self._send_json(200, {"data": template})
                return
            if self.path in ("/api/folders", "/api/ai/folders"):
                if str(payload.get("action") or "").strip() == "delete":
                    folder_id = str(payload.get("id") or payload.get("folderId") or "").strip()
                    self.state.delete_folder(folder_id)
                    self._send_json(200, {"ok": True, "deleted": folder_id})
                    return
                folder = self.state.upsert_folder(payload)
                self._send_json(200, {"data": folder})
                return
            if self.path in ("/api/providers", "/api/ai/providers"):
                action = str(payload.get("action") or "").strip()
                if action in ("add-presets", "add", "seed", ""):
                    added = self.state.add_provider_presets()
                    self._send_json(200, {"ok": True, "added": added, "data": self.state.settings.get("modelProviders", {})})
                    return
                if action in ("delete-model", "remove-model", "delete"):
                    model_id = str(payload.get("id") or payload.get("modelId") or "").strip()
                    self.state.delete_provider_model(model_id)
                    self._send_json(200, {"ok": True, "deleted": model_id, "data": self.state.settings.get("modelProviders", {})})
                    return
                self._send_json(400, {"error": "unsupported provider action"})
                return
            if self.path in ("/api/kb", "/api/ai/kb"):
                action = str(payload.get("action") or "").strip()
                if action == "delete":
                    base_id = str(payload.get("id") or payload.get("baseId") or "").strip()
                    self.state.delete_knowledge_base(base_id)
                    self._send_json(200, {"ok": True, "deleted": base_id})
                    return
                if action == "import":
                    raw = payload.get("content", payload.get("json", payload.get("data")))
                    parsed: Any = raw
                    if isinstance(raw, str):
                        try:
                            parsed = json.loads(raw)
                        except json.JSONDecodeError:
                            self._send_json(400, {"error": "import content must be valid JSON"})
                            return
                    bases, indexes = self.state.import_knowledge_sources(parsed)
                    self._send_json(
                        200,
                        {
                            "data": {
                                "knowledgeBases": bases,
                                "knowledgeIndexes": indexes,
                            }
                        },
                    )
                    return
                if action == "export":
                    self._send_json(
                        200,
                        {
                            "data": {
                                "knowledgeBases": _settings_knowledge_bases(settings),
                                "knowledgeIndexes": _settings_knowledge_indexes(settings),
                                "content": json.dumps(
                                    {
                                        "knowledgeBases": _settings_knowledge_bases(settings),
                                        "knowledgeIndexes": _settings_knowledge_indexes(settings),
                                    },
                                    indent=2,
                                    ensure_ascii=False,
                                )
                                + "\n",
                            }
                        },
                    )
                    return
                if action == "refresh":
                    base_id = str(payload.get("id") or payload.get("baseId") or "").strip()
                    if not base_id:
                        self._send_json(400, {"error": "baseId is required"})
                        return
                    source_label, index, refreshed_base = self.state.refresh_knowledge_base(
                        base_id,
                        int(payload.get("chunkSize") or 2000),
                        int(payload.get("overlap") or 200),
                        int(payload.get("timeout") or DEFAULT_TIMEOUT),
                    )
                    self._send_json(
                        200,
                        {
                            "data": {
                                "sourceLabel": source_label,
                                "knowledgeIndex": index,
                                "knowledgeBase": refreshed_base,
                            }
                        },
                    )
                    return
                if action == "sync":
                    base_id = str(payload.get("id") or payload.get("baseId") or "").strip()
                    output_dir = payload.get("outputDir") or payload.get("output")
                    output_path = pathlib.Path(str(output_dir)).expanduser() if isinstance(output_dir, str) and output_dir.strip() else None
                    manifest = self.state.sync_knowledge_bases(
                        base_id or None,
                        chunk_size=int(payload.get("chunkSize") or 2000),
                        overlap=int(payload.get("overlap") or 200),
                        timeout=int(payload.get("timeout") or DEFAULT_TIMEOUT),
                        output_dir=output_path,
                    )
                    self._send_json(200, {"data": manifest})
                    return
                if action == "watch":
                    base_id = str(payload.get("id") or payload.get("baseId") or "").strip()
                    output_dir = payload.get("outputDir") or payload.get("output")
                    output_path = pathlib.Path(str(output_dir)).expanduser() if isinstance(output_dir, str) and output_dir.strip() else None
                    manifest = self.state.watch_knowledge_bases(
                        base_id or None,
                        iterations=int(payload.get("iterations") or 1),
                        interval=float(payload.get("interval") or 0.0),
                        chunk_size=int(payload.get("chunkSize") or 2000),
                        overlap=int(payload.get("overlap") or 200),
                        timeout=int(payload.get("timeout") or DEFAULT_TIMEOUT),
                        output_dir=output_path,
                    )
                    self._send_json(200, {"data": manifest})
                    return
                if action in ("", "add", "save", "upsert"):
                    base = self.state.upsert_knowledge_base(payload)
                    self._send_json(200, {"data": base})
                    return
                self._send_json(400, {"error": "unsupported knowledge base action"})
                return
            if self.path in ("/api/kb/query", "/api/ai/kb/query"):
                query = str(payload.get("query") or "").strip()
                if not query:
                    self._send_json(400, {"error": "query is required"})
                    return
                base_id = payload.get("baseId")
                base_id = str(base_id).strip() if isinstance(base_id, str) else ""
                matches = _search_knowledge_indexes(
                    _load_knowledge_indexes_from_settings(self.state.settings),
                    query,
                    base_id or None,
                )
                self._send_json(200, {"data": matches})
                return
            if self.path in ("/api/skills", "/api/ai/skills"):
                if str(payload.get("action") or "").strip() == "delete":
                    skill_id = str(payload.get("id") or payload.get("skillId") or "").strip()
                    self.state.delete_skill(skill_id)
                    self._send_json(200, {"ok": True, "deleted": skill_id})
                    return
                if str(payload.get("action") or "").strip() == "share":
                    skill_id = str(payload.get("id") or payload.get("skillId") or "").strip()
                    skill = _find_skill(_settings_skills(self.state.settings), skill_id)
                    if skill is None:
                        self._send_json(404, {"error": f"skill '{skill_id}' not found"})
                        return
                    fmt = str(payload.get("format") or "md").strip().lower()
                    if fmt == "json":
                        rendered = json.dumps(skill, indent=2, ensure_ascii=False) + "\n"
                    elif fmt == "html":
                        rendered = render_skill_html(skill)
                    else:
                        rendered = render_skill_md(skill)
                    self._send_json(
                        200,
                        {
                            "data": {
                                "id": skill.get("id"),
                                "name": skill.get("name"),
                                "format": fmt,
                                "content": rendered,
                            }
                        },
                    )
                    return
                skill = self.state.upsert_skill(payload)
                self._send_json(200, {"data": skill})
                return
            if self.path in ("/api/agents", "/api/ai/agents"):
                if str(payload.get("action") or "").strip() == "delete":
                    agent_id = str(payload.get("id") or payload.get("agentId") or "").strip()
                    self.state.delete_agent(agent_id)
                    self._send_json(200, {"ok": True, "deleted": agent_id})
                    return
                if str(payload.get("action") or "").strip() == "import":
                    raw = payload.get("content", payload.get("json", payload.get("data")))
                    parsed: Any = raw
                    if isinstance(raw, str):
                        try:
                            parsed = json.loads(raw)
                        except json.JSONDecodeError:
                            self._send_json(400, {"error": "import content must be valid JSON"})
                            return
                    imported = _normalize_agent_source_payload(parsed)
                    if not imported:
                        self._send_json(400, {"error": "no agents found in import payload"})
                        return
                    agents = settings.setdefault("agents", [])
                    if not isinstance(agents, list):
                        agents = []
                        settings["agents"] = agents
                    existing = {str(a.get("id")): a for a in agents if isinstance(a, dict)}
                    for item in imported:
                        if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                            item = dict(item)
                            item["id"] = slugify(str(item.get("name") or "agent"))
                        if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                            item["name"] = str(item.get("id"))
                        if not isinstance(item.get("baseModel"), str) or not str(item.get("baseModel")).strip():
                            if isinstance(item.get("model"), str) and str(item.get("model")).strip():
                                item["baseModel"] = str(item.get("model")).strip()
                        existing[str(item.get("id"))] = item
                    agents[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
                    normalize_agents(settings)
                    self.state._save()
                    self._send_json(200, {"data": {"agents": agents}})
                    return
                if str(payload.get("action") or "").strip() == "export":
                    agents = _settings_agents(settings)
                    self._send_json(
                        200,
                        {
                            "data": {
                                "agents": agents,
                                "content": json.dumps({"agents": agents}, indent=2, ensure_ascii=False) + "\n",
                            }
                        },
                    )
                    return
                if str(payload.get("action") or "").strip() == "share":
                    agent_id = str(payload.get("id") or payload.get("agentId") or "").strip()
                    agent = _find_agent(_settings_agents(settings), agent_id)
                    if agent is None:
                        self._send_json(404, {"error": f"agent '{agent_id}' not found"})
                        return
                    fmt = str(payload.get("format") or "md").strip().lower()
                    if fmt == "json":
                        rendered = json.dumps(agent, indent=2, ensure_ascii=False) + "\n"
                    elif fmt == "html":
                        rendered = render_agent_html(agent)
                    else:
                        rendered = render_agent_md(agent)
                    self._send_json(
                        200,
                        {
                            "data": {
                                "id": agent.get("id"),
                                "name": agent.get("name"),
                                "format": fmt,
                                "content": rendered,
                            }
                        },
                    )
                    return
                if str(payload.get("action") or "").strip() == "clone":
                    agent_id = str(payload.get("id") or payload.get("agentId") or "").strip()
                    agents = settings.setdefault("agents", [])
                    if not isinstance(agents, list):
                        agents = []
                        settings["agents"] = agents
                    clone = _clone_registry_item(
                        agents,
                        agent_id,
                        new_id=str(payload.get("newId") or payload.get("new_id") or "") or None,
                        new_title=str(payload.get("name") or "").strip() or None,
                    )
                    clone["name"] = str(payload.get("name") or clone.get("name") or clone["id"]).strip()
                    agents.append(clone)
                    agents.sort(key=lambda x: str(x.get("id", "")).lower())
                    normalize_agents(settings)
                    self.state._save()
                    self._send_json(200, {"data": {"agent": clone}})
                    return
                agent = self.state.upsert_agent(payload)
                self._send_json(200, {"data": agent})
                return
            if self.path in ("/api/webhooks", "/api/ai/webhooks"):
                if str(payload.get("action") or "").strip() == "delete":
                    webhook_id = str(payload.get("id") or payload.get("webhookId") or "").strip()
                    self.state.delete_webhook(webhook_id)
                    self._send_json(200, {"ok": True, "deleted": webhook_id})
                    return
                webhook = self.state.upsert_webhook(payload)
                self._send_json(200, {"data": webhook})
                return
            if self.path in ("/api/web-search", "/api/ai/web-search"):
                action = str(payload.get("action") or "search").strip() or "search"
                if action == "providers":
                    self._send_json(
                        200,
                        {
                            "data": {
                                "providers": [
                                    {
                                        "id": key,
                                        "name": info.get("name", key),
                                        "description": info.get("description", ""),
                                        "requiresApiKey": bool(info.get("env_key")),
                                    }
                                    for key, info in sorted(WEB_SEARCH_PROVIDERS.items())
                                ],
                                "defaultProvider": "duckduckgo",
                            }
                        },
                    )
                    return
                query = str(payload.get("query") or "").strip()
                if not query:
                    self._send_json(400, {"error": "query is required"})
                    return
                providers: list[str] = []
                provider = str(payload.get("provider") or "").strip()
                if provider:
                    providers.append(provider)
                fallback = payload.get("fallbackProviders", payload.get("fallbackProvider", []))
                if isinstance(fallback, str):
                    providers.extend([part.strip() for part in fallback.split(",") if part.strip()])
                elif isinstance(fallback, list):
                    providers.extend([str(part).strip() for part in fallback if str(part).strip()])
                results = fetch_web_search_results_chain(
                    query,
                    providers,
                    engine_url=str(payload.get("engineUrl") or "").strip() or None,
                    api_key=str(payload.get("apiKey") or "").strip(),
                    timeout=int(payload.get("timeout") or DEFAULT_TIMEOUT),
                    limit=int(payload.get("limit") or 10),
                )
                if action in ("search", "query", ""):
                    self._send_json(200, {"data": results})
                    return
                if action in ("save", "save-to-knowledge"):
                    with self.state._lock:
                        save_payload = _save_web_search_results_to_settings(
                            self.state.settings,
                            query,
                            results,
                            base_id=str(payload.get("baseId") or "").strip() or None,
                            knowledge_name=str(payload.get("knowledgeName") or "").strip() or None,
                            description=str(payload.get("description") or "").strip() or None,
                            save_limit=int(payload.get("saveLimit") or 5),
                            chunk_size=int(payload.get("chunkSize") or 2000),
                            overlap=int(payload.get("overlap") or 200),
                            timeout=int(payload.get("timeout") or DEFAULT_TIMEOUT),
                        )
                        self.state.settings["$version"] = 4
                        self.state._save()
                    self._send_json(200, {"data": save_payload})
                    return
                self._send_json(400, {"error": "unsupported web search action"})
                return
            if self.path in ("/api/memories", "/api/ai/memories"):
                if str(payload.get("action") or "").strip() == "delete":
                    memory_id = str(payload.get("id") or payload.get("memoryId") or "").strip()
                    self.state.delete_memory(memory_id)
                    self._send_json(200, {"ok": True, "deleted": memory_id})
                    return
                memory = self.state.upsert_memory(payload)
                self._send_json(200, {"data": memory})
                return
            if self.path in ("/api/notes", "/api/ai/notes"):
                if str(payload.get("action") or "").strip() == "delete":
                    note_id = str(payload.get("id") or payload.get("noteId") or "").strip()
                    self.state.delete_note(note_id)
                    self._send_json(200, {"ok": True, "deleted": note_id})
                    return
                note = self.state.upsert_note(payload)
                self._send_json(200, {"data": note})
                return
            if self.path in ("/api/artifacts", "/api/ai/artifacts"):
                if str(payload.get("action") or "").strip() == "delete":
                    artifact_id = str(payload.get("id") or payload.get("artifactId") or "").strip()
                    self.state.delete_artifact(artifact_id)
                    self._send_json(200, {"ok": True, "deleted": artifact_id})
                    return
                artifact = self.state.upsert_artifact(payload)
                self._send_json(200, {"data": artifact})
                return
            if self.path in ("/api/tools", "/api/ai/tools"):
                if str(payload.get("action") or "").strip() == "delete":
                    tool_id = str(payload.get("id") or payload.get("toolId") or "").strip()
                    self.state.delete_tool_server(tool_id)
                    self._send_json(200, {"ok": True, "deleted": tool_id})
                    return
                tool_server = self.state.upsert_tool_server(payload)
                self._send_json(200, {"data": tool_server})
                return
            if self.path in ("/api/conversations", "/api/ai/conversations"):
                if str(payload.get("action") or "").strip() == "delete":
                    convo_id = str(payload.get("id") or payload.get("conversationId") or "").strip()
                    self.state.delete_conversation(convo_id)
                    self._send_json(200, {"ok": True, "deleted": convo_id})
                    return
                if str(payload.get("action") or "").strip() == "import":
                    raw = payload.get("content", payload.get("json", payload.get("data")))
                    parsed: Any = raw
                    if isinstance(raw, str):
                        try:
                            parsed = json.loads(raw)
                        except json.JSONDecodeError:
                            self._send_json(400, {"error": "import content must be valid JSON"})
                            return
                    imported = _normalize_conversation_source_payload(parsed)
                    if not imported:
                        self._send_json(400, {"error": "no conversations found in import payload"})
                        return
                    conversations = settings.setdefault("conversations", [])
                    if not isinstance(conversations, list):
                        conversations = []
                        settings["conversations"] = conversations
                    existing = {str(c.get("id")): c for c in conversations if isinstance(c, dict)}
                    for item in imported:
                        if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                            item = dict(item)
                            item["id"] = slugify(str(item.get("title") or "conversation"))
                        if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                            item["title"] = str(item.get("id"))
                        existing[str(item.get("id"))] = item
                    conversations[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
                    normalize_conversations(settings)
                    self.state._save()
                    self._send_json(200, {"data": {"conversations": conversations}})
                    return
                if str(payload.get("action") or "").strip() == "export":
                    conversations = _settings_conversations(settings)
                    self._send_json(
                        200,
                        {
                            "data": {
                                "conversations": conversations,
                                "content": json.dumps(
                                    {"conversations": conversations},
                                    indent=2,
                                    ensure_ascii=False,
                                )
                                + "\n",
                            }
                        },
                    )
                    return
                if str(payload.get("action") or "").strip() == "share":
                    convo_id = str(payload.get("id") or payload.get("conversationId") or "").strip()
                    conversation = _find_conversation(_settings_conversations(settings), convo_id)
                    if conversation is None:
                        self._send_json(404, {"error": f"conversation '{convo_id}' not found"})
                        return
                    fmt = str(payload.get("format") or "md").strip().lower()
                    if fmt == "html":
                        rendered = render_conversation_html(conversation)
                    else:
                        rendered = render_conversation_md(conversation)
                    self._send_json(
                        200,
                        {
                            "data": {
                                "id": conversation.get("id"),
                                "name": conversation.get("title"),
                                "format": fmt,
                                "content": rendered,
                            }
                        },
                    )
                    return
                if str(payload.get("action") or "").strip() == "clone":
                    convo_id = str(payload.get("id") or payload.get("conversationId") or "").strip()
                    conversations = settings.setdefault("conversations", [])
                    if not isinstance(conversations, list):
                        conversations = []
                        settings["conversations"] = conversations
                    clone = _clone_registry_item(
                        conversations,
                        convo_id,
                        new_id=str(payload.get("newId") or payload.get("new_id") or "") or None,
                        new_title=str(payload.get("title") or "").strip() or None,
                    )
                    conversations.append(clone)
                    conversations.sort(key=lambda x: str(x.get("id", "")).lower())
                    normalize_conversations(settings)
                    self.state._save()
                    self._send_json(200, {"data": {"conversation": clone}})
                    return
                conversation = self.state.upsert_conversation(payload)
                self._send_json(200, {"data": conversation})
                return
            if self.path in ("/api/files", "/api/ai/files"):
                if str(payload.get("action") or "").strip() == "delete":
                    file_id = str(payload.get("id") or payload.get("fileId") or "").strip()
                    self.state.delete_file(file_id)
                    self._send_json(200, {"ok": True, "deleted": file_id})
                    return
                if str(payload.get("action") or "").strip() == "import":
                    raw = payload.get("content", payload.get("json", payload.get("data")))
                    parsed: Any = raw
                    if isinstance(raw, str):
                        try:
                            parsed = json.loads(raw)
                        except json.JSONDecodeError:
                            self._send_json(400, {"error": "import content must be valid JSON"})
                            return
                    imported = self.state.import_files(parsed)
                    self._send_json(200, {"data": {"files": imported}})
                    return
                if str(payload.get("action") or "").strip() == "export":
                    files = _settings_files(settings)
                    self._send_json(
                        200,
                        {
                            "data": {
                                "files": files,
                                "content": json.dumps({"files": files}, indent=2, ensure_ascii=False) + "\n",
                            }
                        },
                    )
                    return
                if str(payload.get("action") or "").strip() == "share":
                    file_id = str(payload.get("id") or payload.get("fileId") or "").strip()
                    file_item = _find_file(_settings_files(self.state.settings), file_id)
                    if file_item is None:
                        self._send_json(404, {"error": f"file '{file_id}' not found"})
                        return
                    fmt = str(payload.get("format") or "md").strip().lower()
                    if fmt == "json":
                        rendered = json.dumps(file_item, indent=2, ensure_ascii=False) + "\n"
                    elif fmt == "html":
                        rendered = _render_file_html(file_item)
                    else:
                        rendered = _render_file_md(file_item)
                    self._send_json(
                        200,
                        {
                            "data": {
                                "id": file_item.get("id"),
                                "name": file_item.get("name"),
                                "format": fmt,
                                "content": rendered,
                            }
                        },
                    )
                    return
                if str(payload.get("action") or "").strip() == "clone":
                    file_id = str(payload.get("id") or payload.get("fileId") or "").strip()
                    clone = self.state.clone_file(
                        file_id,
                        new_id=str(payload.get("newId") or payload.get("new_id") or "") or None,
                        name=str(payload.get("name") or "").strip() or None,
                    )
                    self._send_json(200, {"data": {"file": clone}})
                    return
                file_item = self.state.upsert_file(payload)
                self._send_json(
                    200,
                    {
                        "data": {
                            "id": file_item.get("id"),
                            "name": file_item.get("name"),
                            "kind": file_item.get("kind", ""),
                            "size": file_item.get("size"),
                            "description": file_item.get("description", ""),
                            "path": file_item.get("path", ""),
                        }
                    },
                )
                return
            if self.path not in ("/api/chat", "/api/ai/chat"):
                self.send_error(404, "Not Found")
                return
            model_id = str(payload.get("model") or _settings_default_model(self.state.settings) or "").strip()
            if not model_id:
                self._send_json(400, {"error": "model is required"})
                return
            requested_models = _chat_requested_models(payload, model_id)
            messages = _chat_messages(payload.get("messages"))
            title = str(payload.get("title") or "").strip()
            if not title or title.lower() == "new chat":
                title = _suggest_chat_title(messages)
            conversation = {
                "id": payload.get("conversationId", payload.get("id")),
                "title": title,
                "model": model_id,
                "systemPrompt": payload.get("systemPrompt"),
                "files": payload.get("files", []),
            }
            if len(requested_models) > 1:
                conversation["compareModels"] = requested_models[1:]
            if bool(payload.get("stream")):
                self._send_stream_headers()
                try:
                    def send_delta(delta: str) -> None:
                        self._send_stream_event({"type": "delta", "content": delta})

                    if len(requested_models) > 1:
                        response, content = _chat_multi_completion(
                            self.state.settings,
                            requested_models,
                            messages,
                            payload,
                            insecure=bool(payload.get("insecure")),
                            stream=True,
                            on_delta=send_delta,
                        )
                    else:
                        response, content = _stream_chat_completion(
                            self.state.settings,
                            model_id,
                            messages,
                            payload,
                            insecure=bool(payload.get("insecure")),
                            on_delta=send_delta,
                        )
                    self._send_stream_event({"type": "done", "content": content, "response": response})
                    conversation["messages"] = messages + [
                        {"role": "assistant", "content": content}
                    ]
                    if isinstance(response, dict) and isinstance(response.get("usage"), dict):
                        conversation["usage"] = dict(response["usage"])
                    self.state.upsert_conversation(conversation)
                    self.close_connection = True
                except SystemExit as exc:
                    self._send_stream_event(
                        {
                            "type": "error",
                            "error": str(exc.code or "request failed"),
                        }
                    )
                    self.close_connection = True
                return
            if len(requested_models) > 1:
                response, content = _chat_multi_completion(
                    self.state.settings,
                    requested_models,
                    messages,
                    payload,
                    insecure=bool(payload.get("insecure")),
                )
                conversation["messages"] = messages + [
                    {"role": "assistant", "content": content}
                ]
                if isinstance(response, dict) and isinstance(response.get("usage"), dict):
                    conversation["usage"] = dict(response["usage"])
                self.state.upsert_conversation(conversation)
                self._send_json(200, response)
                return
            response = _chat_completion(
                self.state.settings,
                model_id,
                messages,
                payload,
                insecure=bool(payload.get("insecure")),
            )
            conversation["messages"] = messages + [
                {"role": "assistant", "content": _chat_response_text(response, model_id)}
            ]
            if isinstance(response, dict) and isinstance(response.get("usage"), dict):
                conversation["usage"] = dict(response["usage"])
            self.state.upsert_conversation(conversation)
        except SystemExit as exc:
            code = int(exc.code or 1)
            self._send_json(code if code >= 400 else 400, {"error": "request failed"})
            return
        self._send_json(200, response)


@dataclass
class QwenChatState:
    settings_path: pathlib.Path
    settings: dict[str, Any]
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False, compare=False)

    @classmethod
    def load(cls, settings_path: pathlib.Path) -> "QwenChatState":
        settings = load_json(settings_path)
        normalize_existing_providers(settings)
        settings["$version"] = 4
        settings.setdefault("modelProviders", {})
        settings.setdefault("promptTemplates", [])
        settings.setdefault("folders", [])
        settings.setdefault("conversations", [])
        settings.setdefault("skills", [])
        settings.setdefault("memories", [])
        settings.setdefault("notes", [])
        settings.setdefault("artifacts", [])
        settings.setdefault("knowledgeBases", [])
        settings.setdefault("toolServers", [])
        settings.setdefault("webhooks", [])
        settings.setdefault("agents", [])
        settings.setdefault("files", [])
        normalize_conversations(settings)
        normalize_folders(settings)
        return cls(settings_path=settings_path, settings=settings)

    def reload(self) -> None:
        with self._lock:
            fresh = load_json(self.settings_path)
            normalize_existing_providers(fresh)
            fresh["$version"] = 4
            fresh.setdefault("modelProviders", {})
            fresh.setdefault("promptTemplates", [])
            fresh.setdefault("folders", [])
            fresh.setdefault("conversations", [])
            fresh.setdefault("skills", [])
            fresh.setdefault("memories", [])
            fresh.setdefault("notes", [])
            fresh.setdefault("artifacts", [])
            fresh.setdefault("knowledgeBases", [])
            fresh.setdefault("toolServers", [])
            fresh.setdefault("webhooks", [])
            fresh.setdefault("agents", [])
            fresh.setdefault("files", [])
            normalize_conversations(fresh)
            normalize_folders(fresh)
            self.settings = fresh

    def _save(self) -> None:
        with self._lock:
            normalize_conversations(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def upsert_conversation(self, conversation: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(conversation, dict):
            die("conversation must be a JSON object")
        with self._lock:
            item = dict(conversation)
            convo_id = item.get("id")
            if not isinstance(convo_id, str) or not convo_id.strip():
                title = str(item.get("title") or item.get("model") or "chat").strip()
                item["id"] = f"{slugify(title)}-{int(time.time())}"
            else:
                item["id"] = convo_id.strip()
            if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                item["title"] = str(item["id"])
            if isinstance(item.get("messages"), list):
                normalized_messages: list[dict[str, str]] = []
                for msg in item["messages"]:
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role")
                    content = msg.get("content")
                    if (
                        isinstance(role, str)
                        and role.strip()
                        and isinstance(content, str)
                        and content.strip()
                    ):
                        normalized_messages.append({"role": role.strip(), "content": content})
                if normalized_messages:
                    item["messages"] = normalized_messages
                    item["transcript"] = "\n".join(
                        f"{msg['role']}: {msg['content']}" for msg in normalized_messages
                    )
            conversations = self.settings.setdefault("conversations", [])
            if not isinstance(conversations, list):
                conversations = []
                self.settings["conversations"] = conversations
            conversations[:] = [c for c in conversations if str(c.get("id")) != str(item["id"])]
            conversations.append(item)
            conversations.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_conversations(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return item

    def upsert_prompt_template(self, template: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(template, dict):
            die("prompt template must be a JSON object")
        with self._lock:
            item = dict(template)
            template_id = item.get("id")
            if not isinstance(template_id, str) or not template_id.strip():
                name = str(item.get("name") or item.get("title") or item.get("content") or "template").strip()
                item["id"] = f"{slugify(name)}-{int(time.time())}"
            else:
                item["id"] = template_id.strip()
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item["id"])
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                die("prompt template content is required")
            templates = self.settings.setdefault("promptTemplates", [])
            if not isinstance(templates, list):
                templates = []
                self.settings["promptTemplates"] = templates
            templates[:] = [t for t in templates if str(t.get("id")) != str(item["id"])]
            templates.append(
                {
                    "id": str(item["id"]),
                    "name": str(item["name"]),
                    "content": str(content),
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str)
                        and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                }
            )
            templates.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_prompt_templates(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next(
                (entry for entry in templates if str(entry.get("id")) == str(item["id"])),
                {
                    "id": str(item["id"]),
                    "name": str(item["name"]),
                    "content": str(content),
                },
            )

    def upsert_note(self, note: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(note, dict):
            die("note must be a JSON object")
        with self._lock:
            item = dict(note)
            note_id = item.get("id")
            if not isinstance(note_id, str) or not note_id.strip():
                title = str(item.get("title") or item.get("body") or item.get("content") or "note").strip()
                item["id"] = slugify(title)
            else:
                item["id"] = note_id.strip()
            if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                item["title"] = str(item["id"])
            body = item.get("body", item.get("content"))
            if not isinstance(body, str) or not body.strip():
                die("note body is required")
            notes = self.settings.setdefault("notes", [])
            if not isinstance(notes, list):
                notes = []
                self.settings["notes"] = notes
            notes[:] = [entry for entry in notes if str(entry.get("id")) != str(item["id"])]
            normalized: dict[str, Any] = {
                "id": str(item["id"]),
                "title": str(item["title"]).strip(),
                "body": str(body),
            }
            if isinstance(item.get("files", item.get("attachments")), list):
                files = [str(entry).strip() for entry in item.get("files", item.get("attachments", [])) if str(entry).strip()]
                if files:
                    normalized["files"] = files
            if isinstance(item.get("images"), list):
                images = [str(entry).strip() for entry in item.get("images", []) if str(entry).strip()]
                if images:
                    normalized["images"] = images
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized["tags"] = tags
            if item.get("pinned") is not None:
                normalized["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized["archived"] = bool(item["archived"])
            notes.append(normalized)
            notes.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_notes(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next((entry for entry in notes if str(entry.get("id")) == str(item["id"])), normalized)

    def delete_note(self, note_id: str) -> None:
        note_id = note_id.strip()
        if not note_id:
            die("note id is required")
        with self._lock:
            notes = self.settings.setdefault("notes", [])
            if not isinstance(notes, list):
                notes = []
                self.settings["notes"] = notes
            before = len(notes)
            notes[:] = [entry for entry in notes if str(entry.get("id")) != note_id]
            if len(notes) == before:
                die(f"note '{note_id}' not found")
            normalize_notes(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def upsert_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(artifact, dict):
            die("artifact must be a JSON object")
        with self._lock:
            item = dict(artifact)
            artifact_id = item.get("id")
            if not isinstance(artifact_id, str) or not artifact_id.strip():
                title = str(item.get("title") or item.get("content") or "artifact").strip()
                item["id"] = slugify(title)
            else:
                item["id"] = artifact_id.strip()
            if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                item["title"] = str(item["id"])
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                die("artifact content is required")
            artifacts = self.settings.setdefault("artifacts", [])
            if not isinstance(artifacts, list):
                artifacts = []
                self.settings["artifacts"] = artifacts
            artifacts[:] = [entry for entry in artifacts if str(entry.get("id")) != str(item["id"])]
            normalized: dict[str, Any] = {
                "id": str(item["id"]),
                "title": str(item["title"]).strip(),
                "content": str(content),
            }
            if isinstance(item.get("kind"), str) and str(item.get("kind")).strip():
                normalized["kind"] = str(item["kind"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized["tags"] = tags
            if item.get("pinned") is not None:
                normalized["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized["archived"] = bool(item["archived"])
            artifacts.append(normalized)
            artifacts.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_artifacts(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next((entry for entry in artifacts if str(entry.get("id")) == str(item["id"])), normalized)

    def delete_artifact(self, artifact_id: str) -> None:
        artifact_id = artifact_id.strip()
        if not artifact_id:
            die("artifact id is required")
        with self._lock:
            artifacts = self.settings.setdefault("artifacts", [])
            if not isinstance(artifacts, list):
                artifacts = []
                self.settings["artifacts"] = artifacts
            before = len(artifacts)
            artifacts[:] = [entry for entry in artifacts if str(entry.get("id")) != artifact_id]
            if len(artifacts) == before:
                die(f"artifact '{artifact_id}' not found")
            normalize_artifacts(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def upsert_knowledge_base(self, knowledge_base: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(knowledge_base, dict):
            die("knowledge base must be a JSON object")
        with self._lock:
            item = dict(knowledge_base)
            base_id = item.get("id")
            if not isinstance(base_id, str) or not base_id.strip():
                name = str(item.get("name") or item.get("sourceDir") or "knowledge base").strip()
                item["id"] = slugify(name)
            else:
                item["id"] = base_id.strip()
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item["id"])
            source_dir = item.get("sourceDir")
            if not isinstance(source_dir, str) or not source_dir.strip():
                die("knowledge base sourceDir is required")
            bases = self.settings.setdefault("knowledgeBases", [])
            if not isinstance(bases, list):
                bases = []
                self.settings["knowledgeBases"] = bases
            bases[:] = [entry for entry in bases if str(entry.get("id")) != str(item["id"])]
            normalized: dict[str, Any] = {
                "id": str(item["id"]),
                "name": str(item["name"]).strip(),
                "sourceDir": str(source_dir).strip(),
            }
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized["description"] = str(item["description"]).strip()
            if item.get("enabled") is not None:
                normalized["enabled"] = bool(item["enabled"])
            for key in ("sources", "tags"):
                value = item.get(key)
                if isinstance(value, list):
                    entries = [str(entry).strip() for entry in value if str(entry).strip()]
                    if entries:
                        normalized[key] = entries
            bases.append(normalized)
            bases.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_knowledge_bases(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next((entry for entry in bases if str(entry.get("id")) == str(item["id"])), normalized)

    def delete_knowledge_base(self, base_id: str) -> None:
        base_id = base_id.strip()
        if not base_id:
            die("knowledge base id is required")
        with self._lock:
            bases = self.settings.setdefault("knowledgeBases", [])
            if not isinstance(bases, list):
                bases = []
                self.settings["knowledgeBases"] = bases
            before = len(bases)
            bases[:] = [entry for entry in bases if str(entry.get("id")) != base_id]
            if len(bases) == before:
                die(f"knowledge base '{base_id}' not found")
            normalize_knowledge_bases(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def refresh_knowledge_base(
        self,
        base_id: str,
        chunk_size: int = 2000,
        overlap: int = 200,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        base_id = base_id.strip()
        if not base_id:
            die("knowledge base id is required")
        with self._lock:
            bases = self.settings.setdefault("knowledgeBases", [])
            if not isinstance(bases, list):
                bases = []
                self.settings["knowledgeBases"] = bases
            base = next((entry for entry in bases if str(entry.get("id")) == base_id), None)
            if base is None:
                die(f"knowledge base '{base_id}' not found")
            source_label, index, refreshed_base = _refresh_knowledge_base_entry(
                base,
                base_id,
                chunk_size,
                overlap,
                timeout,
            )
            indexes = self.settings.setdefault("knowledgeIndexes", [])
            if not isinstance(indexes, list):
                indexes = []
                self.settings["knowledgeIndexes"] = indexes
            indexes[:] = [item for item in indexes if str(item.get("baseId")) != base_id]
            indexes.append(index)
            indexes.sort(key=lambda x: str(x.get("id", "")).lower())
            bases[:] = [entry for entry in bases if str(entry.get("id")) != base_id]
            bases.append(refreshed_base)
            bases.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_knowledge_bases(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return source_label, index, refreshed_base

    def import_knowledge_sources(self, payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        bases_payload = _normalize_knowledge_source_payload(payload)
        indexes_payload = _normalize_knowledge_index_payload(payload)
        if not bases_payload and not indexes_payload:
            die("knowledge source import must include knowledgeBases or knowledgeIndexes")
        with self._lock:
            bases = self.settings.setdefault("knowledgeBases", [])
            if not isinstance(bases, list):
                bases = []
                self.settings["knowledgeBases"] = bases
            indexes = self.settings.setdefault("knowledgeIndexes", [])
            if not isinstance(indexes, list):
                indexes = []
                self.settings["knowledgeIndexes"] = indexes
            merged_bases = {str(item.get("id")): item for item in bases if isinstance(item, dict)}
            for item in bases_payload:
                if not isinstance(item, dict):
                    continue
                if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                    item = dict(item)
                    item["id"] = slugify(str(item.get("name") or "knowledge"))
                if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                    item["name"] = str(item.get("id"))
                merged_bases[str(item.get("id"))] = item
            merged_indexes = {str(item.get("id")): item for item in indexes if isinstance(item, dict)}
            for item in indexes_payload:
                if not isinstance(item, dict):
                    continue
                if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                    item = dict(item)
                    item["id"] = slugify(str(item.get("name") or item.get("baseId") or "knowledge-index"))
                if not isinstance(item.get("baseId"), str) or not str(item.get("baseId")).strip():
                    item["baseId"] = str(item.get("id"))
                merged_indexes[str(item.get("id"))] = item
            bases[:] = sorted(merged_bases.values(), key=lambda x: str(x.get("id", "")).lower())
            indexes[:] = sorted(merged_indexes.values(), key=lambda x: str(x.get("id", "")).lower())
            normalize_knowledge_bases(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return bases, indexes

    def sync_knowledge_bases(
        self,
        base_id: str | None = None,
        *,
        chunk_size: int = 2000,
        overlap: int = 200,
        timeout: int = DEFAULT_TIMEOUT,
        output_dir: pathlib.Path | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            bases = self.settings.setdefault("knowledgeBases", [])
            if not isinstance(bases, list):
                bases = []
                self.settings["knowledgeBases"] = bases
            selected_bases = [
                item
                for item in bases
                if isinstance(item, dict)
                and (not base_id or str(item.get("id")) == base_id)
            ]
            if base_id and not selected_bases:
                die(f"knowledge base '{base_id}' not found")
            if not selected_bases:
                die("no knowledge bases to sync")
            indexes = self.settings.setdefault("knowledgeIndexes", [])
            if not isinstance(indexes, list):
                indexes = []
                self.settings["knowledgeIndexes"] = indexes
            refreshed_indexes: list[dict[str, Any]] = []
            refreshed_bases: list[dict[str, Any]] = []
            if output_dir is not None:
                output_dir.mkdir(parents=True, exist_ok=True)
            for base in selected_bases:
                current_base_id = str(base.get("id", "")).strip()
                if not current_base_id:
                    continue
                source_label, index, refreshed_base = self.refresh_knowledge_base(
                    current_base_id,
                    chunk_size,
                    overlap,
                    timeout,
                )
                refreshed_indexes.append(index)
                refreshed_bases.append(refreshed_base)
                if output_dir is not None:
                    (output_dir / f"{current_base_id}.json").write_text(
                        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                eprint(f"Synced knowledge base: {current_base_id} ({source_label})")
            refreshed_ids = {str(item.get("id")) for item in refreshed_bases}
            remaining_bases = [b for b in bases if str(b.get("id")) not in refreshed_ids]
            remaining_bases.extend(refreshed_bases)
            bases[:] = sorted(remaining_bases, key=lambda x: str(x.get("id", "")).lower())
            indexes[:] = sorted(indexes, key=lambda x: str(x.get("id", "")).lower())
            normalize_knowledge_bases(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            manifest = {
                "knowledgeBases": bases,
                "knowledgeIndexes": indexes,
                "refreshed": [str(item.get("baseId", "")) for item in refreshed_indexes],
            }
            if output_dir is not None:
                (output_dir / "manifest.json").write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            return manifest

    def watch_knowledge_bases(
        self,
        base_id: str | None = None,
        *,
        iterations: int = 1,
        interval: float = 0.0,
        chunk_size: int = 2000,
        overlap: int = 200,
        timeout: int = DEFAULT_TIMEOUT,
        output_dir: pathlib.Path | None = None,
    ) -> dict[str, Any]:
        iterations = max(1, int(iterations or 1))
        interval = max(0.0, float(interval or 0.0))
        manifest: dict[str, Any] = {}
        for index in range(iterations):
            manifest = self.sync_knowledge_bases(
                base_id,
                chunk_size=chunk_size,
                overlap=overlap,
                timeout=timeout,
                output_dir=output_dir,
            )
            if index + 1 < iterations and interval > 0:
                time.sleep(interval)
        return manifest

    def upsert_tool_server(self, tool_server: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(tool_server, dict):
            die("tool server must be a JSON object")
        with self._lock:
            item = dict(tool_server)
            server_id = item.get("id")
            if not isinstance(server_id, str) or not server_id.strip():
                name = str(item.get("name") or item.get("endpoint") or item.get("url") or "tool server").strip()
                item["id"] = slugify(name)
            else:
                item["id"] = server_id.strip()
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item["id"])
            endpoint = item.get("endpoint", item.get("url"))
            if not isinstance(endpoint, str) or not endpoint.strip():
                die("tool server endpoint is required")
            servers = self.settings.setdefault("toolServers", [])
            if not isinstance(servers, list):
                servers = []
                self.settings["toolServers"] = servers
            servers[:] = [entry for entry in servers if str(entry.get("id")) != str(item["id"])]
            normalized: dict[str, Any] = {
                "id": str(item["id"]),
                "name": str(item["name"]).strip(),
                "endpoint": str(endpoint).strip(),
            }
            if isinstance(item.get("type"), str) and str(item.get("type")).strip():
                normalized["type"] = str(item["type"]).strip()
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized["description"] = str(item["description"]).strip()
            if item.get("auth") is not None:
                normalized["auth"] = item["auth"]
            if item.get("enabled") is not None:
                normalized["enabled"] = bool(item["enabled"])
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized["tags"] = tags
            servers.append(normalized)
            servers.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_tool_servers(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next((entry for entry in servers if str(entry.get("id")) == str(item["id"])), normalized)

    def delete_tool_server(self, tool_server_id: str) -> None:
        tool_server_id = tool_server_id.strip()
        if not tool_server_id:
            die("tool server id is required")
        with self._lock:
            servers = self.settings.setdefault("toolServers", [])
            if not isinstance(servers, list):
                servers = []
                self.settings["toolServers"] = servers
            before = len(servers)
            servers[:] = [entry for entry in servers if str(entry.get("id")) != tool_server_id]
            if len(servers) == before:
                die(f"tool server '{tool_server_id}' not found")
            normalize_tool_servers(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def delete_conversation(self, convo_id: str) -> None:
        convo_id = convo_id.strip()
        if not convo_id:
            die("conversation id is required")
        with self._lock:
            conversations = self.settings.setdefault("conversations", [])
            if not isinstance(conversations, list):
                conversations = []
                self.settings["conversations"] = conversations
            conversations[:] = [c for c in conversations if str(c.get("id")) != convo_id]
            normalize_conversations(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def delete_prompt_template(self, template_id: str) -> None:
        template_id = template_id.strip()
        if not template_id:
            die("prompt template id is required")
        with self._lock:
            templates = self.settings.setdefault("promptTemplates", [])
            if not isinstance(templates, list):
                templates = []
                self.settings["promptTemplates"] = templates
            templates[:] = [t for t in templates if str(t.get("id")) != template_id]
            normalize_prompt_templates(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def add_provider_presets(self) -> list[str]:
        with self._lock:
            settings = self.settings
            normalize_existing_providers(settings)
            settings["$version"] = 4
            settings.setdefault("general", {})
            settings.setdefault("ui", {})
            settings.setdefault("privacy", {})
            settings.setdefault("tools", {})
            settings.setdefault("security", {})
            settings.setdefault("model", {})
            settings["general"].setdefault("enableAutoUpdate", True)
            settings["ui"].setdefault("showMemoryUsage", True)
            settings["privacy"].setdefault("usageStatisticsEnabled", False)
            settings["tools"].setdefault("approvalMode", "default")
            settings["security"].setdefault("auth", {})
            apply_root_admin_emails(settings)

            providers = settings.setdefault("modelProviders", {})
            openai_configs = providers.setdefault("openai", [])
            if not isinstance(openai_configs, list):
                die("modelProviders.openai must be an array")

            existing_ids = {
                str(item.get("id"))
                for item in openai_configs
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            added: list[str] = []
            for key, preset in sorted(PRESETS.items()):
                model_id = f"{key}-provider"
                if model_id in existing_ids:
                    continue
                openai_configs.append(
                    {
                        "id": model_id,
                        "name": preset.name,
                        "description": (
                            f"Provider preset for {preset.name}; replace the placeholder "
                            f"model id with a real model supported by this provider."
                        ),
                        "baseUrl": normalize_url(preset.base_url),
                        "envKey": preset.env_key,
                        "generationConfig": {
                            "timeout": 120000,
                            "maxRetries": 3,
                        },
                    }
                )
                existing_ids.add(model_id)
                added.append(key)

            errors = validate_settings(settings)
            if errors:
                die("generated configuration failed validation:\n- " + "\n- ".join(errors))
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return added

    def delete_provider_model(self, model_id: str) -> bool:
        model_id = model_id.strip()
        if not model_id:
            die("provider model id is required")
        with self._lock:
            providers = self.settings.setdefault("modelProviders", {})
            if not isinstance(providers, dict):
                providers = {}
                self.settings["modelProviders"] = providers
            removed = False
            for key, value in list(providers.items()):
                if not isinstance(value, list):
                    providers[key] = []
                    continue
                before = len(value)
                value[:] = [item for item in value if str(item.get("id")) != model_id]
                if len(value) != before:
                    removed = True
            if not removed:
                die(f"provider model '{model_id}' not found")
            normalize_existing_providers(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return True

    def upsert_folder(self, folder: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(folder, dict):
            die("workspace must be a JSON object")
        with self._lock:
            item = dict(folder)
            folder_id = item.get("id")
            if not isinstance(folder_id, str) or not folder_id.strip():
                name = str(item.get("name") or item.get("title") or "workspace").strip()
                item["id"] = slugify(name)
            else:
                item["id"] = folder_id.strip()
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item["id"])
            folders = self.settings.setdefault("folders", [])
            if not isinstance(folders, list):
                folders = []
                self.settings["folders"] = folders
            folders[:] = [entry for entry in folders if str(entry.get("id")) != str(item["id"])]
            normalized: dict[str, Any] = {
                "id": str(item["id"]),
                "name": str(item["name"]).strip(),
            }
            for key in ("parentId", "systemPrompt", "description", "sourceDir"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    normalized[key] = value.strip()
            for key in ("knowledge", "tags"):
                value = item.get(key)
                if isinstance(value, list):
                    entries = [str(entry).strip() for entry in value if str(entry).strip()]
                    if entries:
                        normalized[key] = entries
            if item.get("pinned") is not None:
                normalized["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized["archived"] = bool(item["archived"])
            if item.get("unreadCount") is not None:
                try:
                    normalized["unreadCount"] = int(item["unreadCount"])
                except (TypeError, ValueError):
                    pass
            folders.append(normalized)
            folders.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_folders(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next(
                (entry for entry in folders if str(entry.get("id")) == str(item["id"])),
                normalized,
            )

    def delete_folder(self, folder_id: str) -> None:
        folder_id = folder_id.strip()
        if not folder_id:
            die("workspace id is required")
        with self._lock:
            folders = self.settings.setdefault("folders", [])
            if not isinstance(folders, list):
                folders = []
                self.settings["folders"] = folders
            before = len(folders)
            folders[:] = [entry for entry in folders if str(entry.get("id")) != folder_id]
            if len(folders) == before:
                die(f"workspace '{folder_id}' not found")
            conversations = self.settings.setdefault("conversations", [])
            if isinstance(conversations, list):
                for convo in conversations:
                    if isinstance(convo, dict) and str(convo.get("folderId", "")) == folder_id:
                        convo["folderId"] = ""
            normalize_folders(self.settings)
            normalize_conversations(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def upsert_file(self, file_item: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(file_item, dict):
            die("file must be a JSON object")
        with self._lock:
            item = dict(file_item)
            file_id = item.get("id")
            if not isinstance(file_id, str) or not file_id.strip():
                name = str(item.get("name") or item.get("title") or item.get("path") or "file").strip()
                item["id"] = f"{slugify(name)}-{int(time.time())}"
            else:
                item["id"] = file_id.strip()
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item["id"])
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                die("file content is required")
            if not isinstance(item.get("kind"), str) or not str(item.get("kind")).strip():
                guessed_kind, _ = mimetypes.guess_type(str(item.get("name") or item.get("path") or item["id"]))
                item["kind"] = guessed_kind or "text"
            files = self.settings.setdefault("files", [])
            if not isinstance(files, list):
                files = []
                self.settings["files"] = files
            files[:] = [f for f in files if str(f.get("id")) != str(item["id"])]
            files.append(
                {
                    "id": str(item["id"]),
                    "name": str(item["name"]),
                    "content": str(content),
                    **(
                        {"path": str(item["path"]).strip()}
                        if isinstance(item.get("path"), str) and str(item.get("path")).strip()
                        else {}
                    ),
                    **(
                        {"kind": str(item["kind"]).strip()}
                        if isinstance(item.get("kind"), str) and str(item.get("kind")).strip()
                        else {}
                    ),
                    **(
                        {"description": str(item["description"]).strip()}
                        if isinstance(item.get("description"), str) and str(item.get("description")).strip()
                        else {}
                    ),
                    **(
                        {"tags": [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]}
                        if isinstance(item.get("tags"), list)
                        else {}
                    ),
                    **(
                        {"size": int(item["size"])}
                        if item.get("size") is not None
                        and str(item.get("size")).strip()
                        and str(item.get("size")).strip().isdigit()
                        else {}
                    ),
                }
            )
            normalize_files(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next((entry for entry in files if str(entry.get("id")) == str(item["id"])), files[-1])

    def upsert_skill(self, skill: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(skill, dict):
            die("skill must be a JSON object")
        with self._lock:
            item = dict(skill)
            skill_id = item.get("id")
            if not isinstance(skill_id, str) or not skill_id.strip():
                name = str(item.get("name") or item.get("title") or item.get("content") or "skill").strip()
                item["id"] = slugify(name)
            else:
                item["id"] = skill_id.strip()
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item["id"])
            content = item.get("content", item.get("instructions"))
            if not isinstance(content, str) or not content.strip():
                die("skill content is required")
            skills = self.settings.setdefault("skills", [])
            if not isinstance(skills, list):
                skills = []
                self.settings["skills"] = skills
            skills[:] = [entry for entry in skills if str(entry.get("id")) != str(item["id"])]
            normalized: dict[str, Any] = {
                "id": str(item["id"]),
                "name": str(item["name"]).strip(),
                "content": str(content),
            }
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized["description"] = str(item["description"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized["tags"] = tags
            if item.get("pinned") is not None:
                normalized["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized["archived"] = bool(item["archived"])
            skills.append(normalized)
            skills.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_skills(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next((entry for entry in skills if str(entry.get("id")) == str(item["id"])), normalized)

    def delete_skill(self, skill_id: str) -> None:
        skill_id = skill_id.strip()
        if not skill_id:
            die("skill id is required")
        with self._lock:
            skills = self.settings.setdefault("skills", [])
            if not isinstance(skills, list):
                skills = []
                self.settings["skills"] = skills
            before = len(skills)
            skills[:] = [entry for entry in skills if str(entry.get("id")) != skill_id]
            if len(skills) == before:
                die(f"skill '{skill_id}' not found")
            normalize_skills(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def upsert_agent(self, agent: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(agent, dict):
            die("agent must be a JSON object")
        with self._lock:
            item = dict(agent)
            agent_id = item.get("id")
            if not isinstance(agent_id, str) or not agent_id.strip():
                name = str(item.get("name") or item.get("baseModel") or item.get("model") or "agent").strip()
                item["id"] = slugify(name)
            else:
                item["id"] = agent_id.strip()
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item["id"])
            base_model = item.get("baseModel", item.get("model"))
            if not isinstance(base_model, str) or not base_model.strip():
                die("agent baseModel is required")
            system_prompt = item.get("systemPrompt", item.get("instructions", item.get("prompt")))
            agents = self.settings.setdefault("agents", [])
            if not isinstance(agents, list):
                agents = []
                self.settings["agents"] = agents
            agents[:] = [entry for entry in agents if str(entry.get("id")) != str(item["id"])]
            normalized: dict[str, Any] = {
                "id": str(item["id"]),
                "name": str(item["name"]).strip(),
                "baseModel": str(base_model).strip(),
            }
            if isinstance(system_prompt, str) and system_prompt.strip():
                normalized["systemPrompt"] = system_prompt.strip()
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized["description"] = str(item["description"]).strip()
            folder_id = item.get("folderId", item.get("folder"))
            if isinstance(folder_id, str) and str(folder_id).strip():
                normalized["folderId"] = str(folder_id).strip()
            for key in ("tags", "tools", "knowledge", "skills"):
                value = item.get(key)
                if isinstance(value, list):
                    entries = [str(entry).strip() for entry in value if str(entry).strip()]
                    if entries:
                        normalized[key] = entries
            if isinstance(item.get("parameters"), dict):
                normalized["parameters"] = item["parameters"]
            if isinstance(item.get("avatar"), str) and str(item.get("avatar")).strip():
                normalized["avatar"] = str(item["avatar"]).strip()
            if isinstance(item.get("voice"), str) and str(item.get("voice")).strip():
                normalized["voice"] = str(item["voice"]).strip()
            if isinstance(item.get("visibility"), str) and str(item.get("visibility")).strip():
                normalized["visibility"] = str(item["visibility"]).strip()
            if item.get("pinned") is not None:
                normalized["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized["archived"] = bool(item["archived"])
            agents.append(normalized)
            agents.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_agents(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next((entry for entry in agents if str(entry.get("id")) == str(item["id"])), normalized)

    def delete_agent(self, agent_id: str) -> None:
        agent_id = agent_id.strip()
        if not agent_id:
            die("agent id is required")
        with self._lock:
            agents = self.settings.setdefault("agents", [])
            if not isinstance(agents, list):
                agents = []
                self.settings["agents"] = agents
            before = len(agents)
            agents[:] = [entry for entry in agents if str(entry.get("id")) != agent_id]
            if len(agents) == before:
                die(f"agent '{agent_id}' not found")
            normalize_agents(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def upsert_webhook(self, webhook: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(webhook, dict):
            die("webhook must be a JSON object")
        with self._lock:
            item = dict(webhook)
            webhook_id = item.get("id")
            if not isinstance(webhook_id, str) or not webhook_id.strip():
                name = str(item.get("name") or item.get("url") or "webhook").strip()
                item["id"] = slugify(name)
            else:
                item["id"] = webhook_id.strip()
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item["id"])
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                die("webhook url is required")
            webhooks = self.settings.setdefault("webhooks", [])
            if not isinstance(webhooks, list):
                webhooks = []
                self.settings["webhooks"] = webhooks
            webhooks[:] = [entry for entry in webhooks if str(entry.get("id")) != str(item["id"])]
            normalized: dict[str, Any] = {
                "id": str(item["id"]),
                "name": str(item["name"]).strip(),
                "url": str(url).strip(),
            }
            events = item.get("events")
            if isinstance(events, list):
                entries = [str(entry).strip() for entry in events if str(entry).strip()]
                if entries:
                    normalized["events"] = entries
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized["description"] = str(item["description"]).strip()
            if isinstance(item.get("secret"), str) and str(item.get("secret")).strip():
                normalized["secret"] = str(item["secret"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized["tags"] = tags
            if item.get("enabled") is not None:
                normalized["enabled"] = bool(item["enabled"])
            webhooks.append(normalized)
            webhooks.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_webhooks(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next((entry for entry in webhooks if str(entry.get("id")) == str(item["id"])), normalized)

    def delete_webhook(self, webhook_id: str) -> None:
        webhook_id = webhook_id.strip()
        if not webhook_id:
            die("webhook id is required")
        with self._lock:
            webhooks = self.settings.setdefault("webhooks", [])
            if not isinstance(webhooks, list):
                webhooks = []
                self.settings["webhooks"] = webhooks
            before = len(webhooks)
            webhooks[:] = [entry for entry in webhooks if str(entry.get("id")) != webhook_id]
            if len(webhooks) == before:
                die(f"webhook '{webhook_id}' not found")
            normalize_webhooks(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def upsert_memory(self, memory: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(memory, dict):
            die("memory must be a JSON object")
        with self._lock:
            item = dict(memory)
            memory_id = item.get("id")
            if not isinstance(memory_id, str) or not memory_id.strip():
                title = str(item.get("title") or item.get("content") or "memory").strip()
                item["id"] = slugify(title)
            else:
                item["id"] = memory_id.strip()
            if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                item["title"] = str(item["id"])
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                die("memory content is required")
            memories = self.settings.setdefault("memories", [])
            if not isinstance(memories, list):
                memories = []
                self.settings["memories"] = memories
            memories[:] = [entry for entry in memories if str(entry.get("id")) != str(item["id"])]
            normalized: dict[str, Any] = {
                "id": str(item["id"]),
                "title": str(item["title"]).strip(),
                "content": str(content),
            }
            if isinstance(item.get("scope"), str) and str(item.get("scope")).strip():
                normalized["scope"] = str(item["scope"]).strip()
            if isinstance(item.get("source"), str) and str(item.get("source")).strip():
                normalized["source"] = str(item["source"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized["tags"] = tags
            if item.get("pinned") is not None:
                normalized["pinned"] = bool(item["pinned"])
            if item.get("archived") is not None:
                normalized["archived"] = bool(item["archived"])
            memories.append(normalized)
            memories.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_memories(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return next((entry for entry in memories if str(entry.get("id")) == str(item["id"])), normalized)

    def delete_memory(self, memory_id: str) -> None:
        memory_id = memory_id.strip()
        if not memory_id:
            die("memory id is required")
        with self._lock:
            memories = self.settings.setdefault("memories", [])
            if not isinstance(memories, list):
                memories = []
                self.settings["memories"] = memories
            before = len(memories)
            memories[:] = [entry for entry in memories if str(entry.get("id")) != memory_id]
            if len(memories) == before:
                die(f"memory '{memory_id}' not found")
            normalize_memories(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def delete_file(self, file_id: str) -> None:
        file_id = file_id.strip()
        if not file_id:
            die("file id is required")
        with self._lock:
            files = self.settings.setdefault("files", [])
            if not isinstance(files, list):
                files = []
                self.settings["files"] = files
            files[:] = [f for f in files if str(f.get("id")) != file_id]
            normalize_files(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)

    def import_files(self, payload: Any) -> list[dict[str, Any]]:
        imported = _normalize_file_source_payload(payload)
        if not imported:
            die("file import must include files")
        with self._lock:
            files = self.settings.setdefault("files", [])
            if not isinstance(files, list):
                files = []
                self.settings["files"] = files
            existing = {str(item.get("id")): item for item in files if isinstance(item, dict)}
            for item in imported:
                if not isinstance(item, dict):
                    continue
                if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                    item = dict(item)
                    item["id"] = slugify(str(item.get("name") or item.get("title") or "file"))
                if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                    item["name"] = str(item.get("id"))
                if not isinstance(item.get("content"), str) or not str(item.get("content")).strip():
                    continue
                existing[str(item.get("id"))] = item
            files[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
            normalize_files(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return files

    def clone_file(self, file_id: str, new_id: str | None = None, name: str | None = None) -> dict[str, Any]:
        file_id = file_id.strip()
        if not file_id:
            die("file id is required")
        with self._lock:
            files = self.settings.setdefault("files", [])
            if not isinstance(files, list):
                files = []
                self.settings["files"] = files
            clone = _clone_registry_item(files, file_id, new_id=new_id)
            if isinstance(name, str) and name.strip():
                clone["name"] = name.strip()
            files.append(clone)
            files.sort(key=lambda x: str(x.get("id", "")).lower())
            normalize_files(self.settings)
            self.settings["$version"] = 4
            atomic_write_json(self.settings_path, self.settings)
            return clone


def command_serve(args: argparse.Namespace) -> int:
    settings_path = pathlib.Path(args.settings).expanduser()
    state = QwenChatState.load(settings_path)
    server = QwenChatHTTPServer((args.host, args.port), QwenChatRequestHandler)
    server.state = state  # type: ignore[attr-defined]
    host, port = server.server_address[:2]
    print(f"Qwen chat server listening on http://{host}:{port}/")
    print(f"Settings: {settings_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down.")
    finally:
        server.server_close()
    return 0


def command_folders(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_folders(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("files", [])
    settings.setdefault("memories", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    folders = settings.setdefault("folders", [])
    if not isinstance(folders, list):
        die("folders must be an array")

    if args.action in (None, "list"):
        print("Folders:")
        print("-" * 100)
        if not folders:
            print("(none)")
            return 0
        fmt = "{:<18} {:<24} {:<18} {:<12}"
        print(fmt.format("ID", "NAME", "PARENT", "UNREAD"))
        print("-" * 100)
        for item in folders:
            print(fmt.format(str(item.get("id", "")), str(item.get("name", ""))[:24], str(item.get("parentId", ""))[:18], str(item.get("unreadCount", 0))[:12]))
        return 0

    if args.action == "add":
        folder_id = args.id or slugify(args.name)
        new_folder: dict[str, Any] = {"id": folder_id, "name": args.name}
        if args.parent:
            new_folder["parentId"] = args.parent
        if args.system_prompt:
            new_folder["systemPrompt"] = args.system_prompt
        if args.source_dir:
            new_folder["sourceDir"] = args.source_dir
        if args.description:
            new_folder["description"] = args.description
        if args.knowledge:
            new_folder["knowledge"] = [item for item in args.knowledge if item]
        if args.tag:
            new_folder["tags"] = [item for item in args.tag if item]
        if args.pinned is not None:
            new_folder["pinned"] = args.pinned
        if args.archived is not None:
            new_folder["archived"] = args.archived
        if args.unread_count is not None:
            new_folder["unreadCount"] = args.unread_count
        folders[:] = [folder for folder in folders if str(folder.get("id")) != folder_id]
        folders.append(new_folder)
        folders.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(folders)
        folders[:] = [folder for folder in folders if str(folder.get("id")) != args.id]
        if len(folders) == before:
            die(f"folder '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_folder_source(source)
        if not imported:
            die(f"no folders found in {source}")
        existing = {str(folder.get("id")): folder for folder in folders if isinstance(folder, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "folder"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        folders[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"folders": folders}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported folders: {output}")
        return 0
    elif args.action == "share":
        folder = _find_folder(folders, args.id)
        if folder is None:
            die(f"folder '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(folder, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_folder_html(folder)
        else:
            rendered = render_folder_md(folder)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared folder: {output}")
        return 0
    elif args.action == "clone":
        folder = next((item for item in folders if isinstance(item, dict) and str(item.get("id")) == args.id), None)
        if folder is None:
            die(f"folder '{args.id}' not found")
        clone = dict(folder)
        clone_id = args.new_id or slugify(f"{str(folder.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in folders):
            die(f"folder '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.parent is not None:
            clone["parentId"] = args.parent
        if args.system_prompt is not None:
            clone["systemPrompt"] = args.system_prompt
        if args.source_dir is not None:
            clone["sourceDir"] = args.source_dir
        if args.description is not None:
            clone["description"] = args.description
        if args.knowledge is not None:
            clone["knowledge"] = [item for item in args.knowledge if item]
        if args.tag is not None:
            clone["tags"] = [item for item in args.tag if item]
        if args.pinned is not None:
            clone["pinned"] = args.pinned
        if args.archived is not None:
            clone["archived"] = args.archived
        if args.unread_count is not None:
            clone["unreadCount"] = args.unread_count
        folders.append(clone)
        folders.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"folder": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned folder: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported folders action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Folders: {len(folders)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def command_conversations(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_conversations(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    conversations = settings.setdefault("conversations", [])
    if not isinstance(conversations, list):
        die("conversations must be an array")
    folders = settings.get("folders", [])
    if not isinstance(folders, list):
        die("folders must be an array")

    if args.action in (None, "list"):
        print("Conversations:")
        print("-" * 80)
        if not conversations:
            print("(none)")
            return 0
        fmt = "{:<18} {:<24} {:<14} {:<12}"
        print(fmt.format("ID", "TITLE", "FOLDER", "STATE"))
        print("-" * 80)
        for item in conversations:
            state = "pinned" if item.get("pinned") else "active"
            if item.get("archived"):
                state = "archived"
            print(
                fmt.format(
                    str(item.get("id", "")),
                    str(item.get("title", ""))[:24],
                    str(item.get("folderId", ""))[:14],
                    state,
                )
            )
        return 0

    if args.action == "add":
        convo_id = args.id or slugify(args.title)
        new_convo: dict[str, Any] = {
            "id": convo_id,
            "title": args.title,
        }
        if args.folder:
            new_convo["folderId"] = args.folder
            _apply_folder_defaults(new_convo, _find_folder(folders, args.folder))
        if args.system_prompt:
            new_convo["systemPrompt"] = args.system_prompt
        if args.knowledge:
            new_convo["knowledge"] = [item for item in args.knowledge if item]
        if args.file:
            new_convo["files"] = [item for item in args.file if item]
        if args.image:
            new_convo["images"] = [item for item in args.image if item]
        if args.transcript:
            new_convo["transcript"] = args.transcript
        if args.message:
            messages: list[dict[str, str]] = []
            for item in args.message:
                role, sep, content = item.partition(":")
                if not sep:
                    continue
                role = role.strip()
                content = content.strip()
                if role and content:
                    messages.append({"role": role, "content": content})
            if messages:
                new_convo["messages"] = messages
                if "transcript" not in new_convo:
                    new_convo["transcript"] = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        if args.tag:
            new_convo["tags"] = [tag for tag in args.tag if tag]
        if args.pinned is not None:
            new_convo["pinned"] = args.pinned
        if args.archived is not None:
            new_convo["archived"] = args.archived
        conversations[:] = [c for c in conversations if str(c.get("id")) != convo_id]
        conversations.append(new_convo)
        conversations.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(conversations)
        conversations[:] = [c for c in conversations if str(c.get("id")) != args.id]
        if len(conversations) == before:
            die(f"conversation '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_conversation_source(source)
        if not imported:
            die(f"no conversations found in {source}")
        existing = {str(c.get("id")): c for c in conversations if isinstance(c, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("title") or "conversation"))
            if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                item["title"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        conversations[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"conversations": conversations}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported conversations: {output}")
        return 0
    elif args.action == "share":
        conversation = _find_conversation(conversations, args.id)
        if conversation is None:
            die(f"conversation '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "html":
            rendered = render_conversation_html(conversation)
        else:
            rendered = render_conversation_md(conversation)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared conversation: {output}")
        return 0
    elif args.action == "clone":
        clone = _clone_registry_item(
            conversations,
            args.id,
            new_id=args.new_id,
            new_title=args.title,
        )
        conversations.append(clone)
        conversations.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"conversation": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned conversation: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported conversations action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Conversations: {len(conversations)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _load_channel_source(source: pathlib.Path) -> list[dict[str, Any]]:
    return _load_conversation_source(source)


def _find_channel(channels: list[dict[str, Any]], channel_id: str) -> dict[str, Any] | None:
    return _find_conversation(channels, channel_id)


def render_channel_md(channel: dict[str, Any]) -> str:
    rendered = render_conversation_md(channel)
    return rendered.replace("# Conversation", "# Channel").replace("Conversation", "Channel")


def render_channel_html(channel: dict[str, Any]) -> str:
    rendered = render_conversation_html(channel)
    return rendered.replace("data-conversation-id", "data-channel-id").replace("Conversation ID", "Channel ID").replace("Conversation", "Channel")


def command_channels(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_channels(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("skills", [])
    settings.setdefault("plugins", [])
    settings.setdefault("pipelines", [])
    settings.setdefault("filters", [])
    settings.setdefault("actions", [])
    settings.setdefault("automations", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    channels = settings.setdefault("channels", [])
    if not isinstance(channels, list):
        die("channels must be an array")

    if args.action in (None, "list"):
        print("Channels:")
        print("-" * 80)
        if not channels:
            print("(none)")
            return 0
        fmt = "{:<18} {:<24} {:<14} {:<12}"
        print(fmt.format("ID", "TITLE", "FOLDER", "STATE"))
        print("-" * 80)
        for item in channels:
            state = "pinned" if item.get("pinned") else "active"
            if item.get("archived"):
                state = "archived"
            print(
                fmt.format(
                    str(item.get("id", "")),
                    str(item.get("title", ""))[:24],
                    str(item.get("folderId", ""))[:14],
                    state,
                )
            )
        return 0

    if args.action == "add":
        channel_id = args.id or slugify(args.title)
        new_channel: dict[str, Any] = {
            "id": channel_id,
            "title": args.title,
        }
        if args.folder:
            new_channel["folderId"] = args.folder
        if args.system_prompt:
            new_channel["systemPrompt"] = args.system_prompt
        if args.knowledge:
            new_channel["knowledge"] = [item for item in args.knowledge if item]
        if args.file:
            new_channel["files"] = [item for item in args.file if item]
        if args.image:
            new_channel["images"] = [item for item in args.image if item]
        if args.transcript:
            new_channel["transcript"] = args.transcript
        if args.message:
            messages: list[dict[str, str]] = []
            for item in args.message:
                role, sep, content = item.partition(":")
                if not sep:
                    continue
                role = role.strip()
                content = content.strip()
                if role and content:
                    messages.append({"role": role, "content": content})
            if messages:
                new_channel["messages"] = messages
                if "transcript" not in new_channel:
                    new_channel["transcript"] = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        if args.tag:
            new_channel["tags"] = [tag for tag in args.tag if tag]
        if args.pinned is not None:
            new_channel["pinned"] = args.pinned
        if args.archived is not None:
            new_channel["archived"] = args.archived
        channels[:] = [c for c in channels if str(c.get("id")) != channel_id]
        channels.append(new_channel)
        channels.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(channels)
        channels[:] = [c for c in channels if str(c.get("id")) != args.id]
        if len(channels) == before:
            die(f"channel '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_channel_source(source)
        if not imported:
            die(f"no channels found in {source}")
        existing = {str(c.get("id")): c for c in channels if isinstance(c, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("title") or "channel"))
            if not isinstance(item.get("title"), str) or not str(item.get("title")).strip():
                item["title"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        channels[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"channels": channels}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported channels: {output}")
        return 0
    elif args.action == "share":
        channel = _find_channel(channels, args.id)
        if channel is None:
            die(f"channel '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(channel, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_channel_html(channel)
        else:
            rendered = render_channel_md(channel)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared channel: {output}")
        return 0
    elif args.action == "clone":
        clone = _clone_registry_item(
            channels,
            args.id,
            new_id=args.new_id,
            new_title=args.title,
        )
        channels.append(clone)
        channels.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"channel": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned channel: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported channels action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Channels: {len(channels)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _load_webhook_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        hooks: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() == ".json":
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    payload = payload.get("webhooks", payload.get("items", []))
                if isinstance(payload, list):
                    hooks.extend(item for item in payload if isinstance(item, dict))
        return hooks
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("webhooks", payload.get("items", []))
        if not isinstance(payload, list):
            die("webhook JSON must be an array or an object with webhooks")
        return [item for item in payload if isinstance(item, dict)]
    die("webhook import expects a JSON file or directory")


def _find_webhook(webhooks: list[dict[str, Any]], webhook_id: str) -> dict[str, Any] | None:
    for hook in webhooks:
        if str(hook.get("id")) == webhook_id:
            return hook
    return None


def render_webhook_md(hook: dict[str, Any]) -> str:
    title = str(hook.get("name") or hook.get("id") or "Webhook").strip()
    lines = [f"# {title}", ""]
    for key, label in (("id", "ID"), ("url", "URL")):
        value = hook.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"- {label}: {value.strip()}")
    events = hook.get("events")
    if isinstance(events, list) and events:
        event_line = ", ".join(str(event) for event in events if str(event).strip())
        if event_line:
            lines.append(f"- Events: {event_line}")
    for key, label in (("description", "Description"), ("secret", "Secret")):
        value = hook.get(key)
        if isinstance(value, str) and value.strip():
            lines.extend(["", f"## {label}", value.strip()])
    return "\n".join(lines).strip() + "\n"


def render_webhook_html(hook: dict[str, Any]) -> str:
    title = html_escape(str(hook.get("name") or hook.get("id") or "Webhook"))
    hook_id = html_escape(str(hook.get("id") or "webhook"))
    meta_parts: list[str] = []
    url = hook.get("url")
    if isinstance(url, str) and url.strip():
        meta_parts.append(f"<p class=\"meta\">URL: {html_escape(url.strip())}</p>")
    events = hook.get("events")
    if isinstance(events, list):
        event_line = ", ".join(html_escape(str(event)) for event in events if str(event).strip())
        if event_line:
            meta_parts.append(f"<p class=\"tags\">Events: {event_line}</p>")
    tags = hook.get("tags")
    if isinstance(tags, list):
        tag_line = ", ".join(html_escape(str(tag)) for tag in tags if str(tag).strip())
        if tag_line:
            meta_parts.append(f"<p class=\"tags\">Tags: {tag_line}</p>")
    for key, label in (("description", "Description"), ("secret", "Secret")):
        value = hook.get(key)
        if isinstance(value, str) and value.strip():
            meta_parts.append(f"<pre class=\"{label.lower()}\">{html_escape(value.strip())}</pre>")
    enabled = hook.get("enabled")
    if enabled is not None:
        meta_parts.append(f"<p class=\"meta\">Enabled: {html_escape(str(bool(enabled)))}</p>")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-webhook-id=\"{hook_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Webhook ID: {hook_id}</p>
    {''.join(meta_parts)}
  </article>
</body>
</html>
"""


def normalize_webhooks(settings: dict[str, Any]) -> list[dict[str, Any]]:
    webhooks = settings.get("webhooks")
    if webhooks is None:
        settings["webhooks"] = []
        return []
    if isinstance(webhooks, list):
        normalized: list[dict[str, Any]] = []
        for item in webhooks:
            if not isinstance(item, dict):
                continue
            hook_id = item.get("id")
            name = item.get("name")
            url = item.get("url")
            if not isinstance(hook_id, str) or not hook_id.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                name = hook_id.strip()
            if not isinstance(url, str) or not url.strip():
                continue
            normalized_item: dict[str, Any] = {
                "id": hook_id.strip(),
                "name": str(name).strip(),
                "url": url.strip(),
            }
            events = item.get("events")
            if isinstance(events, list):
                cleaned = [str(event).strip() for event in events if str(event).strip()]
                if cleaned:
                    normalized_item["events"] = cleaned
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                normalized_item["description"] = str(item["description"]).strip()
            if isinstance(item.get("secret"), str) and str(item.get("secret")).strip():
                normalized_item["secret"] = str(item["secret"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    normalized_item["tags"] = tags
            if item.get("enabled") is not None:
                normalized_item["enabled"] = bool(item["enabled"])
            normalized.append(normalized_item)
        settings["webhooks"] = normalized
        return normalized
    if isinstance(webhooks, dict):
        normalized = []
        for key, value in webhooks.items():
            if isinstance(value, str):
                normalized.append({"id": str(key).strip(), "name": str(key).strip(), "url": value})
                continue
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(key).strip())
                item.setdefault("name", str(key).strip())
                if isinstance(item.get("url"), str) and item["url"].strip():
                    normalized.append(item)
        settings["webhooks"] = normalized
        return normalized
    settings["webhooks"] = []
    return []


def command_webhooks(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_webhooks(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("files", [])
    settings.setdefault("memories", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    webhooks = settings.setdefault("webhooks", [])
    if not isinstance(webhooks, list):
        die("webhooks must be an array")

    if args.action in (None, "list"):
        print("Webhooks:")
        print("-" * 80)
        if not webhooks:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<20}"
        print(fmt.format("ID", "NAME", "STATUS"))
        print("-" * 80)
        for item in webhooks:
            status = "enabled" if item.get("enabled", True) else "disabled"
            print(fmt.format(str(item.get("id", "")), str(item.get("name", ""))[:28], status))
        return 0

    if args.action == "add":
        hook_id = args.id or slugify(args.name)
        new_hook: dict[str, Any] = {
            "id": hook_id,
            "name": args.name,
            "url": args.url,
        }
        if args.event:
            new_hook["events"] = [event for event in args.event if event]
        if args.description:
            new_hook["description"] = args.description
        if args.secret:
            new_hook["secret"] = args.secret
        if args.tag:
            new_hook["tags"] = [tag for tag in args.tag if tag]
        if args.enabled is not None:
            new_hook["enabled"] = args.enabled
        webhooks[:] = [hook for hook in webhooks if str(hook.get("id")) != hook_id]
        webhooks.append(new_hook)
        webhooks.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(webhooks)
        webhooks[:] = [hook for hook in webhooks if str(hook.get("id")) != args.id]
        if len(webhooks) == before:
            die(f"webhook '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_webhook_source(source)
        if not imported:
            die(f"no webhooks found in {source}")
        existing = {str(h.get("id")): h for h in webhooks if isinstance(h, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "webhook"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        webhooks[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"webhooks": webhooks}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported webhooks: {output}")
        return 0
    elif args.action == "share":
        hook = _find_webhook(webhooks, args.id)
        if hook is None:
            die(f"webhook '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(hook, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_webhook_html(hook)
        else:
            rendered = render_webhook_md(hook)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared webhook: {output}")
        return 0
    elif args.action == "clone":
        hook = _find_webhook(webhooks, args.id)
        if hook is None:
            die(f"webhook '{args.id}' not found")
        clone = dict(hook)
        clone_id = args.new_id or slugify(f"{str(hook.get('id') or args.id)}-copy")
        if any(str(entry.get("id")) == clone_id for entry in webhooks):
            die(f"webhook '{clone_id}' already exists")
        clone["id"] = clone_id
        clone["name"] = args.name or clone.get("name", clone_id)
        if args.url is not None:
            clone["url"] = args.url
        if args.event is not None:
            clone["events"] = [event for event in args.event if event]
        if args.description is not None:
            clone["description"] = args.description
        if args.secret is not None:
            clone["secret"] = args.secret
        if args.tag is not None:
            clone["tags"] = [tag for tag in args.tag if tag]
        if args.enabled is not None:
            clone["enabled"] = args.enabled
        webhooks.append(clone)
        webhooks.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"webhook": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned webhook: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported webhooks action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Webhooks: {len(webhooks)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _load_file_source(source: pathlib.Path) -> list[dict[str, Any]]:
    def _read_text(path: pathlib.Path) -> str | None:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return None
        return text if text else None

    if source.is_dir():
        files: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            text = _read_text(path)
            if text is None:
                continue
            suffix = path.suffix.lower().lstrip(".")
            files.append(
                {
                    "id": slugify(path.stem),
                    "name": path.stem,
                    "content": text,
                    "path": str(path),
                    "kind": suffix or "text",
                    "size": path.stat().st_size,
                }
            )
        return files
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("files", payload.get("items", []))
        if not isinstance(payload, list):
            die("file JSON must be an array or an object with files")
        files: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            file_id = str(item.get("id", "")).strip()
            name = str(item.get("name", item.get("title", ""))).strip()
            content = str(item.get("content", "")).strip()
            if not file_id or not name or not content:
                continue
            file_item: dict[str, Any] = {
                "id": file_id,
                "name": name,
                "content": content,
            }
            if isinstance(item.get("path"), str) and str(item.get("path")).strip():
                file_item["path"] = str(item["path"]).strip()
            if isinstance(item.get("kind"), str) and str(item.get("kind")).strip():
                file_item["kind"] = str(item["kind"]).strip()
            if isinstance(item.get("description"), str) and str(item.get("description")).strip():
                file_item["description"] = str(item["description"]).strip()
            if isinstance(item.get("tags"), list):
                tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
                if tags:
                    file_item["tags"] = tags
            if item.get("size") is not None:
                try:
                    file_item["size"] = int(item["size"])
                except (TypeError, ValueError):
                    pass
            files.append(file_item)
        return files
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [
        {
            "id": slugify(source.stem),
            "name": source.stem,
            "content": text,
            "path": str(source),
            "kind": source.suffix.lower().lstrip(".") or "text",
            "size": source.stat().st_size,
        }
    ]


def _normalize_file_source_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("files", payload.get("items", []))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _find_file(files: list[dict[str, Any]], file_id: str) -> dict[str, Any] | None:
    for file_item in files:
        if str(file_item.get("id")) == file_id:
            return file_item
    return None


def _render_file_md(file_item: dict[str, Any]) -> str:
    title = str(file_item.get("name") or file_item.get("id") or "File").strip()
    parts = [f"# {title}"]
    meta: list[str] = []
    for key, label in (("id", "ID"), ("kind", "Kind"), ("path", "Path")):
        value = file_item.get(key)
        if isinstance(value, str) and value.strip():
            meta.append(f"- {label}: {value.strip()}")
    size = file_item.get("size")
    if isinstance(size, int):
        meta.append(f"- Size: {size}")
    if meta:
        parts.append("")
        parts.extend(meta)
    description = file_item.get("description")
    if isinstance(description, str) and description.strip():
        parts.extend(["", "## Description", description.strip()])
    content = file_item.get("content")
    if isinstance(content, str) and content.strip():
        parts.extend(["", "## Content", content.strip()])
    tags = file_item.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            parts.extend(["", f"Tags: {tag_line}"])
    return "\n".join(parts).strip() + "\n"


def _render_file_html(file_item: dict[str, Any]) -> str:
    title = html_escape(str(file_item.get("name") or file_item.get("id") or "File"))
    file_id = html_escape(str(file_item.get("id") or "file"))
    body = html_escape(str(file_item.get("content") or ""))
    meta_html = ""
    meta_parts: list[str] = []
    for key, label in (("kind", "Kind"), ("path", "Path")):
        value = file_item.get(key)
        if isinstance(value, str) and value.strip():
            meta_parts.append(f"<p class=\"meta\">{label}: {html_escape(value.strip())}</p>")
    size = file_item.get("size")
    if isinstance(size, int):
        meta_parts.append(f"<p class=\"meta\">Size: {size}</p>")
    if meta_parts:
        meta_html = "\n    ".join(meta_parts)
    description = file_item.get("description")
    description_html = ""
    if isinstance(description, str) and description.strip():
        description_html = f"<pre class=\"description\">{html_escape(description.strip())}</pre>"
    tags = file_item.get("tags")
    tag_html = ""
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            tag_html = "<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>"
    body_html = f"<pre class=\"file-body\">{body}</pre>" if body else "<pre class=\"file-body\"></pre>"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
    .description {{ white-space: pre-wrap; word-wrap: break-word; background: #111827; padding: 1rem; border-radius: 12px; border: 1px solid #374151; }}
  </style>
</head>
<body>
  <article class=\"card\" data-file-id=\"{file_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">File ID: {file_id}</p>
    {meta_html}
    {tag_html}
    {description_html}
    {body_html}
  </article>
</body>
</html>
"""


def _find_artifact(artifacts: list[dict[str, Any]], artifact_id: str) -> dict[str, Any] | None:
    for artifact in artifacts:
        if str(artifact.get("id")) == artifact_id:
            return artifact
    return None


def _render_artifact_md(artifact: dict[str, Any]) -> str:
    title = str(artifact.get("title") or artifact.get("id") or "Artifact").strip()
    parts = [f"# {title}"]
    meta: list[str] = []
    for key, label in (("id", "ID"), ("kind", "Kind")):
        value = artifact.get(key)
        if isinstance(value, str) and value.strip():
            meta.append(f"- {label}: {value.strip()}")
    if meta:
        parts.append("")
        parts.extend(meta)
    tags = artifact.get("tags")
    if isinstance(tags, list) and tags:
        tag_line = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if tag_line:
            parts.extend(["", f"Tags: {tag_line}"])
    content = artifact.get("content")
    if isinstance(content, str) and content.strip():
        parts.extend(["", content.strip()])
    return "\n".join(parts).strip() + "\n"


def _render_artifact_html(artifact: dict[str, Any]) -> str:
    title = html_escape(str(artifact.get("title") or artifact.get("id") or "Artifact"))
    artifact_id = html_escape(str(artifact.get("id") or "artifact"))
    body = html_escape(str(artifact.get("content") or ""))
    meta_html = ""
    kind = artifact.get("kind")
    if isinstance(kind, str) and kind.strip():
        meta_html = f"<p class=\"meta\">Kind: {html_escape(kind.strip())}</p>"
    tags = artifact.get("tags")
    tag_html = ""
    if isinstance(tags, list):
        tag_values = [html_escape(str(tag)) for tag in tags if str(tag).strip()]
        if tag_values:
            tag_html = "<p class=\"tags\">Tags: " + ", ".join(tag_values) + "</p>"
    body_html = f"<pre class=\"artifact-body\">{body}</pre>" if body else "<pre class=\"artifact-body\"></pre>"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
  </style>
</head>
<body>
  <article class=\"card\" data-artifact-id=\"{artifact_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Artifact ID: {artifact_id}</p>
    {meta_html}
    {tag_html}
    {body_html}
  </article>
</body>
</html>
"""


def command_files(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_files(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("promptTemplates", [])
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("skills", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    files = settings.setdefault("files", [])
    if not isinstance(files, list):
        die("files must be an array")

    if args.action in (None, "list"):
        print("Files:")
        print("-" * 80)
        if not files:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<18}"
        print(fmt.format("ID", "NAME", "KIND"))
        print("-" * 80)
        for item in files:
            print(fmt.format(str(item.get("id", "")), str(item.get("name", ""))[:28], str(item.get("kind", ""))[:18]))
        return 0

    if args.action == "add":
        file_id = args.id or slugify(args.name)
        new_file: dict[str, Any] = {
            "id": file_id,
            "name": args.name,
            "content": args.content,
        }
        if args.path:
            new_file["path"] = args.path
        if args.kind:
            new_file["kind"] = args.kind
        if args.description:
            new_file["description"] = args.description
        if args.tag:
            new_file["tags"] = [tag for tag in args.tag if tag]
        if args.size is not None:
            new_file["size"] = args.size
        if args.pinned is not None:
            new_file["pinned"] = args.pinned
        if args.archived is not None:
            new_file["archived"] = args.archived
        files[:] = [f for f in files if str(f.get("id")) != file_id]
        files.append(new_file)
        files.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(files)
        files[:] = [f for f in files if str(f.get("id")) != args.id]
        if len(files) == before:
            die(f"file '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_file_source(source)
        if not imported:
            die(f"no files found in {source}")
        existing = {str(f.get("id")): f for f in files if isinstance(f, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "file"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            existing[str(item.get("id"))] = item
        files[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"files": files}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported files: {output}")
        return 0
    elif args.action == "share":
        file_item = _find_file(files, args.id)
        if file_item is None:
            die(f"file '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(file_item, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = _render_file_html(file_item)
        else:
            rendered = _render_file_md(file_item)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared file: {output}")
        return 0
    elif args.action == "clone":
        clone = _clone_registry_item(
            files,
            args.id,
            new_id=args.new_id,
        )
        clone["name"] = args.name or clone.get("name", clone["id"])
        files.append(clone)
        files.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"file": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned file: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported files action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Files: {len(files)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _load_agent_source(source: pathlib.Path) -> list[dict[str, Any]]:
    if source.is_dir():
        agents: list[dict[str, Any]] = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix.lower() == ".json":
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict):
                    payload = payload.get("agents", payload.get("items", []))
                if isinstance(payload, list):
                    agents.extend(item for item in payload if isinstance(item, dict))
        return agents
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("agents", payload.get("items", []))
        if not isinstance(payload, list):
            die("agent JSON must be an array or an object with agents")
        return [item for item in payload if isinstance(item, dict)]
    die("agent import expects a JSON file or directory")


def _normalize_agent_source_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("agents", payload.get("items", []))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _find_agent(agents: list[dict[str, Any]], agent_id: str) -> dict[str, Any] | None:
    for agent in agents:
        if str(agent.get("id")) == agent_id:
            return agent
    return None


def _agent_value_list(agent: dict[str, Any], key: str) -> str:
    value = agent.get(key)
    if isinstance(value, list) and value:
        return ", ".join(str(entry) for entry in value if str(entry).strip())
    return ""


def render_agent_md(agent: dict[str, Any]) -> str:
    title = str(agent.get("name") or agent.get("id") or "Agent").strip()
    agent_id = str(agent.get("id") or "agent").strip()
    base_model = str(agent.get("baseModel") or agent.get("model") or "").strip()
    lines = [f"# {title}", ""]
    lines.append(f"- ID: {agent_id}")
    if base_model:
        lines.append(f"- Base model: {base_model}")
    if isinstance(agent.get("visibility"), str) and str(agent.get("visibility")).strip():
        lines.append(f"- Visibility: {str(agent['visibility']).strip()}")
    if isinstance(agent.get("description"), str) and str(agent.get("description")).strip():
        lines.extend(["", "## Description", str(agent["description"]).strip()])
    system_prompt = agent.get("systemPrompt", agent.get("instructions", agent.get("prompt")))
    if isinstance(system_prompt, str) and system_prompt.strip():
        lines.extend(["", "## System Prompt", system_prompt.strip()])
    for key, heading in (
        ("tools", "Tools"),
        ("knowledge", "Knowledge"),
        ("skills", "Skills"),
        ("tags", "Tags"),
    ):
        items = _agent_value_list(agent, key)
        if items:
            lines.extend(["", f"## {heading}", items])
    parameters = agent.get("parameters")
    if isinstance(parameters, dict) and parameters:
        lines.extend(["", "## Parameters", json.dumps(parameters, indent=2, ensure_ascii=False)])
    avatar = agent.get("avatar")
    if isinstance(avatar, str) and avatar.strip():
        lines.extend(["", "## Avatar", avatar.strip()])
    voice = agent.get("voice")
    if isinstance(voice, str) and voice.strip():
        lines.extend(["", "## Voice", voice.strip()])
    return "\n".join(lines).strip() + "\n"


def render_agent_html(agent: dict[str, Any]) -> str:
    title = html_escape(str(agent.get("name") or agent.get("id") or "Agent"))
    agent_id = html_escape(str(agent.get("id") or "agent"))
    body_parts: list[str] = []
    base_model = agent.get("baseModel") or agent.get("model")
    if isinstance(base_model, str) and base_model.strip():
        body_parts.append(f"<p class=\"meta\">Base model: {html_escape(base_model.strip())}</p>")
    visibility = agent.get("visibility")
    if isinstance(visibility, str) and visibility.strip():
        body_parts.append(f"<p class=\"meta\">Visibility: {html_escape(visibility.strip())}</p>")
    description = agent.get("description")
    if isinstance(description, str) and description.strip():
        body_parts.append(f"<pre class=\"description\">{html_escape(description.strip())}</pre>")
    system_prompt = agent.get("systemPrompt", agent.get("instructions", agent.get("prompt")))
    if isinstance(system_prompt, str) and system_prompt.strip():
        body_parts.append(f"<pre class=\"system-prompt\">{html_escape(system_prompt.strip())}</pre>")
    for key, label in (("tools", "Tools"), ("knowledge", "Knowledge"), ("skills", "Skills"), ("tags", "Tags")):
        items = _agent_value_list(agent, key)
        if items:
            body_parts.append(f"<p class=\"tags\">{label}: {html_escape(items)}</p>")
    parameters = agent.get("parameters")
    if isinstance(parameters, dict) and parameters:
        body_parts.append(f"<pre class=\"parameters\">{html_escape(json.dumps(parameters, indent=2, ensure_ascii=False))}</pre>")
    avatar = agent.get("avatar")
    if isinstance(avatar, str) and avatar.strip():
        body_parts.append(f"<p class=\"meta\">Avatar: {html_escape(avatar.strip())}</p>")
    voice = agent.get("voice")
    if isinstance(voice, str) and voice.strip():
        body_parts.append(f"<p class=\"meta\">Voice: {html_escape(voice.strip())}</p>")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; background: #0f1115; color: #f5f7fa; }}
    .card {{ max-width: 900px; margin: 0 auto; padding: 2rem; background: #171a21; border: 1px solid #2a2f3a; border-radius: 16px; }}
    h1 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f1115; padding: 1rem; border-radius: 12px; border: 1px solid #2a2f3a; }}
    .meta {{ color: #b8c0cc; font-size: 0.95rem; }}
    .tags {{ color: #c7d2fe; }}
    .description {{ white-space: pre-wrap; word-wrap: break-word; background: #111827; padding: 1rem; border-radius: 12px; border: 1px solid #374151; }}
    .system-prompt {{ white-space: pre-wrap; word-wrap: break-word; background: #111827; padding: 1rem; border-radius: 12px; border: 1px solid #374151; }}
    .parameters {{ white-space: pre-wrap; word-wrap: break-word; background: #0b1220; padding: 1rem; border-radius: 12px; border: 1px solid #1f2937; }}
  </style>
</head>
<body>
  <article class=\"card\" data-agent-id=\"{agent_id}\">
    <h1>{title}</h1>
    <p class=\"meta\">Agent ID: {agent_id}</p>
    {''.join(body_parts)}
  </article>
</body>
</html>
"""


def command_agents(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_agents(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeBases", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})

    agents = settings.setdefault("agents", [])
    if not isinstance(agents, list):
        die("agents must be an array")

    if args.action in (None, "list"):
        print("Agents:")
        print("-" * 80)
        if not agents:
            print("(none)")
            return 0
        fmt = "{:<18} {:<28} {:<24} {:<10}"
        print(fmt.format("ID", "NAME", "BASE MODEL", "STATE"))
        print("-" * 80)
        for item in agents:
            state = "pinned" if item.get("pinned") else "active"
            if item.get("archived"):
                state = "archived"
            print(
                fmt.format(
                    str(item.get("id", "")),
                    str(item.get("name", ""))[:28],
                    str(item.get("baseModel", item.get("model", "")))[:24],
                    state,
                )
            )
        return 0

    if args.action == "add":
        agent_id = args.id or slugify(args.name)
        new_agent: dict[str, Any] = {
            "id": agent_id,
            "name": args.name,
            "baseModel": args.base_model,
        }
        if args.system_prompt:
            new_agent["systemPrompt"] = args.system_prompt
        if args.description:
            new_agent["description"] = args.description
        if args.avatar:
            new_agent["avatar"] = args.avatar
        if args.voice:
            new_agent["voice"] = args.voice
        if args.visibility:
            new_agent["visibility"] = args.visibility
        if args.tag:
            new_agent["tags"] = [tag for tag in args.tag if tag]
        if args.tool:
            new_agent["tools"] = [tool for tool in args.tool if tool]
        if args.knowledge:
            new_agent["knowledge"] = [kb for kb in args.knowledge if kb]
        if args.skill:
            new_agent["skills"] = [skill for skill in args.skill if skill]
        if args.param:
            params: dict[str, Any] = {}
            for item in args.param:
                key, sep, value = item.partition("=")
                if not sep:
                    continue
                key = key.strip()
                value = value.strip()
                if key and value:
                    params[key] = value
            if params:
                new_agent["parameters"] = params
        if args.pinned is not None:
            new_agent["pinned"] = args.pinned
        if args.archived is not None:
            new_agent["archived"] = args.archived
        agents[:] = [a for a in agents if str(a.get("id")) != agent_id]
        agents.append(new_agent)
        agents.sort(key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "remove":
        before = len(agents)
        agents[:] = [a for a in agents if str(a.get("id")) != args.id]
        if len(agents) == before:
            die(f"agent '{args.id}' not found")
    elif args.action == "import":
        source = pathlib.Path(args.source).expanduser()
        imported = _load_agent_source(source)
        if not imported:
            die(f"no agents found in {source}")
        existing = {str(a.get("id")): a for a in agents if isinstance(a, dict)}
        for item in imported:
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("id"), str) or not str(item.get("id")).strip():
                item = dict(item)
                item["id"] = slugify(str(item.get("name") or "agent"))
            if not isinstance(item.get("name"), str) or not str(item.get("name")).strip():
                item["name"] = str(item.get("id"))
            if not isinstance(item.get("baseModel"), str) or not str(item.get("baseModel")).strip():
                if isinstance(item.get("model"), str) and str(item.get("model")).strip():
                    item["baseModel"] = str(item.get("model")).strip()
            existing[str(item.get("id"))] = item
        agents[:] = sorted(existing.values(), key=lambda x: str(x.get("id", "")).lower())
    elif args.action == "export":
        output = pathlib.Path(args.output).expanduser()
        payload = {"agents": agents}
        if args.dry_run:
            json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported agents: {output}")
        return 0
    elif args.action == "share":
        agent = _find_agent(agents, args.id)
        if agent is None:
            die(f"agent '{args.id}' not found")
        output = pathlib.Path(args.output).expanduser()
        if args.format == "json":
            rendered = json.dumps(agent, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            rendered = render_agent_html(agent)
        else:
            rendered = render_agent_md(agent)
        if args.dry_run:
            sys.stdout.write(rendered)
            return 0
        output.write_text(rendered, encoding="utf-8")
        print(f"Shared agent: {output}")
        return 0
    elif args.action == "clone":
        clone = _clone_registry_item(
            agents,
            args.id,
            new_id=args.new_id,
            new_title=args.name,
        )
        clone["name"] = args.name or clone.get("name", clone["id"])
        agents.append(clone)
        agents.sort(key=lambda x: str(x.get("id", "")).lower())
        if args.dry_run:
            json.dump({"agent": clone}, sys.stdout, indent=2, ensure_ascii=False)
            print()
            return 0
        saved_backup = backup(path)
        atomic_write_json(path, settings)
        print(f"Cloned agent: {clone['id']}")
        if saved_backup:
            print(f"Backup: {saved_backup}")
        return 0
    else:
        die(f"unsupported agents action: {args.action}")

    errors = validate_settings(settings)
    if errors:
        die("generated configuration failed validation:\n- " + "\n- ".join(errors))

    if args.dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Agents: {len(agents)}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def _searchable_fields(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "id",
        "name",
        "title",
        "description",
        "body",
        "content",
        "transcript",
        "scope",
        "sourceDir",
        "path",
        "kind",
        "type",
        "endpoint",
        "url",
        "folderId",
        "parentId",
        "baseModel",
        "model",
        "systemPrompt",
        "instructions",
        "prompt",
        "avatar",
        "voice",
        "visibility",
    ):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    for key in ("tags", "sources", "tools", "knowledge", "skills", "events", "files", "images"):
        value = item.get(key)
        if isinstance(value, list):
            parts.extend(str(x) for x in value if str(x).strip())
    messages = item.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                for key in ("role", "content"):
                    value = msg.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value)
    images = item.get("images")
    if isinstance(images, list):
        parts.extend(str(x) for x in images if str(x).strip())
    params = item.get("parameters")
    if isinstance(params, dict):
        for value in params.values():
            if isinstance(value, str) and value.strip():
                parts.append(value)
    return "\n".join(parts).lower()


def command_search(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    term = args.query.strip().lower()
    if not term:
        die("search query must be non-empty")

    scopes = {
        "promptTemplates": settings.get("promptTemplates", []),
        "skills": settings.get("skills", []),
        "plugins": settings.get("plugins", []),
        "pipelines": settings.get("pipelines", []),
        "filters": settings.get("filters", []),
        "actions": settings.get("actions", []),
        "automations": settings.get("automations", []),
        "channels": settings.get("channels", []),
        "files": settings.get("files", []),
        "agents": settings.get("agents", []),
        "conversations": settings.get("conversations", []),
        "folders": settings.get("folders", []),
        "toolServers": settings.get("toolServers", []),
        "knowledgeBases": settings.get("knowledgeBases", []),
        "knowledgeIndexes": settings.get("knowledgeIndexes", []),
        "notes": settings.get("notes", []),
        "memories": settings.get("memories", []),
        "artifacts": settings.get("artifacts", []),
        "webhooks": settings.get("webhooks", []),
        "modelProviders": settings.get("modelProviders", {}),
    }

    matches: list[tuple[str, dict[str, Any]]] = []
    for scope_name, payload in scopes.items():
        if scope_name == "modelProviders":
            if isinstance(payload, dict):
                for proto, models in payload.items():
                    if isinstance(models, list):
                        for model in models:
                            if isinstance(model, dict) and term in _searchable_fields(model):
                                matches.append((f"{scope_name}.{proto}", model))
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and term in _searchable_fields(item):
                    matches.append((scope_name, item))

    if args.kind:
        matches = [m for m in matches if m[0] == args.kind or m[0].startswith(f"{args.kind}.")]

    if not matches:
        print("No matches found.")
        return 0

    print("Search Results:")
    print("-" * 80)
    fmt = "{:<20} {:<24} {:<28}"
    print(fmt.format("SCOPE", "ID", "NAME/TITLE"))
    print("-" * 80)
    for scope, item in matches:
        label = str(item.get("name") or item.get("title") or item.get("id") or "")
        print(fmt.format(scope[:20], str(item.get("id", ""))[:24], label[:28]))
    return 0


def command_web_search(args: argparse.Namespace) -> int:
    if args.list_providers:
        print("Web Search Providers:")
        print("-" * 100)
        fmt = "{:<18} {:<22} {:<40} {:<16}"
        print(fmt.format("KEY", "NAME", "ENGINE URL", "ENV KEY"))
        print("-" * 100)
        for key, info in sorted(WEB_SEARCH_PROVIDERS.items()):
            print(
                fmt.format(
                    key[:18],
                    info["name"][:22],
                    info.get("engine_url", "")[:40],
                    info.get("env_key", "")[:16],
                )
            )
        return 0

    if not args.query:
        die("web-search query must be non-empty")

    providers = [args.provider] if args.provider else []
    providers.extend(args.fallback_provider or [])
    results = fetch_web_search_results_chain(
        args.query,
        providers,
        engine_url=args.engine_url,
        api_key=args.api_key or "",
        timeout=args.timeout,
        limit=args.limit,
    )
    if not results:
        print("No matches found.")
        return 0

    print("Web Search Results:")
    print("-" * 100)
    fmt = "{:<4} {:<28} {:<52}"
    print(fmt.format("#", "TITLE", "URL"))
    print("-" * 100)
    for idx, item in enumerate(results, start=1):
        print(fmt.format(str(idx), str(item.get("title", ""))[:28], str(item.get("url", ""))[:52]))

    if not args.save_to_knowledge:
        return 0

    if not args.output:
        die("an output path is required when --save-to-knowledge is set")

    path = pathlib.Path(args.settings).expanduser()
    settings = load_json(path)
    repairs = normalize_knowledge_bases(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings.setdefault("modelProviders", {})
    settings.setdefault("toolServers", [])
    settings.setdefault("knowledgeIndexes", [])
    settings.setdefault("promptTemplates", [])
    settings.setdefault("notes", [])
    settings.setdefault("artifacts", [])
    settings.setdefault("conversations", [])
    settings.setdefault("agents", [])
    settings.setdefault("skills", [])
    settings.setdefault("files", [])
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"].setdefault("approvalMode", "default")
    settings["security"].setdefault("auth", {})
    save_payload = _save_web_search_results_to_settings(
        settings,
        args.query,
        results,
        base_id=args.base_id,
        knowledge_name=args.knowledge_name,
        description=args.description,
        save_limit=args.save_limit,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        timeout=args.timeout,
    )

    if args.dry_run:
        json.dump(save_payload, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    output = pathlib.Path(args.output).expanduser()
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(save_payload["knowledgeIndex"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported knowledge index: {output}")
    else:
        output.mkdir(parents=True, exist_ok=True)
        for doc in save_payload["knowledgeIndex"]["documents"]:
            doc_path = output / f"{doc['id']}.json"
            doc_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest = output / "manifest.json"
        manifest.write_text(json.dumps(save_payload["knowledgeIndex"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Exported knowledge index: {manifest}")
    saved_backup = backup(path)
    atomic_write_json(path, settings)
    print(f"Updated Qwen settings: {path}")
    print(f"Knowledge index documents: {save_payload['knowledgeIndex']['documentCount']}")
    print(f"Knowledge index chunks: {save_payload['knowledgeIndex']['chunkCount']}")
    if repairs:
        for repair in repairs:
            print(f"Repaired: {repair}")
    if saved_backup:
        print(f"Backup: {saved_backup}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.settings).expanduser()
    print(f"Qwen Omega ProMeta {VERSION}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Settings: {path} ({'present' if path.exists() else 'missing'})")
    qwen = shutil.which("qwen")
    node = shutil.which("node")
    npm = shutil.which("npm")
    print(f"qwen: {qwen or 'not installed'}")
    print(f"node: {node or 'not installed'}")
    print(f"npm: {npm or 'not installed'}")
    if node:
        try:
            print(
                "node version:",
                subprocess.check_output([node, "--version"], text=True).strip(),
            )
        except subprocess.SubprocessError:
            pass
    if path.exists():
        return command_validate(args)
    return 1


def _detect_ram_gb() -> int:
    """Return total system RAM in GB, or 0 if unavailable."""
    try:
        mem = pathlib.Path("/proc/meminfo")
        if mem.exists():
            for line in mem.read_text().splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb // (1024 * 1024)
    except Exception:
        pass
    return 0


def command_install_coder(args: argparse.Namespace) -> int:
    """High-level Qwen Coder install: choose backend, model, generate settings."""

    backend: str = args.backend
    model: str = args.model or ""
    approval_mode: str = args.approval_mode
    dry_run: bool = args.dry_run
    free_only: bool = args.free

    # ── Auto-detect backend ────────────────────────────────────────────────
    if backend == "auto":
        if shutil.which("ollama"):
            backend = "ollama"
        elif os.environ.get("DASHSCOPE_API_KEY"):
            backend = "dashscope"
        elif os.environ.get("OPENROUTER_API_KEY"):
            backend = "openrouter"
        elif os.environ.get("SILICONFLOW_API_KEY"):
            backend = "siliconflow"
        elif os.environ.get("LITELLM_API_KEY"):
            backend = "litellm"
        elif os.environ.get("LMSTUDIO_API_KEY"):
            backend = "lmstudio"
        elif os.environ.get("NEXTCHAT_API_KEY"):
            backend = "nextchat"
        elif os.environ.get("NEXTCHAT_BASE_URL"):
            backend = "nextchat"
        elif os.environ.get("OPEN_WEBUI_API_KEY"):
            backend = "open_webui"
        elif os.environ.get("OPEN_WEBUI_BASE_URL"):
            backend = "open_webui"
        else:
            die(
                "Cannot auto-detect backend. "
                "Set DASHSCOPE_API_KEY / OPENROUTER_API_KEY / SILICONFLOW_API_KEY / LITELLM_API_KEY / LMSTUDIO_API_KEY / NEXTCHAT_API_KEY / OPEN_WEBUI_API_KEY, "
                "or set NEXTCHAT_BASE_URL / OPEN_WEBUI_BASE_URL, or install Ollama, or pass --backend explicitly."
            )

    print(f"Qwen Omega ProMeta {VERSION} — Qwen Coder Installer")
    print(f"Backend : {backend}")

    # ── Select model ───────────────────────────────────────────────────────
    catalog = CODER_CATALOG.get(backend, [])
    if not model:
        if backend == "ollama":
            ram_gb = _detect_ram_gb()
            if ram_gb >= 40:
                model = catalog[0]  # 32b
            elif ram_gb >= 20:
                model = catalog[1]  # 14b
            elif ram_gb >= 10:
                model = catalog[2]  # 7b
            elif ram_gb >= 5:
                model = catalog[3]  # 3b
            else:
                model = catalog[4]  # 1.5b
            print(f"RAM     : {ram_gb}GB → {model}")
        elif catalog:
            model = catalog[0]
        else:
            die(f"No default model catalog for backend '{backend}'. Pass --model.")

    print(f"Model   : {model}")

    # ── Validate API key availability ──────────────────────────────────────
    key_map = {
        "dashscope": "DASHSCOPE_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
    }
    if backend in key_map and not os.environ.get(key_map[backend]):
        die(f"{key_map[backend]} is not set")

    # ── Build generate args namespace ──────────────────────────────────────
    provider_map = {
        "ollama": "ollama",
        "litellm": "litellm",
        "lmstudio": "lmstudio",
        "nextchat": "nextchat",
        "open_webui": "open_webui",
        "dashscope": "dashscope",
        "openrouter": "openrouter",
        "siliconflow": "siliconflow",
    }
    provider = provider_map.get(backend)
    if provider is None:
        die(f"Unsupported backend: {backend}")

    preset = PRESETS[provider]
    base_url = normalize_url(os.environ.get(BASE_URL_HINT_ENV.get(provider, ""), preset.base_url))
    env_key = preset.env_key
    api_key = os.environ.get(env_key, "")

    # For Ollama, skip live discovery — use catalog directly
    if backend == "ollama":
        model_items: list[dict[str, Any]] = [
            {"id": m} for m in (catalog if not model else [model])
        ]
        # Always include selected model first
        if model not in [m["id"] for m in model_items]:
            model_items.insert(0, {"id": model})
    elif backend in (
        "dashscope",
        "siliconflow",
        "litellm",
        "lmstudio",
        "nextchat",
        "open_webui",
    ):
        # Use catalog; avoid live API call
        model_items = [{"id": m} for m in catalog]
    else:
        # openrouter: discover live, then filter to coder + optional :free
        if not api_key:
            # Fall back to known-free catalog
            model_items = [{"id": m} for m in catalog]
        else:
            payload = request_json(
                models_url(base_url),
                api_key,
                DEFAULT_TIMEOUT,
                insecure=False,
            )
            model_items = extract_model_objects(payload)
            coder_pat = re.compile(r"code|coder", re.IGNORECASE)
            model_items = [
                it for it in model_items if coder_pat.search(str(it.get("id", "")))
            ]
            if free_only:
                model_items = [it for it in model_items if explicitly_free(it)] or [
                    {"id": m} for m in catalog
                ]

    if not model_items:
        die("No models available after filtering")

    settings_path = pathlib.Path(args.settings).expanduser()
    configs = to_model_configs(
        model_items,
        base_url,
        env_key,
        120_000,
        3,
        None,
    )
    default_model = choose_default_model(configs, model)

    settings = load_json(settings_path)
    repairs = normalize_existing_providers(settings)
    settings["$version"] = 4
    settings.setdefault("general", {})
    settings.setdefault("ui", {})
    settings.setdefault("privacy", {})
    settings.setdefault("tools", {})
    settings.setdefault("security", {})
    settings.setdefault("model", {})
    settings["general"].setdefault("enableAutoUpdate", True)
    settings["ui"].setdefault("showMemoryUsage", True)
    settings["privacy"].setdefault("usageStatisticsEnabled", False)
    settings["tools"]["approvalMode"] = approval_mode
    settings["security"].setdefault("auth", {})
    settings["security"]["auth"]["selectedType"] = preset.protocol
    apply_root_admin_emails(settings)
    settings["model"]["name"] = default_model
    settings["model"]["maxSessionTurns"] = -1
    settings["modelProviders"][preset.protocol] = configs

    errors = validate_settings(settings)
    if errors:
        die("Generated configuration failed validation:\n- " + "\n- ".join(errors))

    if dry_run:
        json.dump(settings, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    saved_backup = backup(settings_path)
    atomic_write_json(settings_path, settings)

    print(f"Settings : {settings_path}")
    print(f"Models   : {len(configs)}")
    print(f"Default  : {default_model}")
    print(f"Env key  : {env_key}")
    if saved_backup:
        print(f"Backup   : {saved_backup}")
    for repair in repairs:
        print(f"Repaired : {repair}")

    # ── Ollama pull ────────────────────────────────────────────────────────
    if backend == "ollama" and shutil.which("ollama"):
        print(f"Pulling  : {model}")
        try:
            subprocess.run(["ollama", "pull", model], check=True)
            print(f"Ready    : {model}")
        except subprocess.CalledProcessError:
            eprint(
                f"WARNING: ollama pull {model} failed. Run manually: ollama pull {model}"
            )

    print("Done. Run: qwen")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qwen-omega",
        description="Generate and validate production-grade Qwen Code configuration",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    command_parsers: dict[str, argparse.ArgumentParser] = {}

    gen = sub.add_parser("generate", help="discover models and generate settings.json")
    gen.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    gen.add_argument("--provider", choices=sorted(PRESETS))
    gen.add_argument(
        "--protocol", default=None, help="Qwen provider protocol key; default openai"
    )
    gen.add_argument("--base-url")
    gen.add_argument("--env-key")
    gen.add_argument("--api-key", help="used only for discovery; never persisted")
    gen.add_argument("--models", help="comma-separated model IDs; skips API discovery")
    gen.add_argument("--default-model")
    gen.add_argument(
        "--free",
        action="store_true",
        help="include only models explicitly marked zero-cost/free",
    )
    gen.add_argument("--filter-model", help="regex pattern to filter models by ID")
    gen.add_argument("--include-regex", help="alias for --filter-model")
    gen.add_argument("--exclude-regex", help="regex pattern to exclude matching models")
    gen.add_argument(
        "--coder-only", action="store_true", help="filter for code/coder models"
    )
    gen.add_argument(
        "--min-context", type=int, help="minimum context window length requirement"
    )
    gen.add_argument("--limit", type=int)
    gen.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    gen.add_argument("--request-timeout-ms", type=int, default=120000)
    gen.add_argument("--max-retries", type=int, default=3)
    gen.add_argument("--context-window", type=int)
    gen.add_argument("--max-session-turns", type=int, default=-1)
    gen.add_argument(
        "--approval-mode",
        choices=("plan", "default", "auto-edit", "auto", "yolo"),
        default="default",
    )
    gen.add_argument("--allow-unauthenticated", action="store_true")
    gen.add_argument(
        "--insecure",
        action="store_true",
        help="disable TLS verification; local testing only",
    )
    gen.add_argument("--no-backup", action="store_true")
    gen.add_argument("--dry-run", action="store_true")
    gen.set_defaults(func=command_generate)
    command_parsers["generate"] = gen

    val = sub.add_parser("validate", help="validate current settings schema")
    val.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    val.set_defaults(func=command_validate)
    command_parsers["validate"] = val

    repair = sub.add_parser(
        "repair", help="repair string/wrapped legacy modelProviders"
    )
    repair.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    repair.add_argument("--dry-run", action="store_true")
    repair.set_defaults(func=command_repair)
    command_parsers["repair"] = repair

    doctor = sub.add_parser("doctor", help="inspect installation and validate settings")
    doctor.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    doctor.set_defaults(func=command_doctor)
    command_parsers["doctor"] = doctor

    prompts = sub.add_parser(
        "prompts", help="manage reusable prompt templates and libraries"
    )
    prompts_sub = prompts.add_subparsers(dest="prompt_command")

    prompts_list = prompts_sub.add_parser("list", help="list saved prompt templates")
    prompts_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    prompts_list.add_argument("--dry-run", action="store_true")
    prompts_list.set_defaults(func=command_prompts, action="list")

    prompts_add = prompts_sub.add_parser("add", help="add or replace a prompt template")
    prompts_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    prompts_add.add_argument("--dry-run", action="store_true")
    prompts_add.add_argument("--id")
    prompts_add.add_argument("--name", required=True)
    prompts_add.add_argument("--content", required=True)
    prompts_add.add_argument("--description")
    prompts_add.add_argument("--tag", action="append", default=[])
    prompts_add.set_defaults(func=command_prompts, action="add")

    prompts_remove = prompts_sub.add_parser("remove", help="remove a prompt template")
    prompts_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    prompts_remove.add_argument("--dry-run", action="store_true")
    prompts_remove.add_argument("--id", required=True)
    prompts_remove.set_defaults(func=command_prompts, action="remove")

    prompts_import = prompts_sub.add_parser(
        "import", help="import prompt templates from JSON or Markdown files"
    )
    prompts_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    prompts_import.add_argument("--dry-run", action="store_true")
    prompts_import.add_argument("source")
    prompts_import.set_defaults(func=command_prompts, action="import")

    prompts_export = prompts_sub.add_parser(
        "export", help="export prompt templates to a JSON file"
    )
    prompts_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    prompts_export.add_argument("--dry-run", action="store_true")
    prompts_export.add_argument("output")
    prompts_export.set_defaults(func=command_prompts, action="export")

    prompts_clone = prompts_sub.add_parser(
        "clone", help="clone a prompt template into a new entry"
    )
    prompts_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    prompts_clone.add_argument("--dry-run", action="store_true")
    prompts_clone.add_argument("--id", required=True)
    prompts_clone.add_argument("--new-id")
    prompts_clone.add_argument("--name")
    prompts_clone.add_argument("--content")
    prompts_clone.add_argument("--description")
    prompts_clone.add_argument("--tag", action="append", default=None)
    prompts_clone.set_defaults(func=command_prompts, action="clone")

    prompts.set_defaults(func=command_prompts, action="list")
    command_parsers["prompts"] = prompts

    skills_cmd = sub.add_parser(
        "skills", help="manage reusable workspace skills and instructions"
    )
    skills_sub = skills_cmd.add_subparsers(dest="skills_command")

    skills_list = skills_sub.add_parser("list", help="list saved skills")
    skills_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    skills_list.add_argument("--dry-run", action="store_true")
    skills_list.set_defaults(func=command_skills, action="list")

    skills_add = skills_sub.add_parser("add", help="add or replace a skill")
    skills_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    skills_add.add_argument("--dry-run", action="store_true")
    skills_add.add_argument("--id")
    skills_add.add_argument("--name", required=True)
    skills_add.add_argument("--content", required=True)
    skills_add.add_argument("--description")
    skills_add.add_argument("--tag", action="append", default=[])
    skills_add.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    skills_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    skills_add.set_defaults(func=command_skills, action="add")

    skills_remove = skills_sub.add_parser("remove", help="remove a skill")
    skills_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    skills_remove.add_argument("--dry-run", action="store_true")
    skills_remove.add_argument("--id", required=True)
    skills_remove.set_defaults(func=command_skills, action="remove")

    skills_import = skills_sub.add_parser(
        "import", help="import skills from JSON files or Markdown files"
    )
    skills_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    skills_import.add_argument("--dry-run", action="store_true")
    skills_import.add_argument("source")
    skills_import.set_defaults(func=command_skills, action="import")

    skills_export = skills_sub.add_parser("export", help="export skills to a JSON file")
    skills_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    skills_export.add_argument("--dry-run", action="store_true")
    skills_export.add_argument("output")
    skills_export.set_defaults(func=command_skills, action="export")

    skills_share = skills_sub.add_parser(
        "share", help="export a single skill as markdown, html, or json"
    )
    skills_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    skills_share.add_argument("--dry-run", action="store_true")
    skills_share.add_argument("--id", required=True)
    skills_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    skills_share.add_argument("output")
    skills_share.set_defaults(func=command_skills, action="share")

    skills_clone = skills_sub.add_parser("clone", help="clone a skill into a new entry")
    skills_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    skills_clone.add_argument("--dry-run", action="store_true")
    skills_clone.add_argument("--id", required=True)
    skills_clone.add_argument("--new-id")
    skills_clone.add_argument("--name")
    skills_clone.add_argument("--content")
    skills_clone.add_argument("--description")
    skills_clone.add_argument("--tag", action="append", default=None)
    skills_clone.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    skills_clone.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    skills_clone.set_defaults(func=command_skills, action="clone")

    skills_cmd.set_defaults(func=command_skills, action="list")
    command_parsers["skills"] = skills_cmd

    plugins_cmd = sub.add_parser(
        "plugins", help="manage reusable plugin and extension manifests"
    )
    plugins_sub = plugins_cmd.add_subparsers(dest="plugins_command")

    plugins_list = plugins_sub.add_parser("list", help="list saved plugins")
    plugins_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    plugins_list.add_argument("--dry-run", action="store_true")
    plugins_list.set_defaults(func=command_plugins, action="list")

    plugins_add = plugins_sub.add_parser("add", help="add or replace a plugin")
    plugins_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    plugins_add.add_argument("--dry-run", action="store_true")
    plugins_add.add_argument("--id")
    plugins_add.add_argument("--name", required=True)
    plugins_add.add_argument("--content", required=True)
    plugins_add.add_argument("--description")
    plugins_add.add_argument("--url")
    plugins_add.add_argument("--tag", action="append", default=[])
    plugins_add.add_argument("--tool", action="append", default=[])
    plugins_add.add_argument("--knowledge", action="append", default=[])
    plugins_add.add_argument("--skill", action="append", default=[])
    plugins_add.add_argument("--event", action="append", default=[])
    plugins_add.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    plugins_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    plugins_add.set_defaults(func=command_plugins, action="add")

    plugins_remove = plugins_sub.add_parser("remove", help="remove a plugin")
    plugins_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    plugins_remove.add_argument("--dry-run", action="store_true")
    plugins_remove.add_argument("--id", required=True)
    plugins_remove.set_defaults(func=command_plugins, action="remove")

    plugins_import = plugins_sub.add_parser(
        "import", help="import plugins from JSON files or Markdown files"
    )
    plugins_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    plugins_import.add_argument("--dry-run", action="store_true")
    plugins_import.add_argument("source")
    plugins_import.set_defaults(func=command_plugins, action="import")

    plugins_export = plugins_sub.add_parser("export", help="export plugins to a JSON file")
    plugins_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    plugins_export.add_argument("--dry-run", action="store_true")
    plugins_export.add_argument("output")
    plugins_export.set_defaults(func=command_plugins, action="export")

    plugins_share = plugins_sub.add_parser(
        "share", help="export a single plugin as markdown, html, or json"
    )
    plugins_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    plugins_share.add_argument("--dry-run", action="store_true")
    plugins_share.add_argument("--id", required=True)
    plugins_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    plugins_share.add_argument("output")
    plugins_share.set_defaults(func=command_plugins, action="share")

    plugins_clone = plugins_sub.add_parser("clone", help="clone a plugin into a new entry")
    plugins_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    plugins_clone.add_argument("--dry-run", action="store_true")
    plugins_clone.add_argument("--id", required=True)
    plugins_clone.add_argument("--new-id")
    plugins_clone.add_argument("--name")
    plugins_clone.add_argument("--content")
    plugins_clone.add_argument("--description")
    plugins_clone.add_argument("--url")
    plugins_clone.add_argument("--tag", action="append", default=None)
    plugins_clone.add_argument("--tool", action="append", default=None)
    plugins_clone.add_argument("--knowledge", action="append", default=None)
    plugins_clone.add_argument("--skill", action="append", default=None)
    plugins_clone.add_argument("--event", action="append", default=None)
    plugins_clone.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    plugins_clone.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    plugins_clone.set_defaults(func=command_plugins, action="clone")

    plugins_cmd.set_defaults(func=command_plugins, action="list")
    command_parsers["plugins"] = plugins_cmd

    pipelines_cmd = sub.add_parser(
        "pipelines", help="manage reusable pipeline and workflow manifests"
    )
    pipelines_sub = pipelines_cmd.add_subparsers(dest="pipelines_command")

    pipelines_list = pipelines_sub.add_parser("list", help="list saved pipelines")
    pipelines_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    pipelines_list.add_argument("--dry-run", action="store_true")
    pipelines_list.set_defaults(func=command_pipelines, action="list")

    pipelines_add = pipelines_sub.add_parser("add", help="add or replace a pipeline")
    pipelines_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    pipelines_add.add_argument("--dry-run", action="store_true")
    pipelines_add.add_argument("--id")
    pipelines_add.add_argument("--name", required=True)
    pipelines_add.add_argument("--content", required=True)
    pipelines_add.add_argument("--description")
    pipelines_add.add_argument("--url")
    pipelines_add.add_argument("--tag", action="append", default=[])
    pipelines_add.add_argument("--tool", action="append", default=[])
    pipelines_add.add_argument("--knowledge", action="append", default=[])
    pipelines_add.add_argument("--skill", action="append", default=[])
    pipelines_add.add_argument("--event", action="append", default=[])
    pipelines_add.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    pipelines_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    pipelines_add.set_defaults(func=command_pipelines, action="add")

    pipelines_remove = pipelines_sub.add_parser("remove", help="remove a pipeline")
    pipelines_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    pipelines_remove.add_argument("--dry-run", action="store_true")
    pipelines_remove.add_argument("--id", required=True)
    pipelines_remove.set_defaults(func=command_pipelines, action="remove")

    pipelines_import = pipelines_sub.add_parser(
        "import", help="import pipelines from JSON files or Markdown files"
    )
    pipelines_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    pipelines_import.add_argument("--dry-run", action="store_true")
    pipelines_import.add_argument("source")
    pipelines_import.set_defaults(func=command_pipelines, action="import")

    pipelines_export = pipelines_sub.add_parser(
        "export", help="export pipelines to a JSON file"
    )
    pipelines_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    pipelines_export.add_argument("--dry-run", action="store_true")
    pipelines_export.add_argument("output")
    pipelines_export.set_defaults(func=command_pipelines, action="export")

    pipelines_share = pipelines_sub.add_parser(
        "share", help="export a single pipeline as markdown, html, or json"
    )
    pipelines_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    pipelines_share.add_argument("--dry-run", action="store_true")
    pipelines_share.add_argument("--id", required=True)
    pipelines_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    pipelines_share.add_argument("output")
    pipelines_share.set_defaults(func=command_pipelines, action="share")

    pipelines_clone = pipelines_sub.add_parser("clone", help="clone a pipeline into a new entry")
    pipelines_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    pipelines_clone.add_argument("--dry-run", action="store_true")
    pipelines_clone.add_argument("--id", required=True)
    pipelines_clone.add_argument("--new-id")
    pipelines_clone.add_argument("--name")
    pipelines_clone.add_argument("--content")
    pipelines_clone.add_argument("--description")
    pipelines_clone.add_argument("--url")
    pipelines_clone.add_argument("--tag", action="append", default=None)
    pipelines_clone.add_argument("--tool", action="append", default=None)
    pipelines_clone.add_argument("--knowledge", action="append", default=None)
    pipelines_clone.add_argument("--skill", action="append", default=None)
    pipelines_clone.add_argument("--event", action="append", default=None)
    pipelines_clone.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    pipelines_clone.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    pipelines_clone.set_defaults(func=command_pipelines, action="clone")

    pipelines_cmd.set_defaults(func=command_pipelines, action="list")
    command_parsers["pipelines"] = pipelines_cmd

    filters_cmd = sub.add_parser(
        "filters", help="manage reusable filter manifests"
    )
    filters_sub = filters_cmd.add_subparsers(dest="filters_command")

    filters_list = filters_sub.add_parser("list", help="list saved filters")
    filters_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    filters_list.add_argument("--dry-run", action="store_true")
    filters_list.set_defaults(func=command_filters, action="list")

    filters_add = filters_sub.add_parser("add", help="add or replace a filter")
    filters_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    filters_add.add_argument("--dry-run", action="store_true")
    filters_add.add_argument("--id")
    filters_add.add_argument("--name", required=True)
    filters_add.add_argument("--content", required=True)
    filters_add.add_argument("--description")
    filters_add.add_argument("--url")
    filters_add.add_argument("--tag", action="append", default=[])
    filters_add.add_argument("--tool", action="append", default=[])
    filters_add.add_argument("--knowledge", action="append", default=[])
    filters_add.add_argument("--skill", action="append", default=[])
    filters_add.add_argument("--event", action="append", default=[])
    filters_add.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    filters_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    filters_add.set_defaults(func=command_filters, action="add")

    filters_remove = filters_sub.add_parser("remove", help="remove a filter")
    filters_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    filters_remove.add_argument("--dry-run", action="store_true")
    filters_remove.add_argument("--id", required=True)
    filters_remove.set_defaults(func=command_filters, action="remove")

    filters_import = filters_sub.add_parser(
        "import", help="import filters from JSON files or Markdown files"
    )
    filters_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    filters_import.add_argument("--dry-run", action="store_true")
    filters_import.add_argument("source")
    filters_import.set_defaults(func=command_filters, action="import")

    filters_export = filters_sub.add_parser("export", help="export filters to a JSON file")
    filters_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    filters_export.add_argument("--dry-run", action="store_true")
    filters_export.add_argument("output")
    filters_export.set_defaults(func=command_filters, action="export")

    filters_share = filters_sub.add_parser(
        "share", help="export a single filter as markdown, html, or json"
    )
    filters_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    filters_share.add_argument("--dry-run", action="store_true")
    filters_share.add_argument("--id", required=True)
    filters_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    filters_share.add_argument("output")
    filters_share.set_defaults(func=command_filters, action="share")

    filters_clone = filters_sub.add_parser("clone", help="clone a filter into a new entry")
    filters_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    filters_clone.add_argument("--dry-run", action="store_true")
    filters_clone.add_argument("--id", required=True)
    filters_clone.add_argument("--new-id")
    filters_clone.add_argument("--name")
    filters_clone.add_argument("--content")
    filters_clone.add_argument("--description")
    filters_clone.add_argument("--url")
    filters_clone.add_argument("--tag", action="append", default=None)
    filters_clone.add_argument("--tool", action="append", default=None)
    filters_clone.add_argument("--knowledge", action="append", default=None)
    filters_clone.add_argument("--skill", action="append", default=None)
    filters_clone.add_argument("--event", action="append", default=None)
    filters_clone.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    filters_clone.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    filters_clone.set_defaults(func=command_filters, action="clone")

    filters_cmd.set_defaults(func=command_filters, action="list")
    command_parsers["filters"] = filters_cmd

    actions_cmd = sub.add_parser(
        "actions", help="manage reusable action manifests"
    )
    actions_sub = actions_cmd.add_subparsers(dest="actions_command")

    actions_list = actions_sub.add_parser("list", help="list saved actions")
    actions_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    actions_list.add_argument("--dry-run", action="store_true")
    actions_list.set_defaults(func=command_actions, action="list")

    actions_add = actions_sub.add_parser("add", help="add or replace an action")
    actions_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    actions_add.add_argument("--dry-run", action="store_true")
    actions_add.add_argument("--id")
    actions_add.add_argument("--name", required=True)
    actions_add.add_argument("--content", required=True)
    actions_add.add_argument("--description")
    actions_add.add_argument("--url")
    actions_add.add_argument("--tag", action="append", default=[])
    actions_add.add_argument("--tool", action="append", default=[])
    actions_add.add_argument("--knowledge", action="append", default=[])
    actions_add.add_argument("--skill", action="append", default=[])
    actions_add.add_argument("--event", action="append", default=[])
    actions_add.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    actions_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    actions_add.set_defaults(func=command_actions, action="add")

    actions_remove = actions_sub.add_parser("remove", help="remove an action")
    actions_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    actions_remove.add_argument("--dry-run", action="store_true")
    actions_remove.add_argument("--id", required=True)
    actions_remove.set_defaults(func=command_actions, action="remove")

    actions_import = actions_sub.add_parser(
        "import", help="import actions from JSON files or Markdown files"
    )
    actions_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    actions_import.add_argument("--dry-run", action="store_true")
    actions_import.add_argument("source")
    actions_import.set_defaults(func=command_actions, action="import")

    actions_export = actions_sub.add_parser("export", help="export actions to a JSON file")
    actions_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    actions_export.add_argument("--dry-run", action="store_true")
    actions_export.add_argument("output")
    actions_export.set_defaults(func=command_actions, action="export")

    actions_share = actions_sub.add_parser(
        "share", help="export a single action as markdown, html, or json"
    )
    actions_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    actions_share.add_argument("--dry-run", action="store_true")
    actions_share.add_argument("--id", required=True)
    actions_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    actions_share.add_argument("output")
    actions_share.set_defaults(func=command_actions, action="share")

    actions_clone = actions_sub.add_parser("clone", help="clone an action into a new entry")
    actions_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    actions_clone.add_argument("--dry-run", action="store_true")
    actions_clone.add_argument("--id", required=True)
    actions_clone.add_argument("--new-id")
    actions_clone.add_argument("--name")
    actions_clone.add_argument("--content")
    actions_clone.add_argument("--description")
    actions_clone.add_argument("--url")
    actions_clone.add_argument("--tag", action="append", default=None)
    actions_clone.add_argument("--tool", action="append", default=None)
    actions_clone.add_argument("--knowledge", action="append", default=None)
    actions_clone.add_argument("--skill", action="append", default=None)
    actions_clone.add_argument("--event", action="append", default=None)
    actions_clone.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    actions_clone.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    actions_clone.set_defaults(func=command_actions, action="clone")

    actions_cmd.set_defaults(func=command_actions, action="list")
    command_parsers["actions"] = actions_cmd

    automations_cmd = sub.add_parser(
        "automations", help="manage reusable scheduled automation manifests"
    )
    automations_sub = automations_cmd.add_subparsers(dest="automations_command")

    automations_list = automations_sub.add_parser("list", help="list saved automations")
    automations_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    automations_list.add_argument("--dry-run", action="store_true")
    automations_list.set_defaults(func=command_automations, action="list")

    automations_add = automations_sub.add_parser("add", help="add or replace an automation")
    automations_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    automations_add.add_argument("--dry-run", action="store_true")
    automations_add.add_argument("--id")
    automations_add.add_argument("--name", required=True)
    automations_add.add_argument("--content", "--prompt", dest="content", required=True)
    automations_add.add_argument("--schedule", required=True)
    automations_add.add_argument("--timezone")
    automations_add.add_argument("--model")
    automations_add.add_argument("--description")
    automations_add.add_argument("--tag", action="append", default=[])
    automations_add.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    automations_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    automations_add.set_defaults(func=command_automations, action="add")

    automations_remove = automations_sub.add_parser("remove", help="remove an automation")
    automations_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    automations_remove.add_argument("--dry-run", action="store_true")
    automations_remove.add_argument("--id", required=True)
    automations_remove.set_defaults(func=command_automations, action="remove")

    automations_import = automations_sub.add_parser(
        "import", help="import automations from JSON files or Markdown files"
    )
    automations_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    automations_import.add_argument("--dry-run", action="store_true")
    automations_import.add_argument("source")
    automations_import.set_defaults(func=command_automations, action="import")

    automations_export = automations_sub.add_parser(
        "export", help="export automations to a JSON file"
    )
    automations_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    automations_export.add_argument("--dry-run", action="store_true")
    automations_export.add_argument("output")
    automations_export.set_defaults(func=command_automations, action="export")

    automations_share = automations_sub.add_parser(
        "share", help="export a single automation as markdown, html, or json"
    )
    automations_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    automations_share.add_argument("--dry-run", action="store_true")
    automations_share.add_argument("--id", required=True)
    automations_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    automations_share.add_argument("output")
    automations_share.set_defaults(func=command_automations, action="share")

    automations_clone = automations_sub.add_parser(
        "clone", help="clone an automation into a new entry"
    )
    automations_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    automations_clone.add_argument("--dry-run", action="store_true")
    automations_clone.add_argument("--id", required=True)
    automations_clone.add_argument("--new-id")
    automations_clone.add_argument("--name")
    automations_clone.add_argument("--content")
    automations_clone.add_argument("--schedule")
    automations_clone.add_argument("--timezone")
    automations_clone.add_argument("--model")
    automations_clone.add_argument("--description")
    automations_clone.add_argument("--tag", action="append", default=None)
    automations_clone.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    automations_clone.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    automations_clone.set_defaults(func=command_automations, action="clone")

    automations_cmd.set_defaults(func=command_automations, action="list")
    command_parsers["automations"] = automations_cmd

    tools_cmd = sub.add_parser(
        "tools", help="manage reusable tool and MCP server registries"
    )
    tools_sub = tools_cmd.add_subparsers(dest="tool_command")

    tools_list = tools_sub.add_parser("list", help="list saved tool servers")
    tools_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    tools_list.add_argument("--dry-run", action="store_true")
    tools_list.set_defaults(func=command_tools, action="list")

    tools_add = tools_sub.add_parser("add", help="add or replace a tool server")
    tools_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    tools_add.add_argument("--dry-run", action="store_true")
    tools_add.add_argument("--id")
    tools_add.add_argument("--name", required=True)
    tools_add.add_argument("--type", default="mcp")
    tools_add.add_argument("--endpoint", required=True)
    tools_add.add_argument("--description")
    tools_add.add_argument("--auth")
    tools_add.add_argument("--tag", action="append", default=[])
    tools_add.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=True)
    tools_add.set_defaults(func=command_tools, action="add")

    tools_remove = tools_sub.add_parser("remove", help="remove a tool server")
    tools_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    tools_remove.add_argument("--dry-run", action="store_true")
    tools_remove.add_argument("--id", required=True)
    tools_remove.set_defaults(func=command_tools, action="remove")

    tools_import = tools_sub.add_parser(
        "import", help="import tool servers from JSON files or directories"
    )
    tools_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    tools_import.add_argument("--dry-run", action="store_true")
    tools_import.add_argument("source")
    tools_import.set_defaults(func=command_tools, action="import")

    tools_export = tools_sub.add_parser(
        "export", help="export tool servers to a JSON file"
    )
    tools_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    tools_export.add_argument("--dry-run", action="store_true")
    tools_export.add_argument("output")
    tools_export.set_defaults(func=command_tools, action="export")

    tools_clone = tools_sub.add_parser("clone", help="clone a tool server into a new entry")
    tools_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    tools_clone.add_argument("--dry-run", action="store_true")
    tools_clone.add_argument("--id", required=True)
    tools_clone.add_argument("--new-id")
    tools_clone.add_argument("--name")
    tools_clone.add_argument("--type")
    tools_clone.add_argument("--endpoint")
    tools_clone.add_argument("--description")
    tools_clone.add_argument("--auth")
    tools_clone.add_argument("--tag", action="append", default=None)
    tools_clone.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    tools_clone.set_defaults(func=command_tools, action="clone")

    tools_cmd.set_defaults(func=command_tools, action="list")
    command_parsers["tools"] = tools_cmd

    kb_cmd = sub.add_parser(
        "kb", help="manage reusable knowledge base and RAG manifests"
    )
    kb_sub = kb_cmd.add_subparsers(dest="kb_command")

    kb_list = kb_sub.add_parser("list", help="list saved knowledge bases")
    kb_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_list.add_argument("--dry-run", action="store_true")
    kb_list.set_defaults(func=command_kb, action="list")

    kb_add = kb_sub.add_parser("add", help="add or replace a knowledge base")
    kb_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_add.add_argument("--dry-run", action="store_true")
    kb_add.add_argument("--id")
    kb_add.add_argument("--name", required=True)
    kb_add.add_argument("--source-dir")
    kb_add.add_argument("--description")
    kb_add.add_argument("--tag", action="append", default=[])
    kb_add.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=True)
    kb_add.add_argument("--sources", nargs="*")
    kb_add.set_defaults(func=command_kb, action="add")

    kb_remove = kb_sub.add_parser("remove", help="remove a knowledge base")
    kb_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_remove.add_argument("--dry-run", action="store_true")
    kb_remove.add_argument("--id", required=True)
    kb_remove.set_defaults(func=command_kb, action="remove")

    kb_import = kb_sub.add_parser(
        "import", help="import knowledge bases from JSON files or directories"
    )
    kb_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_import.add_argument("--dry-run", action="store_true")
    kb_import.add_argument("source")
    kb_import.set_defaults(func=command_kb, action="import")

    kb_export = kb_sub.add_parser(
        "export", help="export knowledge bases to a JSON file"
    )
    kb_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_export.add_argument("--dry-run", action="store_true")
    kb_export.add_argument("output")
    kb_export.set_defaults(func=command_kb, action="export")

    kb_clone = kb_sub.add_parser("clone", help="clone a knowledge base into a new entry")
    kb_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_clone.add_argument("--dry-run", action="store_true")
    kb_clone.add_argument("--id", required=True)
    kb_clone.add_argument("--new-id")
    kb_clone.add_argument("--name")
    kb_clone.add_argument("--source-dir")
    kb_clone.add_argument("--description")
    kb_clone.add_argument("--tag", action="append", default=None)
    kb_clone.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    kb_clone.add_argument("--sources", nargs="*")
    kb_clone.set_defaults(func=command_kb, action="clone")

    kb_ingest = kb_sub.add_parser(
        "ingest", help="ingest a knowledge source directory into an index manifest"
    )
    kb_ingest.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_ingest.add_argument("--dry-run", action="store_true")
    kb_ingest.add_argument("--base-id")
    kb_ingest.add_argument("--name")
    kb_ingest.add_argument("--description")
    kb_ingest.add_argument("--chunk-size", type=int, default=2000)
    kb_ingest.add_argument("--overlap", type=int, default=200)
    kb_ingest.add_argument("source_dir")
    kb_ingest.add_argument("output")
    kb_ingest.set_defaults(func=command_kb, action="ingest")

    kb_ingest_url = kb_sub.add_parser(
        "ingest-url", help="ingest web pages into a knowledge index manifest"
    )
    kb_ingest_url.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_ingest_url.add_argument("--dry-run", action="store_true")
    kb_ingest_url.add_argument("--base-id")
    kb_ingest_url.add_argument("--name")
    kb_ingest_url.add_argument("--description")
    kb_ingest_url.add_argument("--chunk-size", type=int, default=2000)
    kb_ingest_url.add_argument("--overlap", type=int, default=200)
    kb_ingest_url.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    kb_ingest_url.add_argument("urls", nargs="+")
    kb_ingest_url.add_argument("output")
    kb_ingest_url.set_defaults(func=command_kb, action="ingest-url")

    kb_refresh = kb_sub.add_parser(
        "refresh", help="refresh an existing registered knowledge base from its saved source"
    )
    kb_refresh.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_refresh.add_argument("--dry-run", action="store_true")
    kb_refresh.add_argument("--base-id", required=True)
    kb_refresh.add_argument("--chunk-size", type=int, default=2000)
    kb_refresh.add_argument("--overlap", type=int, default=200)
    kb_refresh.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    kb_refresh.add_argument("output")
    kb_refresh.set_defaults(func=command_kb, action="refresh")

    kb_sync = kb_sub.add_parser(
        "sync", help="refresh every registered knowledge base and export rebuilt indexes"
    )
    kb_sync.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_sync.add_argument("--dry-run", action="store_true")
    kb_sync.add_argument("--base-id", help="limit sync to one knowledge base")
    kb_sync.add_argument("--chunk-size", type=int, default=2000)
    kb_sync.add_argument("--overlap", type=int, default=200)
    kb_sync.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    kb_sync.add_argument("output")
    kb_sync.set_defaults(func=command_kb, action="sync")

    kb_watch = kb_sub.add_parser(
        "watch", help="continuously refresh registered knowledge bases"
    )
    kb_watch.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_watch.add_argument("--dry-run", action="store_true")
    kb_watch.add_argument("--base-id", help="limit watch to one knowledge base")
    kb_watch.add_argument("--chunk-size", type=int, default=2000)
    kb_watch.add_argument("--overlap", type=int, default=200)
    kb_watch.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    kb_watch.add_argument("--interval", type=float, default=2.0)
    kb_watch.add_argument("--iterations", type=int)
    kb_watch.add_argument("output")
    kb_watch.set_defaults(func=command_kb, action="watch")

    kb_query = kb_sub.add_parser(
        "query", help="query ingested knowledge indexes for relevant chunks"
    )
    kb_query.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    kb_query.add_argument("--dry-run", action="store_true")
    kb_query.add_argument("--base-id")
    kb_query.add_argument("--index", help="additional index JSON file or directory")
    kb_query.add_argument("query")
    kb_query.set_defaults(func=command_kb, action="query")

    kb_cmd.set_defaults(func=command_kb, action="list")
    command_parsers["kb"] = kb_cmd

    snapshot_cmd = sub.add_parser(
        "snapshot", help="export or restore the full qwen-gen settings tree"
    )
    snapshot_sub = snapshot_cmd.add_subparsers(dest="snapshot_command")

    snapshot_export = snapshot_sub.add_parser("export", help="export settings to a portable JSON snapshot")
    snapshot_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    snapshot_export.add_argument("--dry-run", action="store_true")
    snapshot_export.add_argument("output")
    snapshot_export.set_defaults(func=command_snapshot, action="export")

    snapshot_import = snapshot_sub.add_parser("import", help="restore settings from a JSON snapshot")
    snapshot_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    snapshot_import.add_argument("--dry-run", action="store_true")
    snapshot_import.add_argument("source")
    snapshot_import.set_defaults(func=command_snapshot, action="import")

    snapshot_sync = snapshot_sub.add_parser(
        "sync", help="synchronize settings with a snapshot file using mtimes"
    )
    snapshot_sync.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    snapshot_sync.add_argument("--dry-run", action="store_true")
    snapshot_sync.add_argument(
        "--mode", choices=("mirror", "push", "pull"), default="mirror"
    )
    snapshot_sync.add_argument("snapshot")
    snapshot_sync.set_defaults(func=command_snapshot, action="sync")

    snapshot_watch = snapshot_sub.add_parser(
        "watch", help="continuously synchronize settings with a snapshot file"
    )
    snapshot_watch.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    snapshot_watch.add_argument("--dry-run", action="store_true")
    snapshot_watch.add_argument(
        "--mode", choices=("mirror", "push", "pull"), default="mirror"
    )
    snapshot_watch.add_argument("--interval", type=float, default=2.0)
    snapshot_watch.add_argument("--iterations", type=int)
    snapshot_watch.add_argument("snapshot")
    snapshot_watch.set_defaults(func=command_snapshot, action="watch")

    snapshot_cmd.set_defaults(func=command_snapshot, action="export")
    command_parsers["snapshot"] = snapshot_cmd

    notes_cmd = sub.add_parser(
        "notes", help="manage reusable notes and chat-side markdown snippets"
    )
    notes_sub = notes_cmd.add_subparsers(dest="notes_command")

    notes_list = notes_sub.add_parser("list", help="list saved notes")
    notes_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    notes_list.add_argument("--dry-run", action="store_true")
    notes_list.set_defaults(func=command_notes, action="list")

    notes_add = notes_sub.add_parser("add", help="add or replace a note")
    notes_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    notes_add.add_argument("--dry-run", action="store_true")
    notes_add.add_argument("--id")
    notes_add.add_argument("--title", required=True)
    notes_add.add_argument("--body", required=True)
    notes_add.add_argument("--file", "--attachment", action="append", default=[])
    notes_add.add_argument("--image", action="append", default=[])
    notes_add.add_argument("--tag", action="append", default=[])
    notes_add.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    notes_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    notes_add.set_defaults(func=command_notes, action="add")

    notes_remove = notes_sub.add_parser("remove", help="remove a note")
    notes_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    notes_remove.add_argument("--dry-run", action="store_true")
    notes_remove.add_argument("--id", required=True)
    notes_remove.set_defaults(func=command_notes, action="remove")

    notes_import = notes_sub.add_parser(
        "import", help="import notes from JSON files or Markdown files"
    )
    notes_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    notes_import.add_argument("--dry-run", action="store_true")
    notes_import.add_argument("source")
    notes_import.set_defaults(func=command_notes, action="import")

    notes_export = notes_sub.add_parser("export", help="export notes to a JSON file")
    notes_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    notes_export.add_argument("--dry-run", action="store_true")
    notes_export.add_argument("output")
    notes_export.set_defaults(func=command_notes, action="export")

    notes_share = notes_sub.add_parser("share", help="export a note as markdown or html")
    notes_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    notes_share.add_argument("--dry-run", action="store_true")
    notes_share.add_argument("--id", required=True)
    notes_share.add_argument("--format", choices=("md", "html"), default="md")
    notes_share.add_argument("output")
    notes_share.set_defaults(func=command_notes, action="share")

    notes_clone = notes_sub.add_parser("clone", help="clone a note into a new entry")
    notes_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    notes_clone.add_argument("--dry-run", action="store_true")
    notes_clone.add_argument("--id", required=True)
    notes_clone.add_argument("--new-id")
    notes_clone.add_argument("--title")
    notes_clone.add_argument("--file", "--attachment", action="append", default=None)
    notes_clone.add_argument("--image", action="append", default=None)
    notes_clone.add_argument("--tag", action="append", default=None)
    notes_clone.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    notes_clone.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    notes_clone.set_defaults(func=command_notes, action="clone")

    notes_cmd.set_defaults(func=command_notes, action="list")
    command_parsers["notes"] = notes_cmd

    folders_cmd = sub.add_parser(
        "folders", help="manage reusable conversation folders and project workspaces"
    )
    folders_sub = folders_cmd.add_subparsers(dest="folders_command")

    folders_list = folders_sub.add_parser("list", help="list saved folders")
    folders_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    folders_list.add_argument("--dry-run", action="store_true")
    folders_list.set_defaults(func=command_folders, action="list")

    folders_add = folders_sub.add_parser("add", help="add or replace a folder")
    folders_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    folders_add.add_argument("--dry-run", action="store_true")
    folders_add.add_argument("--id")
    folders_add.add_argument("--name", required=True)
    folders_add.add_argument("--parent")
    folders_add.add_argument("--system-prompt")
    folders_add.add_argument("--source-dir")
    folders_add.add_argument("--description")
    folders_add.add_argument("--knowledge", action="append", default=[])
    folders_add.add_argument("--tag", action="append", default=[])
    folders_add.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    folders_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    folders_add.add_argument("--unread-count", type=int)
    folders_add.set_defaults(func=command_folders, action="add")

    folders_remove = folders_sub.add_parser("remove", help="remove a folder")
    folders_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    folders_remove.add_argument("--dry-run", action="store_true")
    folders_remove.add_argument("--id", required=True)
    folders_remove.set_defaults(func=command_folders, action="remove")

    folders_import = folders_sub.add_parser(
        "import", help="import folders from JSON files or directories"
    )
    folders_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    folders_import.add_argument("--dry-run", action="store_true")
    folders_import.add_argument("source")
    folders_import.set_defaults(func=command_folders, action="import")

    folders_export = folders_sub.add_parser("export", help="export folders to a JSON file")
    folders_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    folders_export.add_argument("--dry-run", action="store_true")
    folders_export.add_argument("output")
    folders_export.set_defaults(func=command_folders, action="export")

    folders_share = folders_sub.add_parser(
        "share", help="export a single folder as markdown, html, or json"
    )
    folders_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    folders_share.add_argument("--dry-run", action="store_true")
    folders_share.add_argument("--id", required=True)
    folders_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    folders_share.add_argument("output")
    folders_share.set_defaults(func=command_folders, action="share")

    folders_clone = folders_sub.add_parser(
        "clone", help="clone a folder into a new workspace entry"
    )
    folders_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    folders_clone.add_argument("--dry-run", action="store_true")
    folders_clone.add_argument("--id", required=True)
    folders_clone.add_argument("--new-id")
    folders_clone.add_argument("--name")
    folders_clone.add_argument("--parent")
    folders_clone.add_argument("--system-prompt")
    folders_clone.add_argument("--source-dir")
    folders_clone.add_argument("--description")
    folders_clone.add_argument("--knowledge", action="append", default=None)
    folders_clone.add_argument("--tag", action="append", default=None)
    folders_clone.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    folders_clone.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    folders_clone.add_argument("--unread-count", type=int)
    folders_clone.set_defaults(func=command_folders, action="clone")

    folders_cmd.set_defaults(func=command_folders, action="list")
    command_parsers["folders"] = folders_cmd

    memories_cmd = sub.add_parser(
        "memories", help="manage reusable long-term memory facts and preferences"
    )
    memories_sub = memories_cmd.add_subparsers(dest="memories_command")

    memories_list = memories_sub.add_parser("list", help="list saved memories")
    memories_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    memories_list.add_argument("--dry-run", action="store_true")
    memories_list.set_defaults(func=command_memories, action="list")

    memories_add = memories_sub.add_parser("add", help="add or replace a memory")
    memories_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    memories_add.add_argument("--dry-run", action="store_true")
    memories_add.add_argument("--id")
    memories_add.add_argument("--title", required=True)
    memories_add.add_argument("--content", required=True)
    memories_add.add_argument("--scope", default="user")
    memories_add.add_argument("--source")
    memories_add.add_argument("--tag", action="append", default=[])
    memories_add.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    memories_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    memories_add.set_defaults(func=command_memories, action="add")

    memories_remove = memories_sub.add_parser("remove", help="remove a memory")
    memories_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    memories_remove.add_argument("--dry-run", action="store_true")
    memories_remove.add_argument("--id", required=True)
    memories_remove.set_defaults(func=command_memories, action="remove")

    memories_import = memories_sub.add_parser(
        "import", help="import memories from JSON files or Markdown files"
    )
    memories_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    memories_import.add_argument("--dry-run", action="store_true")
    memories_import.add_argument("source")
    memories_import.set_defaults(func=command_memories, action="import")

    memories_export = memories_sub.add_parser("export", help="export memories to a JSON file")
    memories_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    memories_export.add_argument("--dry-run", action="store_true")
    memories_export.add_argument("output")
    memories_export.set_defaults(func=command_memories, action="export")

    memories_share = memories_sub.add_parser(
        "share", help="export a single memory as markdown, html, or json"
    )
    memories_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    memories_share.add_argument("--dry-run", action="store_true")
    memories_share.add_argument("--id", required=True)
    memories_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    memories_share.add_argument("output")
    memories_share.set_defaults(func=command_memories, action="share")

    memories_clone = memories_sub.add_parser("clone", help="clone a memory into a new entry")
    memories_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    memories_clone.add_argument("--dry-run", action="store_true")
    memories_clone.add_argument("--id", required=True)
    memories_clone.add_argument("--new-id")
    memories_clone.add_argument("--title")
    memories_clone.add_argument("--content")
    memories_clone.add_argument("--scope")
    memories_clone.add_argument("--source")
    memories_clone.add_argument("--tag", action="append", default=None)
    memories_clone.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    memories_clone.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    memories_clone.set_defaults(func=command_memories, action="clone")

    memories_cmd.set_defaults(func=command_memories, action="list")
    command_parsers["memories"] = memories_cmd

    files_cmd = sub.add_parser(
        "files", help="manage reusable files, uploads, and attachments"
    )
    files_sub = files_cmd.add_subparsers(dest="files_command")

    files_list = files_sub.add_parser("list", help="list saved files")
    files_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    files_list.add_argument("--dry-run", action="store_true")
    files_list.set_defaults(func=command_files, action="list")

    files_add = files_sub.add_parser("add", help="add or replace a file")
    files_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    files_add.add_argument("--dry-run", action="store_true")
    files_add.add_argument("--id")
    files_add.add_argument("--name", required=True)
    files_add.add_argument("--content", required=True)
    files_add.add_argument("--path")
    files_add.add_argument("--kind", default="text")
    files_add.add_argument("--description")
    files_add.add_argument("--tag", action="append", default=[])
    files_add.add_argument("--size", type=int)
    files_add.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    files_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    files_add.set_defaults(func=command_files, action="add")

    files_remove = files_sub.add_parser("remove", help="remove a file")
    files_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    files_remove.add_argument("--dry-run", action="store_true")
    files_remove.add_argument("--id", required=True)
    files_remove.set_defaults(func=command_files, action="remove")

    files_import = files_sub.add_parser(
        "import", help="import files from JSON files or directories"
    )
    files_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    files_import.add_argument("--dry-run", action="store_true")
    files_import.add_argument("source")
    files_import.set_defaults(func=command_files, action="import")

    files_export = files_sub.add_parser("export", help="export files to a JSON file")
    files_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    files_export.add_argument("--dry-run", action="store_true")
    files_export.add_argument("output")
    files_export.set_defaults(func=command_files, action="export")

    files_share = files_sub.add_parser(
        "share", help="export a single file as markdown or json"
    )
    files_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    files_share.add_argument("--dry-run", action="store_true")
    files_share.add_argument("--id", required=True)
    files_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    files_share.add_argument("output")
    files_share.set_defaults(func=command_files, action="share")

    files_clone = files_sub.add_parser("clone", help="clone a file entry into a new item")
    files_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    files_clone.add_argument("--dry-run", action="store_true")
    files_clone.add_argument("--id", required=True)
    files_clone.add_argument("--new-id")
    files_clone.add_argument("--name")
    files_clone.set_defaults(func=command_files, action="clone")

    files_cmd.set_defaults(func=command_files, action="list")
    command_parsers["files"] = files_cmd

    artifacts_cmd = sub.add_parser(
        "artifacts", help="manage reusable artifacts and generated content snippets"
    )
    artifacts_sub = artifacts_cmd.add_subparsers(dest="artifacts_command")

    artifacts_list = artifacts_sub.add_parser("list", help="list saved artifacts")
    artifacts_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    artifacts_list.add_argument("--dry-run", action="store_true")
    artifacts_list.set_defaults(func=command_artifacts, action="list")

    artifacts_add = artifacts_sub.add_parser("add", help="add or replace an artifact")
    artifacts_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    artifacts_add.add_argument("--dry-run", action="store_true")
    artifacts_add.add_argument("--id")
    artifacts_add.add_argument("--title", required=True)
    artifacts_add.add_argument("--content", required=True)
    artifacts_add.add_argument("--kind", default="text")
    artifacts_add.add_argument("--tag", action="append", default=[])
    artifacts_add.set_defaults(func=command_artifacts, action="add")

    artifacts_remove = artifacts_sub.add_parser("remove", help="remove an artifact")
    artifacts_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    artifacts_remove.add_argument("--dry-run", action="store_true")
    artifacts_remove.add_argument("--id", required=True)
    artifacts_remove.set_defaults(func=command_artifacts, action="remove")

    artifacts_import = artifacts_sub.add_parser(
        "import", help="import artifacts from JSON files or directories"
    )
    artifacts_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    artifacts_import.add_argument("--dry-run", action="store_true")
    artifacts_import.add_argument("source")
    artifacts_import.set_defaults(func=command_artifacts, action="import")

    artifacts_export = artifacts_sub.add_parser(
        "export", help="export artifacts to a JSON file"
    )
    artifacts_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    artifacts_export.add_argument("--dry-run", action="store_true")
    artifacts_export.add_argument("output")
    artifacts_export.set_defaults(func=command_artifacts, action="export")

    artifacts_share = artifacts_sub.add_parser(
        "share", help="export a single artifact as markdown, html, or json"
    )
    artifacts_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    artifacts_share.add_argument("--dry-run", action="store_true")
    artifacts_share.add_argument("--id", required=True)
    artifacts_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    artifacts_share.add_argument("output")
    artifacts_share.set_defaults(func=command_artifacts, action="share")

    artifacts_clone = artifacts_sub.add_parser(
        "clone", help="clone an artifact into a new entry"
    )
    artifacts_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    artifacts_clone.add_argument("--dry-run", action="store_true")
    artifacts_clone.add_argument("--id", required=True)
    artifacts_clone.add_argument("--new-id")
    artifacts_clone.add_argument("--title")
    artifacts_clone.add_argument("--kind")
    artifacts_clone.add_argument("--tag", action="append", default=None)
    artifacts_clone.set_defaults(func=command_artifacts, action="clone")

    artifacts_cmd.set_defaults(func=command_artifacts, action="list")
    command_parsers["artifacts"] = artifacts_cmd

    conversations_cmd = sub.add_parser(
        "conversations", help="manage reusable conversation histories and transcripts"
    )
    conversations_sub = conversations_cmd.add_subparsers(dest="conversations_command")

    conversations_list = conversations_sub.add_parser(
        "list", help="list saved conversations"
    )
    conversations_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    conversations_list.add_argument("--dry-run", action="store_true")
    conversations_list.set_defaults(func=command_conversations, action="list")

    conversations_add = conversations_sub.add_parser(
        "add", help="add or replace a conversation history"
    )
    conversations_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    conversations_add.add_argument("--dry-run", action="store_true")
    conversations_add.add_argument("--id")
    conversations_add.add_argument("--title", required=True)
    conversations_add.add_argument("--folder")
    conversations_add.add_argument("--system-prompt")
    conversations_add.add_argument("--knowledge", action="append", default=[])
    conversations_add.add_argument("--file", "--attachment", action="append", default=[])
    conversations_add.add_argument("--image", action="append", default=[])
    conversations_add.add_argument("--transcript")
    conversations_add.add_argument("--message", action="append", default=[])
    conversations_add.add_argument("--tag", action="append", default=[])
    conversations_add.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    conversations_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    conversations_add.set_defaults(func=command_conversations, action="add")

    conversations_remove = conversations_sub.add_parser(
        "remove", help="remove a conversation"
    )
    conversations_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    conversations_remove.add_argument("--dry-run", action="store_true")
    conversations_remove.add_argument("--id", required=True)
    conversations_remove.set_defaults(func=command_conversations, action="remove")

    conversations_import = conversations_sub.add_parser(
        "import", help="import conversations from JSON files or Markdown transcripts"
    )
    conversations_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    conversations_import.add_argument("--dry-run", action="store_true")
    conversations_import.add_argument("source")
    conversations_import.set_defaults(func=command_conversations, action="import")

    conversations_export = conversations_sub.add_parser(
        "export", help="export conversations to a JSON file"
    )
    conversations_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    conversations_export.add_argument("--dry-run", action="store_true")
    conversations_export.add_argument("output")
    conversations_export.set_defaults(func=command_conversations, action="export")

    conversations_share = conversations_sub.add_parser(
        "share", help="export a conversation as markdown or html"
    )
    conversations_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    conversations_share.add_argument("--dry-run", action="store_true")
    conversations_share.add_argument("--id", required=True)
    conversations_share.add_argument("--format", choices=("md", "html"), default="md")
    conversations_share.add_argument("output")
    conversations_share.set_defaults(func=command_conversations, action="share")

    conversations_clone = conversations_sub.add_parser(
        "clone", help="clone a conversation history into a new session"
    )
    conversations_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    conversations_clone.add_argument("--dry-run", action="store_true")
    conversations_clone.add_argument("--id", required=True)
    conversations_clone.add_argument("--new-id")
    conversations_clone.add_argument("--title")
    conversations_clone.set_defaults(func=command_conversations, action="clone")

    conversations_cmd.set_defaults(func=command_conversations, action="list")
    command_parsers["conversations"] = conversations_cmd

    channels_cmd = sub.add_parser(
        "channels", help="manage reusable shared channels and timelines"
    )
    channels_sub = channels_cmd.add_subparsers(dest="channels_command")

    channels_list = channels_sub.add_parser("list", help="list saved channels")
    channels_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    channels_list.add_argument("--dry-run", action="store_true")
    channels_list.set_defaults(func=command_channels, action="list")

    channels_add = channels_sub.add_parser("add", help="add or replace a channel")
    channels_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    channels_add.add_argument("--dry-run", action="store_true")
    channels_add.add_argument("--id")
    channels_add.add_argument("--title", required=True)
    channels_add.add_argument("--folder")
    channels_add.add_argument("--system-prompt")
    channels_add.add_argument("--knowledge", action="append", default=[])
    channels_add.add_argument("--file", "--attachment", action="append", default=[])
    channels_add.add_argument("--image", action="append", default=[])
    channels_add.add_argument("--transcript")
    channels_add.add_argument("--message", action="append", default=[])
    channels_add.add_argument("--tag", action="append", default=[])
    channels_add.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    channels_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    channels_add.set_defaults(func=command_channels, action="add")

    channels_remove = channels_sub.add_parser("remove", help="remove a channel")
    channels_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    channels_remove.add_argument("--dry-run", action="store_true")
    channels_remove.add_argument("--id", required=True)
    channels_remove.set_defaults(func=command_channels, action="remove")

    channels_import = channels_sub.add_parser(
        "import", help="import channels from JSON files or Markdown transcripts"
    )
    channels_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    channels_import.add_argument("--dry-run", action="store_true")
    channels_import.add_argument("source")
    channels_import.set_defaults(func=command_channels, action="import")

    channels_export = channels_sub.add_parser("export", help="export channels to a JSON file")
    channels_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    channels_export.add_argument("--dry-run", action="store_true")
    channels_export.add_argument("output")
    channels_export.set_defaults(func=command_channels, action="export")

    channels_share = channels_sub.add_parser(
        "share", help="share a single channel as markdown, html, or json"
    )
    channels_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    channels_share.add_argument("--dry-run", action="store_true")
    channels_share.add_argument("--id", required=True)
    channels_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    channels_share.add_argument("output")
    channels_share.set_defaults(func=command_channels, action="share")

    channels_clone = channels_sub.add_parser(
        "clone", help="clone a channel timeline into a new entry"
    )
    channels_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    channels_clone.add_argument("--dry-run", action="store_true")
    channels_clone.add_argument("--id", required=True)
    channels_clone.add_argument("--new-id")
    channels_clone.add_argument("--title")
    channels_clone.set_defaults(func=command_channels, action="clone")

    channels_cmd.set_defaults(func=command_channels, action="list")
    command_parsers["channels"] = channels_cmd

    webhooks_cmd = sub.add_parser(
        "webhooks", help="manage reusable webhook and notification targets"
    )
    webhooks_sub = webhooks_cmd.add_subparsers(dest="webhooks_command")

    webhooks_list = webhooks_sub.add_parser("list", help="list saved webhooks")
    webhooks_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    webhooks_list.add_argument("--dry-run", action="store_true")
    webhooks_list.set_defaults(func=command_webhooks, action="list")

    webhooks_add = webhooks_sub.add_parser("add", help="add or replace a webhook target")
    webhooks_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    webhooks_add.add_argument("--dry-run", action="store_true")
    webhooks_add.add_argument("--id")
    webhooks_add.add_argument("--name", required=True)
    webhooks_add.add_argument("--url", required=True)
    webhooks_add.add_argument("--event", action="append", default=[])
    webhooks_add.add_argument("--description")
    webhooks_add.add_argument("--secret")
    webhooks_add.add_argument("--tag", action="append", default=[])
    webhooks_add.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    webhooks_add.set_defaults(func=command_webhooks, action="add")

    webhooks_remove = webhooks_sub.add_parser("remove", help="remove a webhook target")
    webhooks_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    webhooks_remove.add_argument("--dry-run", action="store_true")
    webhooks_remove.add_argument("--id", required=True)
    webhooks_remove.set_defaults(func=command_webhooks, action="remove")

    webhooks_import = webhooks_sub.add_parser(
        "import", help="import webhooks from JSON files or directories"
    )
    webhooks_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    webhooks_import.add_argument("--dry-run", action="store_true")
    webhooks_import.add_argument("source")
    webhooks_import.set_defaults(func=command_webhooks, action="import")

    webhooks_export = webhooks_sub.add_parser("export", help="export webhooks to a JSON file")
    webhooks_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    webhooks_export.add_argument("--dry-run", action="store_true")
    webhooks_export.add_argument("output")
    webhooks_export.set_defaults(func=command_webhooks, action="export")

    webhooks_share = webhooks_sub.add_parser(
        "share", help="export a single webhook as markdown, html, or json"
    )
    webhooks_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    webhooks_share.add_argument("--dry-run", action="store_true")
    webhooks_share.add_argument("--id", required=True)
    webhooks_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    webhooks_share.add_argument("output")
    webhooks_share.set_defaults(func=command_webhooks, action="share")

    webhooks_clone = webhooks_sub.add_parser("clone", help="clone a webhook target into a new entry")
    webhooks_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    webhooks_clone.add_argument("--dry-run", action="store_true")
    webhooks_clone.add_argument("--id", required=True)
    webhooks_clone.add_argument("--new-id")
    webhooks_clone.add_argument("--name")
    webhooks_clone.add_argument("--url")
    webhooks_clone.add_argument("--event", action="append", default=None)
    webhooks_clone.add_argument("--description")
    webhooks_clone.add_argument("--secret")
    webhooks_clone.add_argument("--tag", action="append", default=None)
    webhooks_clone.add_argument("--enabled", action=argparse.BooleanOptionalAction, default=None)
    webhooks_clone.set_defaults(func=command_webhooks, action="clone")

    webhooks_cmd.set_defaults(func=command_webhooks, action="list")
    command_parsers["webhooks"] = webhooks_cmd

    agents_cmd = sub.add_parser(
        "agents", help="manage reusable model presets and agent wrappers"
    )
    agents_sub = agents_cmd.add_subparsers(dest="agents_command")

    agents_list = agents_sub.add_parser("list", help="list saved agents")
    agents_list.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    agents_list.add_argument("--dry-run", action="store_true")
    agents_list.set_defaults(func=command_agents, action="list")

    agents_add = agents_sub.add_parser("add", help="add or replace an agent preset")
    agents_add.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    agents_add.add_argument("--dry-run", action="store_true")
    agents_add.add_argument("--id")
    agents_add.add_argument("--name", required=True)
    agents_add.add_argument("--base-model", "--model", dest="base_model", required=True)
    agents_add.add_argument("--system-prompt")
    agents_add.add_argument("--description")
    agents_add.add_argument("--avatar")
    agents_add.add_argument("--voice")
    agents_add.add_argument("--visibility", choices=("public", "private"))
    agents_add.add_argument("--tag", action="append", default=[])
    agents_add.add_argument("--tool", action="append", default=[])
    agents_add.add_argument("--knowledge", action="append", default=[])
    agents_add.add_argument("--skill", action="append", default=[])
    agents_add.add_argument("--param", action="append", default=[])
    agents_add.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    agents_add.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)
    agents_add.set_defaults(func=command_agents, action="add")

    agents_remove = agents_sub.add_parser("remove", help="remove an agent preset")
    agents_remove.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    agents_remove.add_argument("--dry-run", action="store_true")
    agents_remove.add_argument("--id", required=True)
    agents_remove.set_defaults(func=command_agents, action="remove")

    agents_import = agents_sub.add_parser(
        "import", help="import agents from JSON files or directories"
    )
    agents_import.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    agents_import.add_argument("--dry-run", action="store_true")
    agents_import.add_argument("source")
    agents_import.set_defaults(func=command_agents, action="import")

    agents_export = agents_sub.add_parser("export", help="export agents to a JSON file")
    agents_export.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    agents_export.add_argument("--dry-run", action="store_true")
    agents_export.add_argument("output")
    agents_export.set_defaults(func=command_agents, action="export")

    agents_share = agents_sub.add_parser(
        "share", help="export a single agent as markdown, html, or json"
    )
    agents_share.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    agents_share.add_argument("--dry-run", action="store_true")
    agents_share.add_argument("--id", required=True)
    agents_share.add_argument("--format", choices=("md", "json", "html"), default="md")
    agents_share.add_argument("output")
    agents_share.set_defaults(func=command_agents, action="share")

    agents_clone = agents_sub.add_parser(
        "clone", help="clone an agent preset into a new entry"
    )
    agents_clone.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    agents_clone.add_argument("--dry-run", action="store_true")
    agents_clone.add_argument("--id", required=True)
    agents_clone.add_argument("--new-id")
    agents_clone.add_argument("--name")
    agents_clone.set_defaults(func=command_agents, action="clone")

    agents_cmd.set_defaults(func=command_agents, action="list")
    command_parsers["agents"] = agents_cmd

    search_cmd = sub.add_parser(
        "search", help="search across prompts, skills, plugins, pipelines, filters, actions, automations, agents, conversations, folders, tools, knowledge, notes, memories, webhooks, and artifacts"
    )
    search_cmd.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    search_cmd.add_argument("--kind", help="limit to a registry scope, like notes or artifacts")
    search_cmd.add_argument("query")
    search_cmd.set_defaults(func=command_search)
    command_parsers["search"] = search_cmd

    web_search_cmd = sub.add_parser(
        "web-search", help="search the web and optionally save results to knowledge"
    )
    web_search_cmd.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    web_search_cmd.add_argument("--dry-run", action="store_true")
    web_search_cmd.add_argument("--list-providers", action="store_true")
    web_search_cmd.add_argument("--provider", choices=sorted(WEB_SEARCH_PROVIDERS))
    web_search_cmd.add_argument(
        "--fallback-provider",
        action="append",
        choices=sorted(WEB_SEARCH_PROVIDERS),
        default=[],
        help="additional providers to query if the primary provider fails or returns duplicates",
    )
    web_search_cmd.add_argument(
        "--engine-url",
        default="https://html.duckduckgo.com/html/?q={query}",
        help="search endpoint template with {query} placeholder",
    )
    web_search_cmd.add_argument("--api-key", help="API key for provider-backed search")
    web_search_cmd.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    web_search_cmd.add_argument("--limit", type=int, default=10)
    web_search_cmd.add_argument("--save-to-knowledge", action="store_true")
    web_search_cmd.add_argument("--save-limit", type=int, default=5)
    web_search_cmd.add_argument("--base-id")
    web_search_cmd.add_argument("--knowledge-name")
    web_search_cmd.add_argument("--description")
    web_search_cmd.add_argument("--chunk-size", type=int, default=2000)
    web_search_cmd.add_argument("--overlap", type=int, default=200)
    web_search_cmd.add_argument("query", nargs="?")
    web_search_cmd.add_argument("output", nargs="?")
    web_search_cmd.set_defaults(func=command_web_search)
    command_parsers["web-search"] = web_search_cmd

    prov = sub.add_parser(
        "providers", help="list supported provider URLs, names, and environment keys"
    )
    prov.add_argument("action", nargs="?", choices=("add",))
    prov.add_argument("target", nargs="?", choices=("all",))
    prov.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    prov.add_argument("--env-root", default=str(pathlib.Path.home()))
    prov.add_argument("--query", "-q", help="search filter for provider key/name/URL")
    prov.add_argument("--free", action="store_true", help="sync free models instead of placeholders")
    prov.add_argument(
        "--auto-fallback",
        action="store_true",
        help="fall back to curated free catalogs when live discovery is unavailable",
    )
    prov.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    prov.add_argument("--insecure", action="store_true")
    prov.add_argument("--dry-run", action="store_true")
    prov.set_defaults(func=command_providers)
    command_parsers["providers"] = prov

    ic = sub.add_parser(
        "install-coder",
        help="one-shot Qwen Coder setup: detect backend, select model, generate settings",
    )
    ic.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    ic.add_argument(
        "--backend",
        choices=(
            "auto",
            "ollama",
            "litellm",
            "lmstudio",
            "nextchat",
            "open_webui",
            "dashscope",
            "openrouter",
            "siliconflow",
        ),
        default="auto",
        help="inference backend (default: auto-detect)",
    )
    ic.add_argument("--model", default="", help="override auto-selected model")
    ic.add_argument("--free", action="store_true", help="restrict to zero-cost models")
    ic.add_argument(
        "--approval-mode",
        choices=("plan", "default", "auto-edit", "auto", "yolo"),
        default="default",
    )
    ic.add_argument("--dry-run", action="store_true")
    ic.set_defaults(func=command_install_coder)
    command_parsers["install-coder"] = ic

    serve_cmd = sub.add_parser(
        "serve", help="start a local NextChat/Open WebUI-style chat interface"
    )
    serve_cmd.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8787)
    serve_cmd.set_defaults(func=command_serve)
    command_parsers["serve"] = serve_cmd

    help_cmd = sub.add_parser("help", help="show help for qwen-omega or a command")
    help_cmd.add_argument(
        "topic",
        nargs="?",
        choices=sorted(command_parsers),
        help="optional command name to show detailed help for",
    )

    def command_help(args: argparse.Namespace) -> int:
        if args.topic:
            command_parsers[args.topic].print_help()
        else:
            parser.print_help()
        return 0

    help_cmd.set_defaults(func=command_help, parser=parser)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
