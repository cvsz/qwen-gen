import unittest
import json
from pathlib import Path


COMPOSE_FILE = Path(__file__).resolve().parent / "docker-compose.fullstack.yml"
LITELLM_CONFIG = Path(__file__).resolve().parent / "litellm-config.yaml"


class TestOpenWebUIRuntime(unittest.TestCase):
    def test_public_openwebui_runtime_is_proxy_safe(self):
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        service = compose.split("  open-webui:\n", 1)[1].split(
            "\n  nextchat:", 1
        )[0]

        self.assertIn("network_mode: " + "$" + "{QWEN_STACK_NETWORK_MODE:-host}", service)
        self.assertIn(
            "WEBUI_URL: http://127.0.0.1:" + "$" + "{OPENWEBUI_HOST_PORT:-3011}",
            service,
        )
        self.assertIn("PORT: " + "$" + "{OPENWEBUI_HOST_PORT:-3011}", service)
        self.assertIn(
            "OPENAI_API_BASE_URL: "
            + "$"
            + "{QWEN_LITELLM_BASE_URL:-http://127.0.0.1:4000/v1}",
            service,
        )
        self.assertIn('ENABLE_WEBSOCKET_SUPPORT: "false"', service)

    def test_nextchat_owns_public_chat_host_port_and_litellm_backend(self):
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        service = compose.split("  nextchat:\n", 1)[1].split(
            "\n  qwen-gen:", 1
        )[0]

        self.assertIn("network_mode: " + "$" + "{QWEN_STACK_NETWORK_MODE:-host}", service)
        self.assertIn("PORT: " + "$" + "{NEXTCHAT_HOST_PORT:-3000}", service)
        self.assertIn("HOSTNAME: 127.0.0.1", service)
        self.assertIn(
            "BASE_URL: " + "$" + "{NEXTCHAT_BASE_URL:-http://127.0.0.1:4000/v1}",
            service,
        )
        self.assertIn(
            "DEFAULT_MODEL: " + "$" + "{NEXTCHAT_DEFAULT_MODEL:-zCoder:latest}",
            service,
        )
        self.assertIn(
            "CUSTOM_MODELS: "
            + "$"
            + "{NEXTCHAT_CUSTOM_MODELS:-zCoder:latest,qwen2.5-coder}",
            service,
        )

    def test_zcoder_is_exposed_through_litellm(self):
        config = json.loads(LITELLM_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(
            [route["model_name"] for route in config["model_list"]],
            ["zCoder:latest", "qwen2.5-coder"],
        )
        route = next(
            item for item in config["model_list"] if item["model_name"] == "zCoder:latest"
        )
        self.assertEqual(route["litellm_params"]["model"], "ollama/zCoder:latest")
        self.assertEqual(
            route["litellm_params"]["api_base"], "http://host.docker.internal:11434"
        )


if __name__ == "__main__":
    unittest.main()
