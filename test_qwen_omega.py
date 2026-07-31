#!/usr/bin/env python3
import argparse
import pathlib
import sys
import tempfile
import unittest
import unittest.mock

# Support both installed package and running from source tree
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import qwen_omega as qo  # noqa: E402


class TestQwenOmega(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = pathlib.Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_normalize_url(self):
        self.assertEqual(
            qo.normalize_url("https://api.openai.com/v1/"), "https://api.openai.com/v1"
        )
        self.assertEqual(
            qo.normalize_url("http://localhost:11434"), "http://localhost:11434"
        )
        with unittest.mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                qo.normalize_url("ftp://example.com")

    def test_models_url(self):
        self.assertEqual(
            qo.models_url("https://api.openai.com/v1"),
            "https://api.openai.com/v1/models",
        )
        self.assertEqual(
            qo.models_url("https://api.openai.com"), "https://api.openai.com/v1/models"
        )

    def test_extract_model_objects(self):
        payload = {"data": [{"id": "model-1"}, {"name": "model-2"}, "model-3"]}
        extracted = qo.extract_model_objects(payload)
        self.assertEqual(len(extracted), 3)
        self.assertEqual(extracted[0]["id"], "model-1")
        self.assertEqual(extracted[1]["id"], "model-2")
        self.assertEqual(extracted[2]["id"], "model-3")

    def test_explicitly_free(self):
        self.assertTrue(qo.explicitly_free({"id": "openrouter/free"}))
        self.assertTrue(qo.explicitly_free({"id": "foo:free"}))
        self.assertTrue(
            qo.explicitly_free(
                {"id": "foo", "pricing": {"prompt": "0", "completion": 0}}
            )
        )
        self.assertFalse(
            qo.explicitly_free(
                {"id": "foo", "pricing": {"prompt": "0.001", "completion": "0"}}
            )
        )

    def test_validate_settings(self):
        valid = {
            "$version": 4,
            "modelProviders": {
                "openai": [
                    {
                        "id": "m1",
                        "name": "m1",
                        "baseUrl": "http://localhost",
                        "envKey": "API_KEY",
                    }
                ]
            },
        }
        self.assertEqual(qo.validate_settings(valid), [])

        invalid_version = dict(valid, **{"$version": 3})
        self.assertIn("$version must be 4", qo.validate_settings(invalid_version))

        duplicate_model = {
            "$version": 4,
            "modelProviders": {
                "openai": [
                    {"id": "m1", "envKey": "KEY1"},
                    {"id": "m1", "envKey": "KEY2"},
                ]
            },
        }
        errors = qo.validate_settings(duplicate_model)
        self.assertTrue(any("duplicate model id" in e for e in errors))

    def test_normalize_existing_providers(self):
        settings = {
            "modelProviders": {
                "p1": [{"id": "m1"}],
                "p2": {"models": [{"id": "m2"}]},
                "p3": '"m3", "m4"',
                "p4": 12345,
            }
        }
        repairs = qo.normalize_existing_providers(settings)
        self.assertEqual(len(repairs), 3)
        self.assertEqual(settings["modelProviders"]["p1"], [{"id": "m1"}])
        self.assertEqual(settings["modelProviders"]["p2"], [{"id": "m2"}])
        self.assertEqual(
            settings["modelProviders"]["p3"],
            [{"id": "m3", "name": "m3"}, {"id": "m4", "name": "m4"}],
        )
        self.assertEqual(settings["modelProviders"]["p4"], [])

    def test_choose_default_model(self):
        configs = [{"id": "gpt-4o"}, {"id": "qwen3-coder:latest"}]
        self.assertEqual(qo.choose_default_model(configs, None), "qwen3-coder:latest")
        self.assertEqual(qo.choose_default_model(configs, "gpt-4o"), "gpt-4o")
        with unittest.mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                qo.choose_default_model(configs, "non-existent")

    def test_filter_model(self):
        items = [
            {"id": "qwen3-coder:latest"},
            {"id": "gpt-4o"},
            {"id": "deepseek-coder"},
        ]
        pattern = argparse.Namespace(
            filter_model="coder",
            include_regex=None,
            exclude_regex=None,
            free=False,
            coder_only=False,
            min_context=None,
            limit=None,
        )
        import re

        pat = re.compile(pattern.filter_model, re.IGNORECASE)
        filtered = [x for x in items if pat.search(x["id"])]
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["id"], "qwen3-coder:latest")
        self.assertEqual(filtered[1]["id"], "deepseek-coder")

    def test_dry_run_generate_without_api_key(self):
        args = argparse.Namespace(
            provider="ollama",
            base_url=None,
            env_key=None,
            protocol=None,
            models=None,
            api_key=None,
            allow_unauthenticated=False,
            timeout=30,
            insecure=False,
            free=False,
            filter_model=None,
            include_regex=None,
            exclude_regex=None,
            coder_only=False,
            min_context=None,
            limit=None,
            request_timeout_ms=120000,
            max_retries=3,
            context_window=None,
            default_model="qwen3-coder:latest",
            approval_mode="default",
            max_session_turns=-1,
            settings=str(self.tmp_path / "settings.json"),
            dry_run=True,
            no_backup=False,
        )
        with unittest.mock.patch("sys.stdout"):
            res = qo.command_generate(args)
            self.assertEqual(res, 0)


if __name__ == "__main__":
    unittest.main()
