#!/usr/bin/env python3
"""Discover provider-declared free chat models and build LiteLLM routes."""

from __future__ import annotations

import copy
import json
import pathlib
import re
from typing import Any, Iterable

import qwen_omega as qo


MEDIA_TYPES = {
    "audio",
    "embedding",
    "image",
    "moderation",
    "rerank",
    "speech",
    "transcribe",
    "tts",
    "video",
}
MEDIA_OUTPUTS = {"audio", "image", "video"}


def _modality_tokens(value: Any) -> set[str]:
    if isinstance(value, list):
        values = value
    elif value is None:
        values = []
    else:
        values = re.split(r"[^a-z0-9]+", str(value).lower())
    return {str(item).strip().lower() for item in values if str(item).strip()}


def is_chat_capable_model(item: dict[str, Any]) -> bool:
    """Return whether a provider model can return text for a chat request."""

    model_type = str(item.get("type") or "").strip().lower()
    if model_type in MEDIA_TYPES:
        return False

    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        outputs = _modality_tokens(architecture.get("output_modalities"))
        if outputs and ("text" not in outputs or outputs & MEDIA_OUTPUTS):
            return False

    # Providers use different type vocabularies. Unknown types are retained when
    # their metadata does not explicitly identify a non-chat modality.
    return True


def select_free_chat_models(
    items: Iterable[dict[str, Any]],
    *,
    local: bool = False,
    hinted_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Keep unique, chat-capable models that are explicitly free.

    Local catalog entries and explicit operator hints are trusted because local
    model APIs generally do not publish pricing metadata.
    """

    hints = {str(model_id).strip() for model_id in hinted_ids if str(model_id).strip()}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("name") or "").strip()
        if not model_id or model_id in seen:
            continue
        if not local and model_id not in hints and not qo.explicitly_free(item):
            continue
        if not is_chat_capable_model(item):
            continue
        copied = dict(item)
        copied["id"] = model_id
        selected.append(copied)
        seen.add(model_id)
    return selected


def discover_free_model_routes(
    env_root: pathlib.Path,
    *,
    timeout: int = qo.DEFAULT_TIMEOUT,
    include_local: bool = False,
) -> list[dict[str, Any]]:
    """Discover free model metadata and attach the provider route it needs."""

    env = qo.read_env_files(env_root)
    routes: list[dict[str, Any]] = []
    for provider_key, preset in sorted(qo.PRESETS.items()):
        local = provider_key in qo.LOCAL_FREE_CATALOG_PROVIDERS
        if local and not include_local:
            continue
        if not qo.provider_enabled(provider_key, preset, env):
            continue

        # Do not synthesize a cloud provider's paid coder catalog when its
        # /models endpoint is unavailable. Explicit free metadata or an
        # operator-provided *_FREE_MODEL hint is required for cloud routes.
        model_items = qo.build_free_model_items(
            provider_key,
            preset,
            env,
            timeout,
            False,
            False,
        )
        hint_key = qo.FREE_MODEL_HINT_ENV.get(provider_key)
        hinted_ids = [env[hint_key]] if hint_key and env.get(hint_key, "").strip() else []
        selected = select_free_chat_models(
            model_items,
            local=local,
            hinted_ids=hinted_ids,
        )
        if not selected:
            continue

        base_url = qo.normalize_url(
            env.get(qo.BASE_URL_HINT_ENV.get(provider_key, ""), preset.base_url)
        )
        for item in selected:
            routes.append(
                {
                    "provider_key": provider_key,
                    "provider_name": preset.name,
                    "model_id": item["id"],
                    "base_url": base_url,
                    "env_key": preset.env_key,
                    "is_local": local,
                }
            )
    return routes


def retain_validated_routes(
    config: dict[str, Any], validated_model_ids: Iterable[str]
) -> dict[str, Any]:
    """Keep only LiteLLM routes whose alias or upstream model was probed.

    A provider catalog can contain models that are free in metadata but have
    no current quota or valid credentials. Runtime clients must not advertise
    those entries. The probe may see the upstream model ID while LiteLLM
    exposes a shorter alias, so both the route name and the provider-stripped
    ``litellm_params.model`` are accepted as identities.
    """

    allowed = {
        str(model_id).strip()
        for model_id in validated_model_ids
        if str(model_id).strip()
    }
    filtered = copy.deepcopy(config)
    current = config.get("model_list")
    if not isinstance(current, list):
        filtered["model_list"] = []
        return filtered

    def matches(route: Any) -> bool:
        if not isinstance(route, dict):
            return False
        route_name = str(route.get("model_name") or "").strip()
        params = route.get("litellm_params")
        upstream = params.get("model") if isinstance(params, dict) else ""
        identities = {route_name, str(upstream or "").strip()}
        for identity in tuple(identities):
            if not identity:
                continue
            identities.add(identity.split("/", 1)[1] if "/" in identity else identity)
        return bool(identities & allowed)

    filtered["model_list"] = [route for route in current if matches(route)]
    return filtered


def build_litellm_config(
    free_models: Iterable[dict[str, Any]],
    existing_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replace generated ``free/`` routes while preserving the base config."""

    config = copy.deepcopy(existing_config) if existing_config else {}
    current = config.get("model_list")
    current_routes = current if isinstance(current, list) else []
    retained_routes = [
        route
        for route in current_routes
        if not (
            isinstance(route, dict)
            and str(route.get("model_name") or "").startswith("free/")
        )
    ]

    routes = list(retained_routes)
    seen_names = {
        str(route.get("model_name"))
        for route in routes
        if isinstance(route, dict) and route.get("model_name")
    }
    for item in free_models:
        provider_key = str(item.get("provider_key") or "").strip()
        model_id = str(item.get("model_id") or "").strip()
        base_url = str(item.get("base_url") or "").strip().rstrip("/")
        env_key = str(item.get("env_key") or "").strip()
        if not provider_key or not model_id or not base_url:
            continue
        model_name = f"free/{provider_key}/{model_id}"
        if model_name in seen_names:
            continue
        route = {
            "model_name": model_name,
            "litellm_params": {
                # The OpenAI adapter keeps provider model IDs unchanged while
                # allowing every OpenAI-compatible upstream to share one route.
                "model": f"openai/{model_id}",
                "api_base": base_url,
            },
        }
        if env_key:
            route["litellm_params"]["api_key"] = f"os.environ/{env_key}"
        routes.append(route)
        seen_names.add(model_name)

    config["model_list"] = routes
    return config


def render_litellm_yaml(config: dict[str, Any]) -> str:
    """Render the small LiteLLM config as JSON, which is valid YAML."""

    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def load_litellm_config(path: pathlib.Path) -> dict[str, Any]:
    """Load a JSON/YAML LiteLLM config without adding a runtime dependency."""

    raw = path.read_text(encoding="utf-8") if path.exists() else "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore[import-not-found]

            payload = yaml.safe_load(raw)
        except ImportError as exc:
            raise RuntimeError(
                "PyYAML is required to read an existing non-JSON LiteLLM config"
            ) from exc
    if not isinstance(payload, dict):
        raise ValueError("LiteLLM config must contain a mapping at the top level")
    return payload


def write_litellm_config(path: pathlib.Path, config: dict[str, Any]) -> None:
    """Atomically write a LiteLLM config file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(render_litellm_yaml(config), encoding="utf-8")
    temporary.replace(path)
