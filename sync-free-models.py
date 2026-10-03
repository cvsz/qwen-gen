#!/usr/bin/env python3
"""Sync every discovered free provider chat model into LiteLLM."""

from __future__ import annotations

import argparse
import collections
import pathlib

from free_model_catalog import (
    build_litellm_config,
    discover_free_model_routes,
    load_litellm_config,
    render_litellm_yaml,
    write_litellm_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover provider-declared free chat models for LiteLLM/Open WebUI."
    )
    parser.add_argument(
        "--config",
        default="litellm-config.yaml",
        help="LiteLLM config to update",
    )
    parser.add_argument(
        "--env-root",
        default=str(pathlib.Path(__file__).resolve().parent),
        help="Directory containing .env.ai and provider environment files",
    )
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--include-local", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = pathlib.Path(args.config).expanduser()
    env_root = pathlib.Path(args.env_root).expanduser()
    routes = discover_free_model_routes(
        env_root,
        timeout=max(1, args.timeout),
        include_local=args.include_local,
    )
    current = load_litellm_config(config_path)
    updated = build_litellm_config(routes, current)

    counts = collections.Counter(str(route["provider_key"]) for route in routes)
    print(f"Discovered free chat routes: {len(routes)}")
    for provider, count in sorted(counts.items()):
        print(f"  {provider}: {count}")
    if args.dry_run:
        print(render_litellm_yaml(updated), end="")
        return 0

    write_litellm_config(config_path, updated)
    print(f"Updated LiteLLM config: {config_path}")
    print(f"LiteLLM routes: {len(updated.get('model_list', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
