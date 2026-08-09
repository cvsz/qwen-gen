#!/usr/bin/env python3
"""Tests for the free-model catalog used by LiteLLM/Open WebUI."""

import unittest

from free_model_catalog import (
    build_litellm_config,
    is_chat_capable_model,
    retain_validated_routes,
    select_free_chat_models,
)


class FreeModelCatalogTests(unittest.TestCase):
    def test_select_free_chat_models_excludes_paid_and_non_chat_media(self):
        items = [
            {
                "id": "chat-model:free",
                "type": "chat",
                "pricing": {"prompt": "0", "completion": "0"},
            },
            {
                "id": "video-model:free",
                "type": "video",
                "pricing": {"prompt": "0", "completion": "0"},
            },
            {
                "id": "paid-chat",
                "type": "chat",
                "pricing": {"prompt": "0.1", "completion": "0.2"},
            },
        ]

        selected = select_free_chat_models(items)

        self.assertEqual([item["id"] for item in selected], ["chat-model:free"])

    def test_chat_capability_rejects_audio_output(self):
        self.assertFalse(
            is_chat_capable_model(
                {
                    "id": "music-model",
                    "architecture": {
                        "input_modalities": ["text"],
                        "output_modalities": ["text", "audio"],
                    },
                }
            )
        )

    def test_build_litellm_config_preserves_local_and_names_provider_routes(self):
        existing = {
            "model_list": [
                {
                    "model_name": "qwen2.5-coder",
                    "litellm_params": {
                        "model": "ollama/qwen2.5-coder:7b-instruct-q4_K_M",
                        "api_base": "http://host.docker.internal:11434",
                    },
                }
            ]
        }
        free_models = [
            {
                "provider_key": "openrouter",
                "model_id": "openrouter/free",
                "base_url": "https://openrouter.ai/api/v1",
                "env_key": "OPENROUTER_API_KEY",
            },
            {
                "provider_key": "together",
                "model_id": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
                "base_url": "https://api.together.xyz/v1",
                "env_key": "TOGETHER_API_KEY",
            },
            {
                "provider_key": "openrouter",
                "model_id": "openrouter/free",
                "base_url": "https://openrouter.ai/api/v1",
                "env_key": "OPENROUTER_API_KEY",
            },
        ]

        config = build_litellm_config(free_models, existing)
        routes = config["model_list"]
        names = [route["model_name"] for route in routes]

        self.assertEqual(names[0], "qwen2.5-coder")
        self.assertEqual(
            names[1:],
            [
                "free/openrouter/openrouter/free",
                "free/together/Qwen/Qwen3-Coder-30B-A3B-Instruct",
            ],
        )
        self.assertEqual(
            routes[1]["litellm_params"],
            {
                "model": "openai/openrouter/free",
                "api_base": "https://openrouter.ai/api/v1",
                "api_key": "os.environ/OPENROUTER_API_KEY",
            },
        )

    def test_retain_validated_routes_matches_direct_and_aliased_models(self):
        config = {
            "model_list": [
                {
                    "model_name": "zCoder:latest",
                    "litellm_params": {"model": "ollama/zCoder:latest"},
                },
                {
                    "model_name": "qwen2.5-coder",
                    "litellm_params": {
                        "model": "ollama/qwen2.5-coder:7b-instruct-q4_K_M"
                    },
                },
                {
                    "model_name": "free/openrouter/no-quota",
                    "litellm_params": {
                        "model": "openai/no-quota:free"
                    },
                },
            ]
        }

        filtered = retain_validated_routes(
            config,
            ["zCoder:latest", "qwen2.5-coder:7b-instruct-q4_K_M"],
        )

        self.assertEqual(
            [route["model_name"] for route in filtered["model_list"]],
            ["zCoder:latest", "qwen2.5-coder"],
        )


if __name__ == "__main__":
    unittest.main()
