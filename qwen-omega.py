#!/usr/bin/env python3
"""Qwen Omega ProMeta configuration generator and validator.

Generates Qwen Code settings using the current v4 modelProviders schema:
  modelProviders.<protocol> = [ModelConfig, ...]

No API key values are written to settings.json. Credentials are referenced by envKey.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

VERSION = "1.1.0"
DEFAULT_TIMEOUT = 30
DEFAULT_SETTINGS = pathlib.Path.home() / ".qwen" / "settings.json"
DEFAULT_ENV = pathlib.Path.home() / ".qwen" / ".env"


@dataclass(frozen=True)
class ProviderPreset:
    name: str
    protocol: str
    base_url: str
    env_key: str


PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset("OpenAI", "openai", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openrouter": ProviderPreset("OpenRouter", "openai", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "nvidia": ProviderPreset("NVIDIA NIM", "openai", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
    "groq": ProviderPreset("Groq", "openai", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "together": ProviderPreset("Together AI", "openai", "https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "fireworks": ProviderPreset("Fireworks AI", "openai", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
    "deepinfra": ProviderPreset("DeepInfra", "openai", "https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY"),
    "cerebras": ProviderPreset("Cerebras", "openai", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
    "mistral": ProviderPreset("Mistral", "openai", "https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "dashscope": ProviderPreset("Alibaba DashScope", "openai", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "ollama": ProviderPreset("Ollama", "openai", "http://127.0.0.1:11434/v1", "OLLAMA_API_KEY"),
    "litellm": ProviderPreset("LiteLLM", "openai", "http://127.0.0.1:4000/v1", "LITELLM_API_KEY"),
    "siliconflow": ProviderPreset("SiliconFlow", "openai", "https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY"),
    "featherless": ProviderPreset("Featherless", "openai", "https://api.featherless.ai/v1", "FEATHERLESS_API_KEY"),
    "novita": ProviderPreset("Novita AI", "openai", "https://api.novita.ai/v3/openai", "NOVITA_API_KEY"),
    "hyperbolic": ProviderPreset("Hyperbolic", "openai", "https://api.hyperbolic.xyz/v1", "HYPERBOLIC_API_KEY"),
    "anyscale": ProviderPreset("Anyscale Endpoints", "openai", "https://api.endpoints.anyscale.com/v1", "ANYSCALE_API_KEY"),
    "friendli": ProviderPreset("FriendliAI", "openai", "https://inference.friendli.ai/v1", "FRIENDLI_TOKEN"),
    "sambanova": ProviderPreset("SambaNova", "openai", "https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY"),
    "deepseek": ProviderPreset("DeepSeek", "openai", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "ai21": ProviderPreset("AI21 Studio", "openai", "https://api.ai21.com/studio/v1", "AI21_API_KEY"),
    "perplexity": ProviderPreset("Perplexity", "openai", "https://api.perplexity.ai", "PERPLEXITY_API_KEY"),
    "cloudflare": ProviderPreset("Cloudflare Workers AI", "openai", "https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1", "CLOUDFLARE_API_KEY"),
    "vllm": ProviderPreset("vLLM", "openai", "http://127.0.0.1:8000/v1", "VLLM_API_KEY"),
    "lmstudio": ProviderPreset("LM Studio", "openai", "http://127.0.0.1:1234/v1", "LMSTUDIO_API_KEY"),
    "tgi": ProviderPreset("Text Generation Inference", "openai", "http://127.0.0.1:8080/v1", "TGI_API_KEY"),
    "sagemaker": ProviderPreset("AWS SageMaker", "openai", "https://runtime.sagemaker.us-east-1.amazonaws.com", "AWS_ACCESS_KEY_ID"),
    "bedrock": ProviderPreset("AWS Bedrock Gateway", "openai", "http://127.0.0.1:8000/v1", "AWS_BEDROCK_API_KEY"),
    "azure-openai": ProviderPreset("Azure OpenAI", "openai", "https://{resource}.openai.azure.com/openai/deployments/{deployment}", "AZURE_OPENAI_API_KEY"),
    "github": ProviderPreset("GitHub Models", "openai", "https://models.inference.ai.azure.com", "GITHUB_TOKEN"),
    "xai": ProviderPreset("xAI (Grok)", "openai", "https://api.x.ai/v1", "XAI_API_KEY"),
    "cohere": ProviderPreset("Cohere", "openai", "https://api.cohere.com/v2", "COHERE_API_KEY"),
    "yi": ProviderPreset("01.AI (Lingyi Wan物)", "openai", "https://api.lingyiwanwu.com/v1", "YI_API_KEY"),
    "zhipu": ProviderPreset("Zhipu AI (GLM)", "openai", "https://open.bigmodel.cn/api/paas/v4", "ZHIPU_API_KEY"),
    "moonshot": ProviderPreset("Moonshot AI (Kimi)", "openai", "https://api.moonshot.cn/v1", "MOONSHOT_API_KEY"),
    "baichuan": ProviderPreset("Baichuan AI", "openai", "https://api.baichuan-ai.com/v1", "BAICHUAN_API_KEY"),
    "minimax": ProviderPreset("MiniMax", "openai", "https://api.minimax.chat/v1", "MINIMAX_API_KEY"),
    "stepfun": ProviderPreset("StepFun (阶跃星辰)", "openai", "https://api.stepfun.com/v1", "STEPFUN_API_KEY"),
    "hunyuan": ProviderPreset("Tencent Hunyuan", "openai", "https://api.hunyuan.tencentyun.com/v1", "HUNYUAN_API_KEY"),
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
}


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def die(message: str, code: int = 1) -> "NoReturn":
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
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
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
    context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
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


def explicitly_free(item: dict[str, Any]) -> bool:
    model_id = str(item.get("id", "")).lower().strip()
    if model_id == "openrouter/free" or model_id.endswith(":free") or "/free" in model_id:
        return True
    if item.get("is_free") is True or item.get("free") is True:
        return True
    pricing = item.get("pricing")
    if isinstance(pricing, dict):
        charge_fields = [
            pricing.get("prompt"), pricing.get("completion"), pricing.get("request"),
            pricing.get("image"), pricing.get("input"), pricing.get("output"),
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
    items: list[dict[str, Any]], base_url: str, env_key: str,
    timeout_ms: int, max_retries: int, context_window: int | None,
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
            providers[key] = [v for v in value if isinstance(v, dict) and isinstance(v.get("id"), str)]
            continue
        if isinstance(value, dict) and isinstance(value.get("models"), list):
            providers[key] = [v for v in value["models"] if isinstance(v, dict) and isinstance(v.get("id"), str)]
            repairs.append(f"converted wrapped modelProviders.{key}.models to an array")
            continue
        if isinstance(value, str):
            ids = [part.strip().strip('"') for part in value.split(",") if part.strip().strip('"')]
            if ids:
                providers[key] = [{"id": model_id, "name": display_name(model_id)} for model_id in ids]
                repairs.append(f"converted comma-separated modelProviders.{key} string to an array")
                continue
        providers[key] = []
        repairs.append(f"replaced invalid modelProviders.{key} with an empty array")
    return repairs


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
                errors.append(f"modelProviders.{protocol}[{index}].id must be a non-empty string")
            elif model_id in seen:
                errors.append(f"duplicate model id in {protocol}: {model_id}")
            else:
                seen.add(model_id)
            env_key = model.get("envKey")
            if env_key is not None and (not isinstance(env_key, str) or not re.match(r"^[A-Z_][A-Z0-9_]*$", env_key)):
                errors.append(f"invalid envKey for {protocol}:{model_id}")
    model = settings.get("model", {})
    if model and not isinstance(model, dict):
        errors.append("model must be an object")
    return errors


def choose_default_model(configs: list[dict[str, Any]], requested: str | None) -> str:
    ids = [str(m["id"]) for m in configs if isinstance(m, dict) and m.get("id") is not None]
    if requested:
        if requested not in ids:
            die(f"default model '{requested}' is not in discovered/configured model list")
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
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL") or (preset.base_url if preset else None)
    env_key = args.env_key or (preset.env_key if preset else "OPENAI_API_KEY")
    protocol = args.protocol or (preset.protocol if preset else "openai")
    if not base_url:
        die("provide --provider or --base-url")
    base_url = normalize_url(base_url)
    api_key = args.api_key or os.environ.get(env_key, "")

    if args.models:
        model_items = [{"id": x.strip()} for x in args.models.split(",") if x.strip()]
    else:
        if not api_key and not args.allow_unauthenticated:
            die(f"environment variable {env_key} is unset; export it or pass --api-key")
        payload = request_json(models_url(base_url), api_key, args.timeout, args.insecure)
        model_items = extract_model_objects(payload)

    if args.free:
        filtered_free = [item for item in model_items if explicitly_free(item)]
        if not filtered_free and args.provider == "openrouter":
            filtered_free = [{"id": m} for m in KNOWN_FREE_MODELS]
        if not filtered_free:
            die("no explicitly free models found; refusing to label accessible paid models as free")
        model_items = filtered_free
    if args.filter_model:
        pattern = re.compile(args.filter_model, re.IGNORECASE)
        model_items = [item for item in model_items if pattern.search(str(item.get("id", "")))]
    if args.include_regex:
        pattern = re.compile(args.include_regex, re.IGNORECASE)
        model_items = [item for item in model_items if pattern.search(str(item.get("id", "")))]
    if args.exclude_regex:
        pattern = re.compile(args.exclude_regex, re.IGNORECASE)
        model_items = [item for item in model_items if not pattern.search(str(item.get("id", "")))]
    if args.coder_only:
        coder_pattern = re.compile(r"code|coder|qwen.*code|deepseek.*coder|starcoder|codellama|dev", re.IGNORECASE)
        model_items = [item for item in model_items if coder_pattern.search(str(item.get("id", "")))]
    if args.min_context:
        filtered: list[dict[str, Any]] = []
        for item in model_items:
            ctx = item.get("context_length") or item.get("context_window") or item.get("max_tokens")
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
        model_items, base_url, env_key, args.request_timeout_ms,
        args.max_retries, args.context_window,
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


def command_providers(args: argparse.Namespace) -> int:
    query = args.query.lower() if args.query else None
    print("Available Provider Presets:")
    print("-" * 80)
    fmt = "{:<16} {:<24} {:<32} {:<20}"
    print(fmt.format("KEY", "NAME", "BASE URL", "ENV KEY"))
    print("-" * 80)
    for key, p in sorted(PRESETS.items()):
        if query and query not in key and query not in p.name.lower() and query not in p.base_url.lower():
            continue
        print(fmt.format(key, p.name[:24], p.base_url[:32], p.env_key))
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
            print("node version:", subprocess.check_output([node, "--version"], text=True).strip())
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
    import shlex

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
        else:
            die(
                "Cannot auto-detect backend. "
                "Set DASHSCOPE_API_KEY / OPENROUTER_API_KEY / SILICONFLOW_API_KEY, "
                "or install Ollama, or pass --backend explicitly."
            )

    print(f"Qwen Omega ProMeta {VERSION} — Qwen Coder Installer")
    print(f"Backend : {backend}")

    # ── Select model ───────────────────────────────────────────────────────
    catalog = CODER_CATALOG.get(backend, [])
    if not model:
        if backend == "ollama":
            ram_gb = _detect_ram_gb()
            if   ram_gb >= 40: model = catalog[0]   # 32b
            elif ram_gb >= 20: model = catalog[1]   # 14b
            elif ram_gb >= 10: model = catalog[2]   # 7b
            elif ram_gb >=  5: model = catalog[3]   # 3b
            else:               model = catalog[4]  # 1.5b
            print(f"RAM     : {ram_gb}GB → {model}")
        elif catalog:
            model = catalog[0]
        else:
            die(f"No default model catalog for backend '{backend}'. Pass --model.")

    print(f"Model   : {model}")

    # ── Validate API key availability ──────────────────────────────────────
    key_map = {
        "dashscope":   "DASHSCOPE_API_KEY",
        "openrouter":  "OPENROUTER_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
    }
    if backend in key_map and not os.environ.get(key_map[backend]):
        die(f"{key_map[backend]} is not set")

    # ── Build generate args namespace ──────────────────────────────────────
    provider_map = {
        "ollama":      "ollama",
        "dashscope":   "dashscope",
        "openrouter":  "openrouter",
        "siliconflow": "siliconflow",
    }
    provider = provider_map.get(backend)
    if provider is None:
        die(f"Unsupported backend: {backend}")

    preset = PRESETS[provider]
    base_url = preset.base_url
    env_key  = preset.env_key
    api_key  = os.environ.get(env_key, "")

    # For Ollama, skip live discovery — use catalog directly
    if backend == "ollama":
        model_items: list[dict[str, Any]] = [{"id": m} for m in (catalog if not model else [model])]
        # Always include selected model first
        if model not in [m["id"] for m in model_items]:
            model_items.insert(0, {"id": model})
    elif backend in ("dashscope", "siliconflow"):
        # Use catalog; avoid live API call
        model_items = [{"id": m} for m in catalog]
    else:
        # openrouter: discover live, then filter to coder + optional :free
        if not api_key:
            # Fall back to known-free catalog
            model_items = [{"id": m} for m in catalog]
        else:
            payload = request_json(
                models_url(base_url), api_key,
                DEFAULT_TIMEOUT, insecure=False,
            )
            model_items = extract_model_objects(payload)
            coder_pat = re.compile(r"code|coder", re.IGNORECASE)
            model_items = [it for it in model_items if coder_pat.search(str(it.get("id", "")))]
            if free_only:
                model_items = [it for it in model_items if explicitly_free(it)] or [
                    {"id": m} for m in catalog
                ]

    if not model_items:
        die("No models available after filtering")

    settings_path = pathlib.Path(args.settings).expanduser()
    configs = to_model_configs(
        model_items, base_url, env_key,
        120_000, 3, None,
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
            eprint(f"WARNING: ollama pull {model} failed. Run manually: ollama pull {model}")

    print("Done. Run: qwen")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qwen-omega", description="Generate and validate production-grade Qwen Code configuration")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="discover models and generate settings.json")
    gen.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    gen.add_argument("--provider", choices=sorted(PRESETS))
    gen.add_argument("--protocol", default=None, help="Qwen provider protocol key; default openai")
    gen.add_argument("--base-url")
    gen.add_argument("--env-key")
    gen.add_argument("--api-key", help="used only for discovery; never persisted")
    gen.add_argument("--models", help="comma-separated model IDs; skips API discovery")
    gen.add_argument("--default-model")
    gen.add_argument("--free", action="store_true", help="include only models explicitly marked zero-cost/free")
    gen.add_argument("--filter-model", help="regex pattern to filter models by ID")
    gen.add_argument("--include-regex", help="alias for --filter-model")
    gen.add_argument("--exclude-regex", help="regex pattern to exclude matching models")
    gen.add_argument("--coder-only", action="store_true", help="filter for code/coder models")
    gen.add_argument("--min-context", type=int, help="minimum context window length requirement")
    gen.add_argument("--limit", type=int)
    gen.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    gen.add_argument("--request-timeout-ms", type=int, default=120000)
    gen.add_argument("--max-retries", type=int, default=3)
    gen.add_argument("--context-window", type=int)
    gen.add_argument("--max-session-turns", type=int, default=-1)
    gen.add_argument("--approval-mode", choices=("plan", "default", "auto-edit", "auto", "yolo"), default="default")
    gen.add_argument("--allow-unauthenticated", action="store_true")
    gen.add_argument("--insecure", action="store_true", help="disable TLS verification; local testing only")
    gen.add_argument("--no-backup", action="store_true")
    gen.add_argument("--dry-run", action="store_true")
    gen.set_defaults(func=command_generate)

    val = sub.add_parser("validate", help="validate current settings schema")
    val.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    val.set_defaults(func=command_validate)

    repair = sub.add_parser("repair", help="repair string/wrapped legacy modelProviders")
    repair.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    repair.add_argument("--dry-run", action="store_true")
    repair.set_defaults(func=command_repair)

    doctor = sub.add_parser("doctor", help="inspect installation and validate settings")
    doctor.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    doctor.set_defaults(func=command_doctor)

    prov = sub.add_parser("providers", help="list supported provider URLs, names, and environment keys")
    prov.add_argument("--query", "-q", help="search filter for provider key/name/URL")
    prov.set_defaults(func=command_providers)

    ic = sub.add_parser(
        "install-coder",
        help="one-shot Qwen Coder setup: detect backend, select model, generate settings",
    )
    ic.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    ic.add_argument(
        "--backend",
        choices=("auto", "ollama", "dashscope", "openrouter", "siliconflow"),
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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
