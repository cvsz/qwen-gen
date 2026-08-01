#!/usr/bin/env python3
import argparse
import http.server
import json
import io
import os
import pathlib
import sys
import tempfile
import time
import unittest
import unittest.mock
import threading
import urllib.request
from contextlib import redirect_stdout

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
            "agents": [
                {
                    "id": "mentor",
                    "name": "Mentor",
                    "baseModel": "qwen3-coder:latest",
                    "systemPrompt": "Be concise.",
                }
            ],
            "skills": [
                {
                    "id": "planning",
                    "name": "Planning",
                    "content": "Help organize work.",
                }
            ],
            "memories": [
                {
                    "id": "prefs",
                    "title": "Preferences",
                    "content": "Prefer concise answers.",
                    "scope": "user",
                }
            ],
            "folders": [
                {
                    "id": "project-alpha",
                    "name": "Project Alpha",
                    "systemPrompt": "Be concise and project-aware.",
                    "knowledge": ["docs"],
                }
            ],
            "webhooks": [
                {
                    "id": "ops-alerts",
                    "name": "Ops Alerts",
                    "url": "http://127.0.0.1:9000/webhook",
                    "events": ["chat.created"],
                }
            ],
            "security": {
                "auth": {
                    "selectedType": "openai",
                    "adminEmails": [
                        "cvsitem@gmail.com",
                        "seaza@msn.com",
                        "sea@zeaz.dev",
                    ],
                }
            },
            "files": [
                {
                    "id": "handoff",
                    "name": "Handoff",
                    "content": "This is the handoff file.",
                }
            ],
            "notes": [
                {
                    "id": "review",
                    "title": "Review",
                    "body": "Check the diff for regressions.",
                    "files": ["handoff"],
                    "images": ["preview.png"],
                }
            ],
            "conversations": [
                {
                    "id": "planning",
                    "title": "Planning",
                    "transcript": "assistant: Plan the release.",
                    "folderId": "project-alpha",
                    "images": ["screenshot.png"],
                }
            ],
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

        duplicate_agent = {
            "$version": 4,
            "modelProviders": valid["modelProviders"],
            "agents": [
                {"id": "mentor", "name": "Mentor", "baseModel": "qwen3-coder:latest"},
                {"id": "mentor", "name": "Duplicate", "baseModel": "qwen3-coder:latest"},
            ],
        }
        self.assertTrue(any("duplicate agent id" in e for e in qo.validate_settings(duplicate_agent)))

        duplicate_skill = {
            "$version": 4,
            "modelProviders": valid["modelProviders"],
            "skills": [
                {"id": "planning", "name": "Planning", "content": "Help organize work."},
                {"id": "planning", "name": "Duplicate", "content": "Duplicate."},
            ],
        }
        self.assertTrue(any("duplicate skill id" in e for e in qo.validate_settings(duplicate_skill)))

        duplicate_file = {
            "$version": 4,
            "modelProviders": valid["modelProviders"],
            "files": [
                {"id": "handoff", "name": "Handoff", "content": "This is the handoff file."},
                {"id": "handoff", "name": "Duplicate", "content": "Duplicate."},
            ],
        }
        self.assertTrue(any("duplicate file id" in e for e in qo.validate_settings(duplicate_file)))

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

    def test_help_command(self):
        parser = qo.build_parser()
        args = parser.parse_args(["help"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("Generate and validate production-grade Qwen Code configuration", buf.getvalue())

    def test_providers_add_all(self):
        settings_path = self.tmp_path / "settings.json"
        settings_path.write_text(
            """
            {
              "$version": 4,
              "modelProviders": {
                "openai": [
                  {
                    "id": "existing-model",
                    "name": "existing model",
                    "baseUrl": "http://localhost/v1",
                    "envKey": "EXISTING_KEY",
                    "generationConfig": {
                      "timeout": 120000,
                      "maxRetries": 3
                    }
                  }
                ]
              }
            }
            """.strip(),
            encoding="utf-8",
        )
        parser = qo.build_parser()
        args = parser.parse_args(["providers", "add", "all", "--settings", str(settings_path)])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        updated = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["$version"], 4)
        self.assertIn("openai", updated["modelProviders"])
        self.assertGreaterEqual(
            len(updated["modelProviders"]["openai"]),
            1 + len(qo.PRESETS),
        )
        self.assertTrue(
            any(item["id"] == "openrouter-provider" for item in updated["modelProviders"]["openai"])
        )
        self.assertEqual(
            updated["security"]["auth"]["adminEmails"],
            ["cvsitem@gmail.com", "seaza@msn.com", "sea@zeaz.dev"],
        )

    def test_read_env_files(self):
        env_root = self.tmp_path / "envs"
        env_root.mkdir()
        (env_root / ".env").write_text(
            "\n".join(
                [
                    "OPENROUTER_API_KEY=test-key",
                    "OPENROUTER_FREE_MODEL=openrouter/free",
                    "NEXTCHAT_BASE_URL=http://127.0.0.1:3000/api/openai/v1",
                    "OPEN_WEBUI_BASE_URL=http://127.0.0.1:8080/v1",
                ]
            ),
            encoding="utf-8",
        )
        values = qo.read_env_files(env_root)
        self.assertEqual(values["OPENROUTER_API_KEY"], "test-key")
        self.assertEqual(values["OPENROUTER_FREE_MODEL"], "openrouter/free")
        self.assertEqual(
            values["NEXTCHAT_BASE_URL"], "http://127.0.0.1:3000/api/openai/v1"
        )
        self.assertEqual(values["OPEN_WEBUI_BASE_URL"], "http://127.0.0.1:8080/v1")

    def test_providers_add_free_from_env(self):
        env_root = self.tmp_path / "envs"
        env_root.mkdir()
        (env_root / ".env").write_text(
            "\n".join(
                [
                    "OPENROUTER_API_KEY=test-key",
                    "OPENROUTER_FREE_MODEL=openrouter/free",
                    "GROQ_API_KEY=test-key",
                    "GROQ_FREE_MODEL=openai/gpt-oss-20b",
                ]
            ),
            encoding="utf-8",
        )
        settings_path = self.tmp_path / "settings-free.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "providers",
                "add",
                "all",
                "--free",
                "--auto-fallback",
                "--env-root",
                str(env_root),
                "--settings",
                str(settings_path),
                "--dry-run",
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        updated = json.loads(buf.getvalue())
        openai_models = updated["modelProviders"]["openai"]
        self.assertTrue(any(item["id"] == "openrouter/free" for item in openai_models))
        self.assertTrue(any(item["id"] == "openai/gpt-oss-20b" for item in openai_models))
        self.assertTrue(any(item["id"] == "qwen3-coder:latest" for item in openai_models))

    def test_install_coder_auto_detects_nextchat_from_base_url(self):
        args = argparse.Namespace(
            settings=str(self.tmp_path / "settings-nextchat.json"),
            backend="auto",
            model="",
            free=True,
            approval_mode="default",
            dry_run=True,
        )
        buf = io.StringIO()
        with unittest.mock.patch.dict(
            os.environ,
            {"NEXTCHAT_BASE_URL": "http://127.0.0.1:3000/api/openai/v1"},
            clear=False,
        ):
            with unittest.mock.patch("shutil.which", return_value=None):
                with redirect_stdout(buf):
                    self.assertEqual(qo.command_install_coder(args), 0)
        self.assertIn("Backend : nextchat", buf.getvalue())
        text = buf.getvalue()
        payload = json.loads(text[text.index("{") :])
        self.assertEqual(payload["security"]["auth"]["selectedType"], "openai")
        self.assertEqual(
            payload["security"]["auth"]["adminEmails"],
            ["cvsitem@gmail.com", "seaza@msn.com", "sea@zeaz.dev"],
        )
        self.assertEqual(
            payload["modelProviders"]["openai"][0]["baseUrl"],
            "http://127.0.0.1:3000/api/openai/v1",
        )

    def test_serve_command_exposes_models_and_chat(self):
        upstream_requests = []

        class UpstreamHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0") or "0")
                body = json.loads(self.rfile.read(length))
                upstream_requests.append(body)
                response = {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": body["model"],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 7,
                        "total_tokens": 19,
                    },
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": f"echo: {body['messages'][-1]['content']}",
                            },
                        }
                    ],
                }
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        self.addCleanup(upstream.shutdown)
        self.addCleanup(upstream.server_close)

        knowledge_source_dir = self.tmp_path / "docs"
        knowledge_source_dir.mkdir()
        knowledge_source_file = knowledge_source_dir / "release.md"
        knowledge_source_file.write_text(
            "This release adds provider controls and workspace support.",
            encoding="utf-8",
        )
        docs_index = qo.build_knowledge_index("docs", knowledge_source_dir, 2000, 200)

        settings_path = self.tmp_path / "serve-settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "model": {"name": "qwen3-coder:latest"},
                    "modelProviders": {
                        "openai": [
                            {
                                "id": "qwen3-coder:latest",
                                "name": "Qwen 3 Coder",
                                "baseUrl": f"http://127.0.0.1:{upstream.server_address[1]}/v1",
                                "envKey": "TEST_API_KEY",
                            },
                            {
                                "id": "qwen3-coder:mini",
                                "name": "Qwen 3 Coder Mini",
                                "baseUrl": f"http://127.0.0.1:{upstream.server_address[1]}/v1",
                                "envKey": "TEST_API_KEY",
                            }
                        ]
                    },
                    "promptTemplates": [
                        {
                            "id": "review",
                            "name": "Review",
                            "content": "Review this code for bugs.",
                        }
                    ],
                    "folders": [
                        {
                            "id": "project-alpha",
                            "name": "Project Alpha",
                            "systemPrompt": "Be concise and project-aware.",
                        }
                    ],
                    "knowledgeBases": [
                        {
                            "id": "docs",
                            "name": "Docs",
                            "sourceDir": str(knowledge_source_dir),
                        }
                    ],
                    "agents": [
                        {
                            "id": "mentor",
                            "name": "Mentor",
                            "baseModel": "qwen3-coder:latest",
                            "systemPrompt": "Be concise.",
                            "description": "Helpful coding mentor.",
                            "tools": ["browser"],
                            "knowledge": ["docs"],
                            "skills": ["planning"],
                        }
                    ],
                    "skills": [
                        {
                            "id": "planning",
                            "name": "Planning",
                            "content": "Organize work before implementation.",
                            "description": "A simple planning skill.",
                            "tags": ["workflow"],
                        }
                    ],
                    "memories": [
                        {
                            "id": "preferences",
                            "title": "Preferences",
                            "content": "Prefer concise answers.",
                            "scope": "user",
                            "tags": ["style"],
                        }
                    ],
                    "knowledgeIndexes": [
                        docs_index,
                    ],
                    "notes": [
                        {
                            "id": "review",
                            "title": "Review",
                            "body": "Check the diff for regressions.",
                            "files": ["handoff"],
                            "images": ["preview.png"],
                        }
                    ],
                    "artifacts": [
                        {
                            "id": "release-notes",
                            "title": "Release Notes",
                            "content": "Release notes content.",
                            "kind": "markdown",
                        }
                    ],
                    "toolServers": [
                        {
                            "id": "search",
                            "name": "Search",
                            "type": "mcp",
                            "endpoint": "http://127.0.0.1:3001/mcp",
                        }
                    ],
                    "webhooks": [
                        {
                            "id": "ops-alerts",
                            "name": "Ops Alerts",
                            "url": "https://example.com/webhook",
                            "events": ["chat.created"],
                            "description": "Alerts for new chats.",
                        }
                    ],
                    "files": [
                        {
                            "id": "handoff",
                            "name": "Handoff",
                            "kind": "markdown",
                            "content": "Ship this feature with caution.",
                        }
                    ],
                    "conversations": [
                        {
                            "id": "planning",
                            "title": "Planning",
                            "transcript": "assistant: Plan the release.",
                            "folderId": "project-alpha",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        server = qo.QwenChatHTTPServer(("127.0.0.1", 0), qo.QwenChatRequestHandler)
        server.state = qo.QwenChatState.load(settings_path)  # type: ignore[attr-defined]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        models = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/models").read())
        self.assertEqual(models["object"], "list")
        self.assertTrue(any(item["id"] == "qwen3-coder:latest" for item in models["data"]))

        html = urllib.request.urlopen(f"{base_url}/ai.html").read().decode("utf-8")
        self.assertIn("Qwen Gen Chat", html)
        self.assertIn("bootstrap", html)
        self.assertIn("manifest.webmanifest", html)
        self.assertIn("serviceWorker.register", html)
        self.assertIn("Export MD", html)
        self.assertIn("Export JSON", html)
        self.assertIn("Export HTML", html)
        self.assertIn("ShareGPT", html)
        self.assertIn("Share Image", html)
        self.assertIn("Regenerate", html)
        self.assertIn("Stop", html)
        self.assertIn("toggle-sidebar", html)
        self.assertIn("Collapse sidebar", html)
        self.assertIn("sidebarCollapsed: localStorage.getItem('qwen-gen.chat.sidebarCollapsed') !== '0'", html)
        self.assertIn("theme-toggle", html)
        self.assertIn("Theme: Dark", html)
        self.assertIn("shortcuts-help", html)
        self.assertIn("Keyboard shortcuts", html)
        self.assertIn("dictate-button", html)
        self.assertIn("voice-status", html)
        self.assertIn("Read aloud", html)
        self.assertIn("status-pills", html)
        self.assertIn("Providers", html)
        self.assertIn("Add presets", html)
        self.assertIn("Refresh", html)
        self.assertIn("provider-chips", html)
        self.assertIn("Knowledge Bases", html)
        self.assertIn("kb-query", html)
        self.assertIn("new-kb", html)
        self.assertIn("edit-kb", html)
        self.assertIn("delete-kb", html)
        self.assertIn("kb-preview", html)
        self.assertIn("kb-editor-name", html)
        self.assertIn("kb-editor-source-dir", html)
        self.assertIn("kb-editor-description", html)
        self.assertIn("kb-editor-tags", html)
        self.assertIn("kb-save", html)
        self.assertIn("kb-cancel", html)
        self.assertIn("kb-import-file", html)
        self.assertIn("kb-import", html)
        self.assertIn("kb-export", html)
        self.assertIn("kb-output-dir", html)
        self.assertIn("kb-watch-iterations", html)
        self.assertIn("kb-watch-interval", html)
        self.assertIn("kb-sync", html)
        self.assertIn("kb-watch", html)
        self.assertIn("kb-results", html)
        self.assertIn("Web Search", html)
        self.assertIn("web-search-query", html)
        self.assertIn("web-search-run", html)
        self.assertIn("web-search-provider", html)
        self.assertIn("web-search-fallback", html)
        self.assertIn("web-search-engine-url", html)
        self.assertIn("web-search-api-key", html)
        self.assertIn("web-search-base-id", html)
        self.assertIn("web-search-name", html)
        self.assertIn("web-search-description", html)
        self.assertIn("web-search-save-limit", html)
        self.assertIn("web-search-save", html)
        self.assertIn("web-search-clear", html)
        self.assertIn("web-search-results", html)
        self.assertIn("Agents", html)
        self.assertIn("agent-select", html)
        self.assertIn("agent-chips", html)
        self.assertIn("new-agent", html)
        self.assertIn("edit-agent", html)
        self.assertIn("delete-agent", html)
        self.assertIn("agent-preview", html)
        self.assertIn("agent-editor-name", html)
        self.assertIn("agent-editor-base-model", html)
        self.assertIn("agent-editor-folder", html)
        self.assertIn("agent-editor-system-prompt", html)
        self.assertIn("agent-editor-tools", html)
        self.assertIn("agent-editor-knowledge", html)
        self.assertIn("agent-editor-skills", html)
        self.assertIn("agent-editor-avatar", html)
        self.assertIn("agent-editor-voice", html)
        self.assertIn("agent-editor-visibility", html)
        self.assertIn("agent-save", html)
        self.assertIn("agent-cancel", html)
        self.assertIn("agent-import-file", html)
        self.assertIn("agent-import", html)
        self.assertIn("agent-export", html)
        self.assertIn("agent-share-md", html)
        self.assertIn("agent-share-html", html)
        self.assertIn("agent-share-json", html)
        self.assertIn("agent-clone", html)
        self.assertIn("Skills", html)
        self.assertIn("skill-chips", html)
        self.assertIn("skill-preview", html)
        self.assertIn("Share MD", html)
        self.assertIn("Share HTML", html)
        self.assertIn("Share JSON", html)
        self.assertIn("edit-skill", html)
        self.assertIn("skill-editor-name", html)
        self.assertIn("skill-editor-content", html)
        self.assertIn("skill-editor-tags", html)
        self.assertIn("skill-save", html)
        self.assertIn("skill-cancel", html)
        self.assertIn("Memories", html)
        self.assertIn("memory-chips", html)
        self.assertIn("memory-preview", html)
        self.assertIn("edit-memory", html)
        self.assertIn("memory-editor-title", html)
        self.assertIn("memory-editor-content", html)
        self.assertIn("memory-editor-scope", html)
        self.assertIn("memory-save", html)
        self.assertIn("memory-cancel", html)
        self.assertIn("Notes", html)
        self.assertIn("note-chips", html)
        self.assertIn("note-preview", html)
        self.assertIn("edit-note", html)
        self.assertIn("note-editor-title", html)
        self.assertIn("note-editor-body", html)
        self.assertIn("note-save", html)
        self.assertIn("note-cancel", html)
        self.assertIn("Artifacts", html)
        self.assertIn("artifact-chips", html)
        self.assertIn("artifact-preview", html)
        self.assertIn("edit-artifact", html)
        self.assertIn("artifact-editor-title", html)
        self.assertIn("artifact-editor-content", html)
        self.assertIn("artifact-editor-kind", html)
        self.assertIn("artifact-editor-tags", html)
        self.assertIn("artifact-save", html)
        self.assertIn("artifact-cancel", html)
        self.assertIn("Tools", html)
        self.assertIn("new-tool", html)
        self.assertIn("delete-tool", html)
        self.assertIn("refresh-tools", html)
        self.assertIn("tool-chips", html)
        self.assertIn("tool-preview", html)
        self.assertIn("edit-tool", html)
        self.assertIn("tool-editor-name", html)
        self.assertIn("tool-editor-endpoint", html)
        self.assertIn("tool-editor-type", html)
        self.assertIn("tool-editor-description", html)
        self.assertIn("tool-editor-auth", html)
        self.assertIn("tool-save", html)
        self.assertIn("tool-cancel", html)
        self.assertIn("Webhooks", html)
        self.assertIn("new-webhook", html)
        self.assertIn("edit-webhook", html)
        self.assertIn("delete-webhook", html)
        self.assertIn("refresh-webhooks", html)
        self.assertIn("webhook-chips", html)
        self.assertIn("webhook-preview", html)
        self.assertIn("webhook-editor-name", html)
        self.assertIn("webhook-editor-url", html)
        self.assertIn("webhook-editor-events", html)
        self.assertIn("webhook-editor-description", html)
        self.assertIn("webhook-editor-secret", html)
        self.assertIn("webhook-save", html)
        self.assertIn("webhook-cancel", html)
        self.assertIn("Search chats", html)
        self.assertIn("Workspace overview", html)
        self.assertIn("Chat interface ready for use", html)
        self.assertIn("Ready-to-use local chat interface", html)
        self.assertIn("First load onboarding", html)
        self.assertIn("Set up your first workspace", html)
        self.assertIn("Recommended first steps", html)
        self.assertIn("Add provider presets", html)
        self.assertIn("0 models", html)
        self.assertIn("0 templates", html)
        self.assertIn("0 chats", html)
        self.assertIn("Open template gallery", html)
        self.assertIn("template-drawer", html)
        self.assertIn("Template gallery", html)
        self.assertIn("Search templates by name, tag, or content", html)
        self.assertIn("Compare", html)
        self.assertIn("Copy current", html)
        self.assertIn("Workspace", html)
        self.assertIn("folder-select", html)
        self.assertIn("New workspace name", html)
        self.assertIn("create-folder", html)
        self.assertIn("folder-chips", html)
        self.assertIn("Prompt templates", html)
        self.assertIn("Starter templates", html)
        self.assertIn("Unified workspace", html)
        self.assertIn("Find in chat", html)
        self.assertIn("message-search", html)
        self.assertIn("Upload files", html)
        self.assertIn("file-import-file", html)
        self.assertIn("file-import", html)
        self.assertIn("file-export", html)
        self.assertIn("file-clone", html)
        self.assertIn("file-upload", html)
        self.assertIn("file-search", html)
        self.assertIn("clear-file-search", html)
        self.assertIn("clear-file-attachments", html)
        self.assertIn("selected-file-chips", html)
        self.assertIn("selected-file-meta", html)
        self.assertIn("drag/paste files here to upload", html)
        self.assertIn("Compare models", html)
        self.assertIn("Enable compare mode", html)
        self.assertIn("Pin", html)
        self.assertIn("Archive", html)
        self.assertIn("Saved chats", html)
        self.assertIn("Ready for use", html)
        self.assertIn("chat-empty-presets", html)
        self.assertIn("chat-empty-templates", html)
        self.assertIn("chat-empty-files", html)
        self.assertIn("conversation-import-file", html)
        self.assertIn("conversation-import", html)
        self.assertIn("conversation-export", html)
        self.assertIn("conversation-share-md", html)
        self.assertIn("conversation-share-html", html)
        self.assertIn("conversation-clone", html)
        self.assertIn("conversation-filter-pinned", html)
        self.assertIn("conversation-filter-archived", html)
        self.assertIn("Delete file", html)
        self.assertIn("Preview file", html)
        self.assertIn("Share MD", html)
        self.assertIn("Share HTML", html)
        self.assertIn("Share JSON", html)
        self.assertIn("file-preview-backdrop", html)
        self.assertIn("queue-status", html)
        self.assertIn("No queued messages.", html)
        self.assertIn("streaming-status", html)
        self.assertIn("Generating response live.", html)
        self.assertIn("chat-usage", html)
        self.assertIn("Token estimate:", html)
        self.assertIn("copy-chat", html)
        self.assertIn("rename-chat", html)
        self.assertIn("Edit conversation title", html)
        self.assertIn("new-chat-header", html)
        self.assertIn("duplicate-chat", html)
        self.assertIn("toggle-chat-pin", html)
        self.assertIn("toggle-chat-archive", html)
        self.assertIn("delete-chat", html)
        self.assertIn("Save", html)
        self.assertIn("New", html)
        self.assertIn("template-name", html)
        self.assertIn("message-actions", html)
        self.assertIn("Copy", html)
        self.assertIn("Copy code", html)
        self.assertIn("Edit", html)
        self.assertIn("Fork", html)
        self.assertIn("Retry", html)
        self.assertIn("message-editor", html)
        self.assertIn("scroll-latest", html)
        self.assertIn("Latest", html)
        self.assertIn("typing-indicator", html)
        self.assertIn("Assistant is typing", html)
        self.assertIn("Edit template", html)
        self.assertIn("Clone", html)
        self.assertIn("Delete", html)
        self.assertIn("conversation-item-select", html)

        manifest = json.loads(urllib.request.urlopen(f"{base_url}/manifest.webmanifest").read())
        self.assertEqual(manifest["name"], "Qwen Gen Chat")
        self.assertEqual(manifest["scope"], "/")
        self.assertTrue(manifest["icons"])
        head_req = urllib.request.Request(f"{base_url}/manifest.webmanifest", method="HEAD")
        with urllib.request.urlopen(head_req) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "application/manifest+json")

        sw = urllib.request.urlopen(f"{base_url}/sw.js").read().decode("utf-8")
        self.assertIn("qwen-gen-chat-v2", sw)
        self.assertIn("self.addEventListener('fetch'", sw)
        head_req = urllib.request.Request(f"{base_url}/sw.js", method="HEAD")
        with urllib.request.urlopen(head_req) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "application/javascript")

        icon = urllib.request.urlopen(f"{base_url}/qwen-gen-icon.svg").read().decode("utf-8")
        self.assertIn("<svg", icon)
        self.assertIn("Qwen Gen", icon)
        head_req = urllib.request.Request(f"{base_url}/qwen-gen-icon.svg", method="HEAD")
        with urllib.request.urlopen(head_req) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "image/svg+xml")

        uploaded = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/files",
                    data=json.dumps(
                        {
                            "name": "upload.txt",
                            "content": "hello upload",
                            "kind": "text/plain",
                            "path": "upload.txt",
                            "description": "Test upload",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(uploaded["data"]["name"], "upload.txt")
        files = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/files").read())
        self.assertTrue(any(item["name"] == "upload.txt" for item in files["data"]))
        file_import = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/files",
                    data=json.dumps(
                        {
                            "action": "import",
                            "content": json.dumps(
                                {
                                    "files": [
                                        {
                                            "id": "browser-file",
                                            "name": "Browser File",
                                            "content": "Imported from browser.",
                                            "kind": "text/plain",
                                        }
                                    ]
                                }
                            ),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(any(item["id"] == "browser-file" for item in file_import["data"]["files"]))
        file_export = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/files",
                    data=json.dumps({"action": "export"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("browser-file", file_export["data"]["content"])
        file_clone = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/files",
                    data=json.dumps(
                        {
                            "action": "clone",
                            "id": uploaded["data"]["id"],
                            "newId": "upload-browser-copy",
                            "name": "Upload Browser Copy",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(file_clone["data"]["file"]["id"], "upload-browser-copy")
        shared_file = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/files",
                    data=json.dumps(
                        {
                            "action": "share",
                            "id": uploaded["data"]["id"],
                            "format": "html",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("upload.txt", shared_file["data"]["content"])
        delete_response = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/files",
                    data=json.dumps({"action": "delete", "id": uploaded["data"]["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(delete_response["deleted"], uploaded["data"]["id"])

        chat_response = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/chat",
                    data=json.dumps(
                        {
                            "conversationId": "demo-chat",
                            "title": "Demo chat",
                            "model": "qwen3-coder:latest",
                            "systemPrompt": "Be brief.",
                            "files": ["handoff"],
                            "messages": [{"role": "user", "content": "Hello"}],
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(chat_response["choices"][0]["message"]["content"], "echo: Hello")
        self.assertTrue(upstream_requests)
        self.assertEqual(upstream_requests[0]["model"], "qwen3-coder:latest")
        self.assertGreaterEqual(len(upstream_requests[0]["messages"]), 2)
        self.assertTrue(upstream_requests[0]["messages"][0]["content"].startswith("Attached files:"))
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        conversation = next(item for item in persisted["conversations"] if item["id"] == "demo-chat")
        self.assertEqual(conversation["title"], "Demo chat")
        self.assertEqual(conversation["systemPrompt"], "Be brief.")
        self.assertEqual(conversation["files"], ["handoff"])
        self.assertEqual(conversation["messages"][-1]["content"], "echo: Hello")
        self.assertEqual(conversation["usage"]["total_tokens"], 19)

        auto_title_response = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/chat",
                    data=json.dumps(
                        {
                            "conversationId": "auto-title-chat",
                            "model": "qwen3-coder:latest",
                            "messages": [
                                {"role": "user", "content": "plan terraform cloudflare for qwen.zeaz.dev"}
                            ],
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(auto_title_response["choices"][0]["message"]["content"], "echo: plan terraform cloudflare for qwen.zeaz.dev")
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        auto_title_conversation = next(item for item in persisted["conversations"] if item["id"] == "auto-title-chat")
        self.assertEqual(auto_title_conversation["title"], "Plan terraform cloudflare for qwen.zeaz.dev")

        compare_response = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/chat",
                    data=json.dumps(
                        {
                            "conversationId": "compare-chat",
                            "title": "Compare chat",
                            "model": "qwen3-coder:latest",
                            "models": ["qwen3-coder:latest", "qwen3-coder:mini"],
                            "messages": [{"role": "user", "content": "Compare these"}],
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("qwen3-coder:latest", compare_response["choices"][0]["message"]["content"])
        self.assertIn("qwen3-coder:mini", compare_response["choices"][0]["message"]["content"])
        self.assertEqual(len(compare_response["comparison"]), 2)
        self.assertEqual(compare_response["comparison"][0]["model"], "qwen3-coder:latest")
        self.assertEqual(compare_response["comparison"][1]["model"], "qwen3-coder:mini")
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        compare_conversation = next(item for item in persisted["conversations"] if item["id"] == "compare-chat")
        self.assertEqual(compare_conversation["compareModels"], ["qwen3-coder:mini"])

        fallback_settings = {
            "modelProviders": {
                "openai": [
                    {
                        "id": "qwen3-coder:latest",
                        "baseUrl": "http://127.0.0.1:11434/v1",
                    },
                    {
                        "id": "deepseek-coder:latest",
                        "baseUrl": "http://127.0.0.1:11434/v1",
                    },
                ]
            }
        }

        def fake_single(settings, model_id, messages, payload, insecure=False):
            if model_id == "qwen3-coder:latest":
                raise qo.RequestError(
                    "HTTP 404 from http://127.0.0.1:11434/v1/chat/completions: {\"error\":{\"message\":\"model 'qwen3-coder:latest' not found\"}}"
                )
            self.assertEqual(model_id, "deepseek-coder:latest")
            return {
                "id": "chatcmpl-fallback",
                "object": "chat.completion",
                "created": 123,
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "echo: fallback"},
                        "finish_reason": "stop",
                    }
                ],
                "provider": "openai",
                "providerName": "OpenAI",
            }

        with unittest.mock.patch.object(qo, "_CHAT_COMPLETION_SINGLE", side_effect=fake_single):
            fallback_response = qo._chat_completion(
                fallback_settings,
                "qwen3-coder:latest",
                [{"role": "user", "content": "fallback"}],
                {},
            )
        self.assertEqual(fallback_response["model"], "deepseek-coder:latest")
        self.assertEqual(fallback_response["choices"][0]["message"]["content"], "echo: fallback")

        state_response = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/conversations",
                    data=json.dumps(
                        {
                            "id": "state-chat",
                            "title": "State chat",
                            "model": "qwen3-coder:latest",
                            "folderId": "project-alpha",
                            "pinned": True,
                            "archived": True,
                            "messages": [{"role": "user", "content": "Hello"}],
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(state_response["data"]["pinned"], True)
        self.assertEqual(state_response["data"]["archived"], True)
        self.assertEqual(state_response["data"]["folderId"], "project-alpha")
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        state_conversation = next(item for item in persisted["conversations"] if item["id"] == "state-chat")
        self.assertEqual(state_conversation["pinned"], True)
        self.assertEqual(state_conversation["archived"], True)
        self.assertEqual(state_conversation["folderId"], "project-alpha")

        folder_response = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/folders",
                    data=json.dumps(
                        {
                            "id": "project-beta",
                            "name": "Project Beta",
                            "systemPrompt": "Be direct.",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(folder_response["data"]["id"], "project-beta")
        folder_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/folders").read())
        self.assertTrue(any(item["id"] == "project-beta" for item in folder_list["data"]))
        folder_delete = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/folders",
                    data=json.dumps({"action": "delete", "id": "project-beta"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(folder_delete["deleted"], "project-beta")
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertFalse(any(item["id"] == "project-beta" for item in persisted["folders"]))

        conversation_import = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/conversations",
                    data=json.dumps(
                        {
                            "action": "import",
                            "content": json.dumps(
                                {
                                    "conversations": [
                                        {
                                            "id": "browser-import",
                                            "title": "Browser Import",
                                            "transcript": "assistant: Imported from the browser.",
                                        }
                                    ]
                                }
                            ),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(
            any(item["id"] == "browser-import" for item in conversation_import["data"]["conversations"])
        )
        conversation_export = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/conversations",
                    data=json.dumps({"action": "export"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("browser-import", conversation_export["data"]["content"])
        conversation_share_md = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/conversations",
                    data=json.dumps({"action": "share", "id": "planning", "format": "md"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("assistant: Plan the release.", conversation_share_md["data"]["content"])
        conversation_share_html = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/conversations",
                    data=json.dumps({"action": "share", "id": "planning", "format": "html"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("data-conversation-id=\"planning\"", conversation_share_html["data"]["content"])
        conversation_clone = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/conversations",
                    data=json.dumps(
                        {
                            "action": "clone",
                            "id": "planning",
                            "newId": "planning-browser-copy",
                            "title": "Planning Browser Copy",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(conversation_clone["data"]["conversation"]["id"], "planning-browser-copy")

        agent_import = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/agents",
                    data=json.dumps(
                        {
                            "action": "import",
                            "content": json.dumps(
                                {
                                    "agents": [
                                        {
                                            "id": "browser-agent",
                                            "name": "Browser Agent",
                                            "baseModel": "qwen3-coder:latest",
                                            "systemPrompt": "Assist from the browser.",
                                        }
                                    ]
                                }
                            ),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(any(item["id"] == "browser-agent" for item in agent_import["data"]["agents"]))
        agent_export = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/agents",
                    data=json.dumps({"action": "export"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("browser-agent", agent_export["data"]["content"])
        agent_share_json = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/agents",
                    data=json.dumps({"action": "share", "id": "mentor", "format": "json"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(agent_share_json["data"]["id"], "mentor")
        self.assertEqual(agent_share_json["data"]["format"], "json")
        agent_clone = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/agents",
                    data=json.dumps(
                        {
                            "action": "clone",
                            "id": "mentor",
                            "newId": "mentor-browser-copy",
                            "name": "Mentor Browser Copy",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(agent_clone["data"]["agent"]["id"], "mentor-browser-copy")

        kb_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/kb").read())
        self.assertTrue(any(item["id"] == "docs" for item in kb_list["data"]["knowledgeBases"]))
        self.assertTrue(any(item["id"] == "docs-index" for item in kb_list["data"]["knowledgeIndexes"]))
        imported_kb = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb",
                    data=json.dumps(
                        {
                            "action": "import",
                            "content": json.dumps(
                                {
                                    "knowledgeBases": [
                                        {
                                            "id": "imported-docs",
                                            "name": "Imported Docs",
                                            "sourceDir": "/tmp/imported-docs",
                                        }
                                    ],
                                    "knowledgeIndexes": [
                                        {
                                            "id": "imported-docs-index",
                                            "baseId": "imported-docs",
                                            "path": "/tmp/imported-docs/index.json",
                                            "sourceDir": "/tmp/imported-docs",
                                            "documentCount": 1,
                                            "chunkCount": 1,
                                            "documents": [],
                                        }
                                    ],
                                }
                            ),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(any(item["id"] == "imported-docs" for item in imported_kb["data"]["knowledgeBases"]))
        self.assertTrue(
            any(item["id"] == "imported-docs-index" for item in imported_kb["data"]["knowledgeIndexes"])
        )
        exported_kb = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb",
                    data=json.dumps({"action": "export"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("Imported Docs", exported_kb["data"]["content"])
        web_search_meta = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/web-search").read())
        self.assertTrue(any(item["id"] == "duckduckgo" for item in web_search_meta["data"]["providers"]))
        self.assertEqual(web_search_meta["data"]["defaultProvider"], "duckduckgo")
        web_search_results = [
            {
                "title": "Release Notes",
                "url": "http://example.test/release",
                "snippet": "Version 1.2 ships today.",
            },
            {
                "title": "Documentation",
                "url": "http://example.test/docs",
                "snippet": "Read the setup guide.",
            },
        ]
        web_search_docs = {
            "http://example.test/release": {
                "id": "release-notes",
                "name": "Release Notes",
                "content": "Release Notes Version 1.2 ships today.",
                "path": "http://example.test/release",
                "kind": "html",
                "description": "Fetched from http://example.test/release",
                "size": 123,
            },
            "http://example.test/docs": {
                "id": "documentation",
                "name": "Documentation",
                "content": "Documentation Read the setup guide.",
                "path": "http://example.test/docs",
                "kind": "html",
                "description": "Fetched from http://example.test/docs",
                "size": 123,
            },
        }
        with unittest.mock.patch(
            "qwen_omega.fetch_web_search_results_chain",
            return_value=web_search_results,
        ), unittest.mock.patch(
            "qwen_omega.fetch_web_document",
            side_effect=lambda url, timeout: web_search_docs[url],
        ):
            web_search_response = json.loads(
                urllib.request.urlopen(
                    urllib.request.Request(
                        f"{base_url}/api/ai/web-search",
                        data=json.dumps(
                            {
                                "query": "release",
                                "provider": "duckduckgo",
                            }
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                ).read()
            )
            self.assertEqual(web_search_response["data"][0]["title"], "Release Notes")
            saved_web_search = json.loads(
                urllib.request.urlopen(
                    urllib.request.Request(
                        f"{base_url}/api/ai/web-search",
                        data=json.dumps(
                            {
                                "action": "save",
                                "query": "release",
                                "provider": "duckduckgo",
                                "baseId": "search-release",
                                "knowledgeName": "Search Release",
                                "description": "Saved from browser search.",
                                "saveLimit": 2,
                            }
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                ).read()
            )
        self.assertEqual(saved_web_search["data"]["knowledgeIndex"]["baseId"], "search-release")
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "search-release" for item in persisted["knowledgeBases"]))
        self.assertTrue(any(item["baseId"] == "search-release" for item in persisted["knowledgeIndexes"]))
        kb_query = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb/query",
                    data=json.dumps({"query": "provider controls"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(kb_query["data"])
        self.assertEqual(kb_query["data"][0]["baseId"], "docs")
        self.assertIn("provider controls", kb_query["data"][0]["snippet"])
        kb_query_empty = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb/query",
                    data=json.dumps({"query": "does-not-match"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(kb_query_empty["data"], [])

        knowledge_source_file.write_text(
            "This release adds browser refresh support for knowledge bases.",
            encoding="utf-8",
        )
        refreshed_kb = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb",
                    data=json.dumps({"action": "refresh", "baseId": "docs"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(refreshed_kb["data"]["knowledgeBase"]["id"], "docs")
        self.assertEqual(refreshed_kb["data"]["knowledgeIndex"]["baseId"], "docs")
        sync_output_dir = self.tmp_path / "browser-kb-sync"
        synced_kb = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb",
                    data=json.dumps(
                        {
                            "action": "sync",
                            "baseId": "docs",
                            "outputDir": str(sync_output_dir),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("docs", synced_kb["data"]["refreshed"])
        self.assertTrue((sync_output_dir / "docs.json").exists())
        self.assertTrue((sync_output_dir / "manifest.json").exists())
        knowledge_source_file.write_text(
            "# Release Notes\nUpdated watch content with browser sync.\n",
            encoding="utf-8",
        )
        watch_output_dir = self.tmp_path / "browser-kb-watch"
        watched_kb = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb",
                    data=json.dumps(
                        {
                            "action": "watch",
                            "baseId": "docs",
                            "iterations": 2,
                            "interval": 0.1,
                            "outputDir": str(watch_output_dir),
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("docs", watched_kb["data"]["refreshed"])
        watched_index = json.loads((watch_output_dir / "docs.json").read_text(encoding="utf-8"))
        self.assertIn("Updated watch content with browser sync", watched_index["documents"][0]["chunks"][0]["text"])
        self.assertTrue((watch_output_dir / "manifest.json").exists())
        refreshed_query = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb/query",
                    data=json.dumps({"query": "browser refresh"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(refreshed_query["data"])
        self.assertIn("Updated watch content with browser sync", refreshed_query["data"][0]["snippet"])

        kb_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/kb").read())
        self.assertTrue(any(item["id"] == "docs" for item in kb_list["data"]["knowledgeBases"]))
        saved_kb = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb",
                    data=json.dumps(
                        {
                            "name": "Browser KB",
                            "sourceDir": "/tmp/browser-kb",
                            "description": "Browser-created knowledge base.",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(saved_kb["data"]["name"], "Browser KB")
        deleted_kb = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/kb",
                    data=json.dumps({"action": "delete", "id": saved_kb["data"]["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(deleted_kb["deleted"], saved_kb["data"]["id"])

        tools_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/tools").read())
        self.assertTrue(any(item["id"] == "search" for item in tools_list["data"]))
        saved_tool = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/tools",
                    data=json.dumps(
                        {
                            "name": "Browser Tool",
                            "endpoint": "http://127.0.0.1:3001/mcp",
                            "type": "mcp",
                            "description": "Browser-created tool server.",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(saved_tool["data"]["name"], "Browser Tool")
        deleted_tool = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/tools",
                    data=json.dumps({"action": "delete", "id": saved_tool["data"]["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(deleted_tool["deleted"], saved_tool["data"]["id"])

        agents_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/agents").read())
        self.assertTrue(any(item["id"] == "mentor" for item in agents_list["data"]))
        saved_agent = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/agents",
                    data=json.dumps(
                        {
                            "name": "Browser Agent",
                            "baseModel": "qwen3-coder:latest",
                            "systemPrompt": "Be concise.",
                            "folderId": "project-alpha",
                            "tools": ["browser-tool"],
                            "knowledge": ["kb-1"],
                            "skills": ["planning"],
                            "avatar": "https://example.com/avatar.png",
                            "voice": "echo",
                            "visibility": "private",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(saved_agent["data"]["name"], "Browser Agent")
        self.assertEqual(saved_agent["data"]["folderId"], "project-alpha")
        self.assertEqual(saved_agent["data"]["tools"], ["browser-tool"])
        self.assertEqual(saved_agent["data"]["knowledge"], ["kb-1"])
        self.assertEqual(saved_agent["data"]["skills"], ["planning"])
        self.assertEqual(saved_agent["data"]["avatar"], "https://example.com/avatar.png")
        self.assertEqual(saved_agent["data"]["voice"], "echo")
        self.assertEqual(saved_agent["data"]["visibility"], "private")
        deleted_agent = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/agents",
                    data=json.dumps({"action": "delete", "id": saved_agent["data"]["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(deleted_agent["deleted"], saved_agent["data"]["id"])

        skills_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/skills").read())
        self.assertTrue(any(item["id"] == "planning" for item in skills_list["data"]))
        webhooks_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/webhooks").read())
        self.assertTrue(any(item["id"] == "ops-alerts" for item in webhooks_list["data"]))
        saved_webhook = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/webhooks",
                    data=json.dumps(
                        {
                            "name": "Browser Webhook",
                            "url": "https://example.com/browser",
                            "events": ["chat.created"],
                            "description": "Browser-created target.",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(saved_webhook["data"]["name"], "Browser Webhook")
        deleted_webhook = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/webhooks",
                    data=json.dumps({"action": "delete", "id": saved_webhook["data"]["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(deleted_webhook["deleted"], saved_webhook["data"]["id"])
        memories_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/memories").read())
        self.assertTrue(any(item["id"] == "preferences" for item in memories_list["data"]))
        saved_memory = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/memories",
                    data=json.dumps(
                        {
                            "title": "Browser Memory",
                            "content": "Prefer to use the sidebar.",
                            "scope": "user",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(saved_memory["data"]["title"], "Browser Memory")
        deleted_memory = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/memories",
                    data=json.dumps({"action": "delete", "id": saved_memory["data"]["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(deleted_memory["deleted"], saved_memory["data"]["id"])
        saved_skill = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/skills",
                    data=json.dumps(
                        {
                            "name": "Browser Skill",
                            "content": "Use this from the sidebar.",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(saved_skill["data"]["name"], "Browser Skill")
        shared_skill = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/skills",
                    data=json.dumps(
                        {
                            "action": "share",
                            "id": saved_skill["data"]["id"],
                            "format": "md",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertIn("Browser Skill", shared_skill["data"]["content"])
        self.assertIn("Use this from the sidebar.", shared_skill["data"]["content"])
        deleted_skill = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/skills",
                    data=json.dumps({"action": "delete", "id": saved_skill["data"]["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(deleted_skill["deleted"], saved_skill["data"]["id"])

        notes_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/notes").read())
        self.assertTrue(any(item["id"] == "review" for item in notes_list["data"]))
        saved_note = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/notes",
                    data=json.dumps(
                        {
                            "title": "Browser Note",
                            "body": "Use this in the sidebar.",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(saved_note["data"]["title"], "Browser Note")
        deleted_note = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/notes",
                    data=json.dumps({"action": "delete", "id": saved_note["data"]["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(deleted_note["deleted"], saved_note["data"]["id"])
        artifacts_list = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/artifacts").read())
        self.assertTrue(any(item["id"] == "release-notes" for item in artifacts_list["data"]))
        saved_artifact = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/artifacts",
                    data=json.dumps(
                        {
                            "title": "Browser Artifact",
                            "content": "Artifact content from the browser.",
                            "kind": "markdown",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(saved_artifact["data"]["title"], "Browser Artifact")
        deleted_artifact = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/artifacts",
                    data=json.dumps({"action": "delete", "id": saved_artifact["data"]["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(deleted_artifact["deleted"], saved_artifact["data"]["id"])

        providers_response = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/providers",
                    data=json.dumps({"action": "add-presets"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(providers_response["ok"])
        self.assertIn("openai", providers_response["data"])
        provider_models = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/models").read())
        self.assertTrue(any(item["id"] == "openrouter-provider" for item in provider_models["data"]))
        provider_delete = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/providers",
                    data=json.dumps({"action": "delete-model", "id": "openrouter-provider"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(provider_delete["ok"])
        refreshed_models = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/models").read())
        self.assertFalse(any(item["id"] == "openrouter-provider" for item in refreshed_models["data"]))

        sort_path = self.tmp_path / "sort-settings.json"
        sort_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "model": {"name": "qwen3-coder:latest"},
                    "modelProviders": {
                        "openai": [
                            {
                                "id": "qwen3-coder:latest",
                                "name": "Qwen 3 Coder",
                                "baseUrl": f"http://127.0.0.1:{upstream.server_address[1]}/v1",
                                "envKey": "TEST_API_KEY",
                            }
                        ]
                    },
                    "conversations": [
                        {"id": "zeta", "title": "Zeta", "transcript": "assistant: zeta"},
                        {"id": "alpha", "title": "Alpha", "transcript": "assistant: alpha", "pinned": True},
                        {"id": "beta", "title": "Beta", "transcript": "assistant: beta", "archived": True},
                    ],
                }
            ),
            encoding="utf-8",
        )
        server = qo.QwenChatHTTPServer(("127.0.0.1", 0), qo.QwenChatRequestHandler)
        server.state = qo.QwenChatState.load(sort_path)  # type: ignore[attr-defined]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        base_url_sort = f"http://127.0.0.1:{server.server_address[1]}"
        html_sort = urllib.request.urlopen(f"{base_url_sort}/ai.html").read().decode("utf-8")
        self.assertIn("conversation-filter-all", html_sort)
        self.assertIn("conversation-filter-pinned", html_sort)
        self.assertIn("conversation-filter-archived", html_sort)
        self.assertLess(html_sort.find("Alpha"), html_sort.find("Zeta"))

    def test_serve_state_delete_conversation(self):
        settings_path = self.tmp_path / "delete-settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "conversations": [
                        {"id": "keep", "title": "Keep"},
                        {"id": "remove", "title": "Remove"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        state = qo.QwenChatState.load(settings_path)
        state.delete_conversation("remove")
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "keep" for item in saved["conversations"]))
        self.assertFalse(any(item["id"] == "remove" for item in saved["conversations"]))

    def test_serve_state_prompt_template_upsert_and_delete(self):
        settings_path = self.tmp_path / "templates-settings.json"
        settings_path.write_text(json.dumps({"$version": 4, "promptTemplates": []}), encoding="utf-8")
        state = qo.QwenChatState.load(settings_path)
        saved = state.upsert_prompt_template(
            {
                "name": "Code Review",
                "content": "Review this diff for bugs.",
                "tags": ["review"],
            }
        )
        self.assertEqual(saved["name"], "Code Review")
        self.assertEqual(saved["content"], "Review this diff for bugs.")
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == saved["id"] for item in persisted["promptTemplates"]))
        state.delete_prompt_template(saved["id"])
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertFalse(any(item["id"] == saved["id"] for item in persisted["promptTemplates"]))

    def test_serve_state_folder_upsert_and_delete(self):
        settings_path = self.tmp_path / "folders-settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "folders": [],
                    "conversations": [
                        {"id": "demo", "title": "Demo", "folderId": "project-alpha"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        state = qo.QwenChatState.load(settings_path)
        saved = state.upsert_folder(
            {
                "name": "Project Alpha",
                "systemPrompt": "Be concise.",
                "description": "Primary workspace.",
            }
        )
        self.assertEqual(saved["name"], "Project Alpha")
        self.assertTrue(saved["id"])
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == saved["id"] for item in persisted["folders"]))
        state.delete_folder(saved["id"])
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertFalse(any(item["id"] == saved["id"] for item in persisted["folders"]))
        self.assertEqual(persisted["conversations"][0].get("folderId", ""), "")

    def test_serve_api_folder_roundtrip(self):
        settings_path = self.tmp_path / "folder-api-settings.json"
        settings_path.write_text(json.dumps({"$version": 4, "folders": []}), encoding="utf-8")
        server = qo.QwenChatHTTPServer(("127.0.0.1", 0), qo.QwenChatRequestHandler)
        server.state = qo.QwenChatState.load(settings_path)  # type: ignore[attr-defined]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        created = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/folders",
                    data=json.dumps(
                        {
                            "name": "Workspace One",
                            "systemPrompt": "Use short answers.",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        folder = created["data"]
        self.assertEqual(folder["name"], "Workspace One")
        listed = json.loads(urllib.request.urlopen(f"{base_url}/api/ai/folders").read())
        self.assertTrue(any(item["id"] == folder["id"] for item in listed["data"]))
        deleted = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/folders",
                    data=json.dumps({"action": "delete", "id": folder["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(deleted["ok"])
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertFalse(any(item["id"] == folder["id"] for item in persisted["folders"]))

    def test_serve_state_provider_preset_add_and_delete(self):
        settings_path = self.tmp_path / "providers-settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "modelProviders": {
                        "openai": [
                            {
                                "id": "keep-model",
                                "name": "Keep Model",
                                "baseUrl": "http://localhost/v1",
                                "envKey": "KEEP_KEY",
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        state = qo.QwenChatState.load(settings_path)
        added = state.add_provider_presets()
        self.assertIn("openrouter", added)
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "openrouter-provider" for item in persisted["modelProviders"]["openai"]))
        self.assertTrue(state.delete_provider_model("openrouter-provider"))
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertFalse(any(item["id"] == "openrouter-provider" for item in persisted["modelProviders"]["openai"]))

    def test_serve_api_prompt_template_roundtrip(self):
        settings_path = self.tmp_path / "prompt-api-settings.json"
        settings_path.write_text(json.dumps({"$version": 4, "promptTemplates": []}), encoding="utf-8")
        server = qo.QwenChatHTTPServer(("127.0.0.1", 0), qo.QwenChatRequestHandler)
        server.state = qo.QwenChatState.load(settings_path)  # type: ignore[attr-defined]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        created = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/prompt-templates",
                    data=json.dumps(
                        {
                            "name": "Code Review",
                            "content": "Review this diff for bugs.",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        template = created["data"]
        self.assertEqual(template["name"], "Code Review")
        self.assertEqual(template["content"], "Review this diff for bugs.")

        deleted = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/prompt-templates",
                    data=json.dumps({"action": "delete", "id": template["id"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertTrue(deleted["ok"])
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertFalse(any(item["id"] == template["id"] for item in persisted["promptTemplates"]))

    def test_serve_api_prompt_template_update_existing(self):
        settings_path = self.tmp_path / "prompt-api-update-settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "promptTemplates": [
                        {"id": "review", "name": "Review", "content": "Old text."}
                    ],
                }
            ),
            encoding="utf-8",
        )
        server = qo.QwenChatHTTPServer(("127.0.0.1", 0), qo.QwenChatRequestHandler)
        server.state = qo.QwenChatState.load(settings_path)  # type: ignore[attr-defined]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        updated = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base_url}/api/ai/prompt-templates",
                    data=json.dumps(
                        {"id": "review", "name": "Review", "content": "New text."}
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            ).read()
        )
        self.assertEqual(updated["data"]["id"], "review")
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["promptTemplates"][0]["content"], "New text.")

    def test_serve_command_streams_chat(self):
        upstream_requests = []

        class UpstreamHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0") or "0")
                body = json.loads(self.rfile.read(length))
                upstream_requests.append(body)
                if body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    for piece in ("echo: ", body["messages"][-1]["content"]):
                        chunk = {
                            "id": "chatcmpl-test",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": body["model"],
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": piece},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        data = f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                        self.wfile.write(data)
                        self.wfile.flush()
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    self.close_connection = True
                    return
                response = {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": f"echo: {body['messages'][-1]['content']}",
                            },
                        }
                    ],
                }
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        self.addCleanup(upstream.shutdown)
        self.addCleanup(upstream.server_close)

        settings_path = self.tmp_path / "serve-stream-settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "model": {"name": "qwen3-coder:latest"},
                    "modelProviders": {
                        "openai": [
                            {
                                "id": "qwen3-coder:latest",
                                "name": "Qwen 3 Coder",
                                "baseUrl": f"http://127.0.0.1:{upstream.server_address[1]}/v1",
                                "envKey": "TEST_API_KEY",
                            }
                        ]
                    },
                    "conversations": [],
                }
            ),
            encoding="utf-8",
        )

        server = qo.QwenChatHTTPServer(("127.0.0.1", 0), qo.QwenChatRequestHandler)
        server.state = qo.QwenChatState.load(settings_path)  # type: ignore[attr-defined]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        response = urllib.request.urlopen(
            urllib.request.Request(
                f"{base_url}/api/ai/chat",
                data=json.dumps(
                    {
                        "conversationId": "stream-chat",
                        "title": "Stream chat",
                        "model": "qwen3-coder:latest",
                        "stream": True,
                        "messages": [{"role": "user", "content": "Hello"}],
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        )
        body = response.read().decode("utf-8")
        self.assertIn('"type": "delta"', body)
        self.assertIn('"content": "echo: "', body)
        self.assertIn('"type": "done"', body)
        self.assertTrue(upstream_requests)
        self.assertTrue(upstream_requests[0]["stream"])
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        conversation = next(item for item in persisted["conversations"] if item["id"] == "stream-chat")
        self.assertEqual(conversation["messages"][-1]["content"], "echo: Hello")

    def test_prompts_add_and_list(self):
        settings_path = self.tmp_path / "prompts.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "prompts",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Code Review",
                "--content",
                "Review this diff for bugs.",
                "--tag",
                "review",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("promptTemplates", saved)
        self.assertEqual(saved["promptTemplates"][0]["id"], "code-review")
        self.assertEqual(saved["promptTemplates"][0]["name"], "Code Review")
        self.assertEqual(saved["promptTemplates"][0]["content"], "Review this diff for bugs.")

    def test_prompts_clone(self):
        settings_path = self.tmp_path / "prompts-clone.json"
        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "promptTemplates": [
                        {
                            "id": "code-review",
                            "name": "Code Review",
                            "content": "Review this diff for bugs.",
                            "description": "Review checklist",
                            "tags": ["review"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "prompts",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "code-review",
                "--new-id",
                "code-review-copy",
                "--name",
                "Code Review Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["promptTemplates"]), 2)
        clone = next(
            item for item in saved["promptTemplates"] if item["id"] == "code-review-copy"
        )
        self.assertEqual(clone["name"], "Code Review Copy")
        self.assertEqual(clone["content"], "Review this diff for bugs.")
        self.assertEqual(clone["description"], "Review checklist")
        self.assertEqual(clone["tags"], ["review"])

    def test_prompts_import_markdown(self):
        source_dir = self.tmp_path / "prompts"
        source_dir.mkdir()
        (source_dir / "review.md").write_text(
            "# Review\nCheck the code for regressions.\n",
            encoding="utf-8",
        )
        settings_path = self.tmp_path / "prompts-import.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "prompts",
                "import",
                "--settings",
                str(settings_path),
                str(source_dir),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["promptTemplates"]), 1)
        self.assertEqual(saved["promptTemplates"][0]["id"], "review")
        self.assertEqual(saved["promptTemplates"][0]["name"], "Review")

    def test_prompts_export(self):
        settings_path = self.tmp_path / "prompts-export.json"
        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "promptTemplates": [
                        {
                            "id": "review",
                            "name": "Review",
                            "content": "Review this diff.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        out_path = self.tmp_path / "export.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "prompts",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(exported["promptTemplates"][0]["id"], "review")

    def test_skills_add_import_export_share(self):
        settings_path = self.tmp_path / "skills.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "skills",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Planning",
                "--content",
                "Help organize the work.",
                "--tag",
                "workflow",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("skills", saved)
        self.assertEqual(saved["skills"][0]["id"], "planning")
        self.assertEqual(saved["skills"][0]["name"], "Planning")

        source_dir = self.tmp_path / "skills"
        source_dir.mkdir()
        (source_dir / "review.md").write_text("# Review\nCheck the code for regressions.\n", encoding="utf-8")
        args = parser.parse_args(
            [
                "skills",
                "import",
                "--settings",
                str(settings_path),
                str(source_dir),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "review" for item in saved["skills"]))

        out_path = self.tmp_path / "skills-export.json"
        args = parser.parse_args(
            [
                "skills",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["skills"])

        md_path = self.tmp_path / "skill-share.md"
        args = parser.parse_args(
            [
                "skills",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "planning",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Planning", rendered_md)
        self.assertIn("Help organize the work.", rendered_md)

        json_path = self.tmp_path / "skill-share.json"
        args = parser.parse_args(
            [
                "skills",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "planning",
                "--format",
                "json",
                str(json_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_json = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(rendered_json["id"], "planning")
        self.assertEqual(rendered_json["name"], "Planning")

        html_path = self.tmp_path / "skill-share.html"
        args = parser.parse_args(
            [
                "skills",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "planning",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("data-skill-id=\"planning\"", rendered_html)
        self.assertIn("Help organize the work.", rendered_html)

        args = parser.parse_args(
            [
                "skills",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "planning",
                "--new-id",
                "planning-copy",
                "--name",
                "Planning Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "planning-copy" for item in cloned["skills"]))
        clone_item = next(item for item in cloned["skills"] if item["id"] == "planning-copy")
        self.assertEqual(clone_item["name"], "Planning Copy")
        self.assertEqual(clone_item["content"], "Help organize the work.")

    def test_plugins_add_import_export_share(self):
        settings_path = self.tmp_path / "plugins.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "plugins",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Search Booster",
                "--content",
                "Enhance search with external APIs.",
                "--tag",
                "search",
                "--tool",
                "web-search",
                "--event",
                "chat.created",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("plugins", saved)
        self.assertEqual(saved["plugins"][0]["id"], "search-booster")
        self.assertEqual(saved["plugins"][0]["name"], "Search Booster")
        self.assertEqual(saved["plugins"][0]["tools"], ["web-search"])

        source_dir = self.tmp_path / "plugins"
        source_dir.mkdir()
        (source_dir / "moderation.md").write_text(
            "# Moderation\nReview content before publishing.\n",
            encoding="utf-8",
        )
        args = parser.parse_args(
            [
                "plugins",
                "import",
                "--settings",
                str(settings_path),
                str(source_dir),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "moderation" for item in saved["plugins"]))

        out_path = self.tmp_path / "plugins-export.json"
        args = parser.parse_args(
            [
                "plugins",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["plugins"])

        md_path = self.tmp_path / "plugin-share.md"
        args = parser.parse_args(
            [
                "plugins",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "search-booster",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Search Booster", rendered_md)
        self.assertIn("Enhance search with external APIs.", rendered_md)

        html_path = self.tmp_path / "plugin-share.html"
        args = parser.parse_args(
            [
                "plugins",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "search-booster",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("data-plugin-id=\"search-booster\"", rendered_html)
        self.assertIn("Enhance search with external APIs.", rendered_html)

        args = parser.parse_args(
            [
                "plugins",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "search-booster",
                "--new-id",
                "search-booster-copy",
                "--name",
                "Search Booster Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "search-booster-copy" for item in cloned["plugins"]))
        clone_item = next(item for item in cloned["plugins"] if item["id"] == "search-booster-copy")
        self.assertEqual(clone_item["name"], "Search Booster Copy")
        self.assertEqual(clone_item["content"], "Enhance search with external APIs.")

    def test_filters_and_actions_add_import_export_share(self):
        settings_path = self.tmp_path / "manifests.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "filters",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Safety Filter",
                "--content",
                "Block unsafe outputs before delivery.",
                "--event",
                "chat.created",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        args = parser.parse_args(
            [
                "actions",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Ticket Action",
                "--content",
                "Open an issue when a user asks for escalation.",
                "--tool",
                "web-search",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("filters", saved)
        self.assertIn("actions", saved)
        self.assertEqual(saved["filters"][0]["id"], "safety-filter")
        self.assertEqual(saved["actions"][0]["id"], "ticket-action")

        filter_md = self.tmp_path / "filter-share.md"
        args = parser.parse_args(
            [
                "filters",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "safety-filter",
                str(filter_md),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        self.assertIn("Safety Filter", filter_md.read_text(encoding="utf-8"))

        action_html = self.tmp_path / "action-share.html"
        args = parser.parse_args(
            [
                "actions",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "ticket-action",
                "--format",
                "html",
                str(action_html),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        self.assertIn("data-action-id=\"ticket-action\"", action_html.read_text(encoding="utf-8"))

        args = parser.parse_args(
            [
                "filters",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "safety-filter",
                "--new-id",
                "safety-filter-copy",
                "--name",
                "Safety Filter Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "safety-filter-copy" for item in cloned["filters"]))
        clone_item = next(item for item in cloned["filters"] if item["id"] == "safety-filter-copy")
        self.assertEqual(clone_item["name"], "Safety Filter Copy")
        self.assertEqual(clone_item["content"], "Block unsafe outputs before delivery.")

        args = parser.parse_args(
            [
                "actions",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "ticket-action",
                "--new-id",
                "ticket-action-copy",
                "--name",
                "Ticket Action Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "ticket-action-copy" for item in cloned["actions"]))
        clone_item = next(item for item in cloned["actions"] if item["id"] == "ticket-action-copy")
        self.assertEqual(clone_item["name"], "Ticket Action Copy")
        self.assertEqual(
            clone_item["content"],
            "Open an issue when a user asks for escalation.",
        )

    def test_automations_add_import_export_share(self):
        settings_path = self.tmp_path / "automations.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "automations",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Daily Summary",
                "--content",
                "Summarize the last 24 hours of work.",
                "--schedule",
                "0 9 * * *",
                "--timezone",
                "UTC",
                "--model",
                "qwen3-coder:latest",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("automations", saved)
        self.assertEqual(saved["automations"][0]["id"], "daily-summary")
        self.assertEqual(saved["automations"][0]["schedule"], "0 9 * * *")
        self.assertEqual(saved["automations"][0]["timezone"], "UTC")

        source_dir = self.tmp_path / "automations"
        source_dir.mkdir()
        (source_dir / "standup.md").write_text(
            "# Standup\nReport progress every morning.\n",
            encoding="utf-8",
        )
        args = parser.parse_args(
            [
                "automations",
                "import",
                "--settings",
                str(settings_path),
                str(source_dir),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "standup" for item in saved["automations"]))

        out_path = self.tmp_path / "automations-export.json"
        args = parser.parse_args(
            [
                "automations",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["automations"])

        md_path = self.tmp_path / "automation-share.md"
        args = parser.parse_args(
            [
                "automations",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "daily-summary",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Daily Summary", rendered_md)
        self.assertIn("0 9 * * *", rendered_md)

        html_path = self.tmp_path / "automation-share.html"
        args = parser.parse_args(
            [
                "automations",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "daily-summary",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("data-automation-id=\"daily-summary\"", rendered_html)
        self.assertIn("Summarize the last 24 hours of work.", rendered_html)

        args = parser.parse_args(
            [
                "automations",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "daily-summary",
                "--new-id",
                "daily-summary-copy",
                "--name",
                "Daily Summary Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "daily-summary-copy" for item in cloned["automations"]))
        clone_item = next(item for item in cloned["automations"] if item["id"] == "daily-summary-copy")
        self.assertEqual(clone_item["name"], "Daily Summary Copy")
        self.assertEqual(clone_item["prompt"], "Summarize the last 24 hours of work.")

    def test_pipelines_add_import_export_share(self):
        settings_path = self.tmp_path / "pipelines.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "pipelines",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Moderation",
                "--content",
                "Review content before publishing.",
                "--tag",
                "moderation",
                "--tool",
                "web-search",
                "--event",
                "chat.created",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("pipelines", saved)
        self.assertEqual(saved["pipelines"][0]["id"], "moderation")
        self.assertEqual(saved["pipelines"][0]["name"], "Moderation")
        self.assertEqual(saved["pipelines"][0]["tools"], ["web-search"])

        source_dir = self.tmp_path / "pipelines"
        source_dir.mkdir()
        (source_dir / "triage.md").write_text(
            "# Triage\nClassify incoming requests before routing.\n",
            encoding="utf-8",
        )
        args = parser.parse_args(
            [
                "pipelines",
                "import",
                "--settings",
                str(settings_path),
                str(source_dir),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "triage" for item in saved["pipelines"]))

        out_path = self.tmp_path / "pipelines-export.json"
        args = parser.parse_args(
            [
                "pipelines",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["pipelines"])

        md_path = self.tmp_path / "pipeline-share.md"
        args = parser.parse_args(
            [
                "pipelines",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "moderation",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Moderation", rendered_md)
        self.assertIn("Review content before publishing.", rendered_md)

        html_path = self.tmp_path / "pipeline-share.html"
        args = parser.parse_args(
            [
                "pipelines",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "moderation",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("data-plugin-id=\"moderation\"", rendered_html)
        self.assertIn("Review content before publishing.", rendered_html)

    def test_files_add_import_export_share(self):
        settings_path = self.tmp_path / "files.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "files",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Handoff",
                "--content",
                "This is the handoff file.",
                "--kind",
                "markdown",
                "--description",
                "Project handoff notes.",
                "--tag",
                "handoff",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["files"][0]["id"], "handoff")
        self.assertEqual(saved["files"][0]["kind"], "markdown")
        self.assertEqual(saved["files"][0]["description"], "Project handoff notes.")

        source_dir = self.tmp_path / "files"
        source_dir.mkdir()
        (source_dir / "guide.md").write_text("# Guide\nRead this guide.\n", encoding="utf-8")
        args = parser.parse_args(
            [
                "files",
                "import",
                "--settings",
                str(settings_path),
                str(source_dir),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "guide" for item in saved["files"]))

        out_path = self.tmp_path / "files-export.json"
        args = parser.parse_args(
            [
                "files",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["files"])

        md_path = self.tmp_path / "file-share.md"
        args = parser.parse_args(
            [
                "files",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "handoff",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Handoff", rendered_md)
        self.assertIn("Project handoff notes.", rendered_md)

        html_path = self.tmp_path / "file-share.html"
        args = parser.parse_args(
            [
                "files",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "handoff",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("data-file-id=\"handoff\"", rendered_html)
        self.assertIn("Project handoff notes.", rendered_html)

        json_path = self.tmp_path / "file-share.json"
        args = parser.parse_args(
            [
                "files",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "handoff",
                "--format",
                "json",
                str(json_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_json = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(rendered_json["id"], "handoff")
        self.assertEqual(rendered_json["name"], "Handoff")

        html_path = self.tmp_path / "file-share.html"
        args = parser.parse_args(
            [
                "files",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "handoff",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("data-file-id=\"handoff\"", rendered_html)
        self.assertIn("Project handoff notes.", rendered_html)

        args = parser.parse_args(
            [
                "files",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "handoff",
                "--new-id",
                "handoff-copy",
                "--name",
                "Handoff Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "handoff-copy" for item in cloned["files"]))
        clone_item = next(item for item in cloned["files"] if item["id"] == "handoff-copy")
        self.assertEqual(clone_item["name"], "Handoff Copy")
        self.assertEqual(clone_item["content"], "This is the handoff file.")

    def test_tools_add_and_list(self):
        settings_path = self.tmp_path / "tools.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "tools",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Search",
                "--endpoint",
                "http://127.0.0.1:3001/mcp",
                "--type",
                "mcp",
                "--tag",
                "search",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("toolServers", saved)
        self.assertEqual(saved["toolServers"][0]["id"], "search")
        self.assertEqual(saved["toolServers"][0]["endpoint"], "http://127.0.0.1:3001/mcp")

    def test_tools_import_export(self):
        source_path = self.tmp_path / "tools-source.json"
        source_path.write_text(
            json.dumps(
                {
                    "toolServers": [
                        {
                            "id": "search",
                            "name": "Search",
                            "type": "mcp",
                            "endpoint": "http://127.0.0.1:3001/mcp",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        settings_path = self.tmp_path / "tools-import.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "tools",
                "import",
                "--settings",
                str(settings_path),
                str(source_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["toolServers"][0]["id"], "search")

        args = parser.parse_args(
            [
                "tools",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "search",
                "--new-id",
                "search-copy",
                "--name",
                "Search Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "search-copy" for item in cloned["toolServers"]))
        clone_item = next(item for item in cloned["toolServers"] if item["id"] == "search-copy")
        self.assertEqual(clone_item["name"], "Search Copy")
        self.assertEqual(clone_item["endpoint"], "http://127.0.0.1:3001/mcp")

        out_path = self.tmp_path / "tools-export.json"
        args = parser.parse_args(
            [
                "tools",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(exported["toolServers"][0]["endpoint"], "http://127.0.0.1:3001/mcp")

    def test_kb_add_and_list(self):
        settings_path = self.tmp_path / "kb.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "kb",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Product Docs",
                "--source-dir",
                "/tmp/docs",
                "--tag",
                "docs",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("knowledgeBases", saved)
        self.assertEqual(saved["knowledgeBases"][0]["id"], "product-docs")
        self.assertEqual(saved["knowledgeBases"][0]["sourceDir"], "/tmp/docs")

        args = parser.parse_args(
            [
                "kb",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "product-docs",
                "--new-id",
                "product-docs-copy",
                "--name",
                "Product Docs Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "product-docs-copy" for item in cloned["knowledgeBases"]))
        clone_item = next(
            item for item in cloned["knowledgeBases"] if item["id"] == "product-docs-copy"
        )
        self.assertEqual(clone_item["name"], "Product Docs Copy")
        self.assertEqual(clone_item["sourceDir"], "/tmp/docs")

    def test_kb_import_export(self):
        source_path = self.tmp_path / "kb-source.json"
        source_path.write_text(
            json.dumps(
                {
                    "knowledgeBases": [
                        {
                            "id": "docs",
                            "name": "Docs",
                            "sourceDir": "/tmp/docs",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        settings_path = self.tmp_path / "kb-import.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "kb",
                "import",
                "--settings",
                str(settings_path),
                str(source_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["knowledgeBases"][0]["id"], "docs")

        out_path = self.tmp_path / "kb-export.json"
        args = parser.parse_args(
            [
                "kb",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(exported["knowledgeBases"][0]["sourceDir"], "/tmp/docs")

    def test_kb_ingest(self):
        source_dir = self.tmp_path / "kb-src"
        source_dir.mkdir()
        (source_dir / "guide.md").write_text(
            "# Guide\nThis is a sample knowledge document for ingestion.\n",
            encoding="utf-8",
        )
        index_path = self.tmp_path / "kb-index.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "kb",
                "ingest",
                "--settings",
                str(self.tmp_path / "kb-settings.json"),
                "--chunk-size",
                "24",
                "--overlap",
                "4",
                str(source_dir),
                str(index_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads((self.tmp_path / "kb-settings.json").read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "kb-src" for item in saved["knowledgeBases"]))
        self.assertTrue(any(item["baseId"] == "kb-src" for item in saved["knowledgeIndexes"]))
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(index["baseId"], "kb-src")
        self.assertEqual(index["documentCount"], 1)
        self.assertGreaterEqual(index["chunkCount"], 1)
        self.assertEqual(index["documents"][0]["title"], "guide")

    def test_kb_ingest_url(self):
        url = "http://example.test/release"
        settings_path = self.tmp_path / "kb-web-settings.json"
        out_path = self.tmp_path / "kb-web-index.json"
        parser = qo.build_parser()
        with unittest.mock.patch(
            "qwen_omega.fetch_web_document",
            return_value={
                "id": "release-notes",
                "name": "Release Notes",
                "content": "Release Notes Version 1.2 ships today.",
                "path": url,
                "kind": "html",
                "description": f"Fetched from {url}",
                "size": 123,
            },
        ):
            args = parser.parse_args(
                [
                    "kb",
                    "ingest-url",
                    "--settings",
                    str(settings_path),
                    "--base-id",
                    "web-release",
                    url,
                    str(out_path),
                ]
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "web-release" for item in saved["knowledgeBases"]))
        index = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(index["baseId"], "web-release")
        self.assertEqual(index["documentCount"], 1)
        self.assertGreaterEqual(index["chunkCount"], 1)
        self.assertIn("Version 1.2 ships today", index["documents"][0]["chunks"][0]["text"])

    def test_kb_query(self):
        source_dir = self.tmp_path / "kb-query-src"
        source_dir.mkdir()
        (source_dir / "handbook.md").write_text(
            "# Handbook\nThe release checklist includes testing, docs, and rollout.\n",
            encoding="utf-8",
        )
        settings_path = self.tmp_path / "kb-query-settings.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "kb",
                "ingest",
                "--settings",
                str(settings_path),
                "--base-id",
                "docs",
                str(source_dir),
                str(self.tmp_path / "kb-query-index.json"),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        args = parser.parse_args(
            [
                "kb",
                "query",
                "--settings",
                str(settings_path),
                "release",
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        output = buf.getvalue()
        self.assertIn("Knowledge Query Results", output)
        self.assertIn("handbook", output)
        self.assertIn("release", output.lower())

        args = parser.parse_args(
            [
                "kb",
                "query",
                "--settings",
                str(settings_path),
                "--base-id",
                "docs",
                "testing",
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("docs", buf.getvalue())

    def test_kb_refresh_rebuilds_registered_base(self):
        source_dir = self.tmp_path / "kb-refresh-src"
        source_dir.mkdir()
        doc_path = source_dir / "notes.md"
        doc_path.write_text(
            "# Release Notes\nInitial draft content.\n",
            encoding="utf-8",
        )
        settings_path = self.tmp_path / "kb-refresh-settings.json"
        out_path = self.tmp_path / "kb-refresh-index.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "kb",
                "ingest",
                "--settings",
                str(settings_path),
                "--base-id",
                "release-notes",
                str(source_dir),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        doc_path.write_text(
            "# Release Notes\nUpdated content with new rollout steps.\n",
            encoding="utf-8",
        )
        refresh_path = self.tmp_path / "kb-refresh-rebuilt.json"
        args = parser.parse_args(
            [
                "kb",
                "refresh",
                "--settings",
                str(settings_path),
                "--base-id",
                "release-notes",
                str(refresh_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        refreshed_settings = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "release-notes" for item in refreshed_settings["knowledgeBases"]))
        refreshed_index = json.loads(refresh_path.read_text(encoding="utf-8"))
        self.assertEqual(refreshed_index["baseId"], "release-notes")
        self.assertIn("Updated content with new rollout steps", refreshed_index["documents"][0]["chunks"][0]["text"])

    def test_kb_sync_rebuilds_all_registered_bases(self):
        source_one = self.tmp_path / "kb-sync-one"
        source_one.mkdir()
        source_two = self.tmp_path / "kb-sync-two"
        source_two.mkdir()
        doc_one = source_one / "alpha.md"
        doc_two = source_two / "beta.md"
        doc_one.write_text("# Alpha\nInitial alpha content.\n", encoding="utf-8")
        doc_two.write_text("# Beta\nInitial beta content.\n", encoding="utf-8")

        settings_path = self.tmp_path / "kb-sync-settings.json"
        out_one = self.tmp_path / "kb-sync-alpha.json"
        out_two = self.tmp_path / "kb-sync-beta.json"
        sync_dir = self.tmp_path / "kb-sync-out"
        parser = qo.build_parser()

        args = parser.parse_args(
            [
                "kb",
                "ingest",
                "--settings",
                str(settings_path),
                "--base-id",
                "alpha",
                str(source_one),
                str(out_one),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        args = parser.parse_args(
            [
                "kb",
                "ingest",
                "--settings",
                str(settings_path),
                "--base-id",
                "beta",
                str(source_two),
                str(out_two),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        doc_one.write_text("# Alpha\nUpdated alpha content.\n", encoding="utf-8")
        doc_two.write_text("# Beta\nUpdated beta content.\n", encoding="utf-8")

        args = parser.parse_args(
            [
                "kb",
                "sync",
                "--settings",
                str(settings_path),
                str(sync_dir),
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("Knowledge bases synced: 2", buf.getvalue())

        synced_settings = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "alpha" for item in synced_settings["knowledgeBases"]))
        self.assertTrue(any(item["id"] == "beta" for item in synced_settings["knowledgeBases"]))
        synced_alpha = json.loads((sync_dir / "alpha.json").read_text(encoding="utf-8"))
        synced_beta = json.loads((sync_dir / "beta.json").read_text(encoding="utf-8"))
        self.assertEqual(synced_alpha["baseId"], "alpha")
        self.assertEqual(synced_beta["baseId"], "beta")
        self.assertIn("Updated alpha content", synced_alpha["documents"][0]["chunks"][0]["text"])
        self.assertIn("Updated beta content", synced_beta["documents"][0]["chunks"][0]["text"])
        manifest = json.loads((sync_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(manifest["refreshed"]), ["alpha", "beta"])

    def test_kb_watch_rebuilds_after_source_change(self):
        source_dir = self.tmp_path / "kb-watch-src"
        source_dir.mkdir()
        doc_path = source_dir / "watch.md"
        doc_path.write_text("# Watch\nInitial watch content.\n", encoding="utf-8")

        settings_path = self.tmp_path / "kb-watch-settings.json"
        out_dir = self.tmp_path / "kb-watch-out"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "kb",
                "ingest",
                "--settings",
                str(settings_path),
                "--base-id",
                "watch",
                str(source_dir),
                str(self.tmp_path / "kb-watch-index.json"),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        def mutate_source_later() -> None:
            time.sleep(0.12)
            doc_path.write_text("# Watch\nUpdated watch content.\n", encoding="utf-8")

        thread = threading.Thread(target=mutate_source_later, daemon=True)
        thread.start()

        args = parser.parse_args(
            [
                "kb",
                "watch",
                "--settings",
                str(settings_path),
                "--interval",
                "0.2",
                "--iterations",
                "2",
                str(out_dir),
            ]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        thread.join(timeout=2)

        watched_index = json.loads((out_dir / "watch.json").read_text(encoding="utf-8"))
        self.assertEqual(watched_index["baseId"], "watch")
        self.assertIn("Updated watch content", watched_index["documents"][0]["chunks"][0]["text"])
        self.assertIn("Watched knowledge bases:", buf.getvalue())

    def test_snapshot_export_import_round_trip(self):
        settings_path = self.tmp_path / "snapshot-settings.json"
        settings_path.write_text(
            json.dumps(
                {
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
                    "notes": [
                        {
                            "id": "review",
                            "title": "Review",
                            "body": "Check the diff for regressions.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        parser = qo.build_parser()

        snapshot_path = self.tmp_path / "snapshot.json"
        args = parser.parse_args(
            [
                "snapshot",
                "export",
                "--settings",
                str(settings_path),
                str(snapshot_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "modelProviders": {
                        "openai": [
                            {
                                "id": "other",
                                "name": "other",
                                "baseUrl": "http://localhost",
                                "envKey": "API_KEY",
                            }
                        ]
                    },
                    "notes": [],
                }
            ),
            encoding="utf-8",
        )

        args = parser.parse_args(
            [
                "snapshot",
                "import",
                "--settings",
                str(settings_path),
                str(snapshot_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        restored = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(restored["modelProviders"]["openai"][0]["id"], "m1")
        self.assertEqual(restored["notes"][0]["title"], "Review")

        push_settings = {
            "$version": 4,
            "modelProviders": {
                "openai": [
                    {
                        "id": "push",
                        "name": "push",
                        "baseUrl": "http://localhost",
                        "envKey": "API_KEY",
                    }
                ]
            },
            "notes": [
                {
                    "id": "push-note",
                    "title": "Push Note",
                    "body": "Push content.",
                }
            ],
        }
        settings_path.write_text(json.dumps(push_settings), encoding="utf-8")
        now = time.time()
        os.utime(settings_path, (now + 20, now + 20))
        os.utime(snapshot_path, (now - 20, now - 20))

        args = parser.parse_args(
            [
                "snapshot",
                "sync",
                "--settings",
                str(settings_path),
                str(snapshot_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        pushed_bundle = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(pushed_bundle["settings"]["modelProviders"]["openai"][0]["id"], "push")
        self.assertEqual(pushed_bundle["settings"]["notes"][0]["title"], "Push Note")

        pull_bundle = {
            "format": qo.SNAPSHOT_FORMAT,
            "createdAt": "2026-08-01T00:00:00Z",
            "source": str(settings_path),
            "settings": {
                "$version": 4,
                "modelProviders": {
                    "openai": [
                        {
                            "id": "pull",
                            "name": "pull",
                            "baseUrl": "http://localhost",
                            "envKey": "API_KEY",
                        }
                    ]
                },
                "notes": [
                    {
                        "id": "pull-note",
                        "title": "Pull Note",
                        "body": "Pull content.",
                    }
                ],
            },
        }
        snapshot_path.write_text(json.dumps(pull_bundle), encoding="utf-8")
        os.utime(snapshot_path, (now + 40, now + 40))
        os.utime(settings_path, (now - 40, now - 40))

        args = parser.parse_args(
            [
                "snapshot",
                "sync",
                "--settings",
                str(settings_path),
                str(snapshot_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        pulled = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(pulled["modelProviders"]["openai"][0]["id"], "pull")
        self.assertEqual(pulled["notes"][0]["title"], "Pull Note")

    def test_snapshot_watch_tracks_changes(self):
        settings_path = self.tmp_path / "snapshot-watch-settings.json"
        snapshot_path = self.tmp_path / "snapshot-watch.json"

        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "modelProviders": {
                        "openai": [
                            {
                                "id": "start",
                                "name": "start",
                                "baseUrl": "http://localhost",
                                "envKey": "API_KEY",
                            }
                        ]
                    },
                    "notes": [
                        {
                            "id": "start-note",
                            "title": "Start Note",
                            "body": "Start content.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        snapshot_path.write_text(
            json.dumps(
                {
                    "format": qo.SNAPSHOT_FORMAT,
                    "createdAt": "2026-08-01T00:00:00Z",
                    "source": str(settings_path),
                    "settings": {
                        "$version": 4,
                        "modelProviders": {
                            "openai": [
                                {
                                    "id": "seed",
                                    "name": "seed",
                                    "baseUrl": "http://localhost",
                                    "envKey": "API_KEY",
                                }
                            ]
                        },
                        "notes": [
                            {
                                "id": "seed-note",
                                "title": "Seed Note",
                                "body": "Seed content.",
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        now = time.time()
        os.utime(settings_path, (now - 40, now - 40))
        os.utime(snapshot_path, (now - 20, now - 20))

        mutation_done = threading.Event()

        def mutate_settings_later() -> None:
            time.sleep(0.12)
            settings_path.write_text(
                json.dumps(
                    {
                        "$version": 4,
                        "modelProviders": {
                            "openai": [
                                {
                                    "id": "watch-push",
                                    "name": "watch-push",
                                    "baseUrl": "http://localhost",
                                    "envKey": "API_KEY",
                                }
                            ]
                        },
                        "notes": [
                            {
                                "id": "watch-push-note",
                                "title": "Watch Push",
                                "body": "Watch push content.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            os.utime(settings_path, None)
            mutation_done.set()

        thread = threading.Thread(target=mutate_settings_later, daemon=True)
        thread.start()
        self.assertTrue(mutation_done.wait(timeout=2), "settings mutation did not complete")
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "snapshot",
                "watch",
                "--settings",
                str(settings_path),
                "--interval",
                "0.1",
                "--iterations",
                "1",
                str(snapshot_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        thread.join(timeout=2)

        watched_settings = json.loads(settings_path.read_text(encoding="utf-8"))
        watched_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(watched_settings["modelProviders"]["openai"][0]["id"], "watch-push")
        self.assertEqual(watched_snapshot["settings"]["modelProviders"]["openai"][0]["id"], "watch-push")
        self.assertEqual(watched_snapshot["settings"]["notes"][0]["title"], "Watch Push")

    def test_web_search_and_save_to_knowledge(self):
        parser = qo.build_parser()
        search_results = [
            {
                "title": "Release Notes",
                "url": "http://example.test/release",
                "snippet": "Version 1.2 ships today.",
            },
            {
                "title": "Documentation",
                "url": "http://example.test/docs",
                "snippet": "Read the setup guide.",
            },
        ]

        def fake_fetch_web_search_results(query, *, provider, engine_url, api_key, timeout, limit):
            self.assertEqual(query, "release")
            self.assertEqual(provider, "duckduckgo")
            return search_results

        with unittest.mock.patch(
            "qwen_omega.fetch_web_search_results",
            side_effect=fake_fetch_web_search_results,
        ):
            args = parser.parse_args(
                [
                    "web-search",
                    "--engine-url",
                    "http://example.test/search?q={query}",
                    "--limit",
                    "2",
                    "release",
                ]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(args.func(args), 0)
            output = buf.getvalue()
            self.assertIn("Web Search Results", output)
            self.assertIn("Release Notes", output)
            self.assertIn("/release", output)

        settings_path = self.tmp_path / "web-search-settings.json"
        out_path = self.tmp_path / "web-search-index.json"
        doc_map = {
            "http://example.test/release": {
                "id": "release-notes",
                "name": "Release Notes",
                "content": "Release Notes Version 1.2 ships today.",
                "path": "http://example.test/release",
                "kind": "html",
                "description": "Fetched from http://example.test/release",
                "size": 123,
            },
            "http://example.test/docs": {
                "id": "documentation",
                "name": "Documentation",
                "content": "Documentation Read the setup guide.",
                "path": "http://example.test/docs",
                "kind": "html",
                "description": "Fetched from http://example.test/docs",
                "size": 123,
            },
        }

        with unittest.mock.patch(
            "qwen_omega.fetch_web_search_results",
            side_effect=fake_fetch_web_search_results,
        ), unittest.mock.patch(
            "qwen_omega.fetch_web_document",
            side_effect=lambda url, timeout: doc_map[url],
        ):
            args = parser.parse_args(
                [
                    "web-search",
                    "--settings",
                    str(settings_path),
                    "--engine-url",
                    "http://example.test/search?q={query}",
                    "--save-to-knowledge",
                    "--base-id",
                    "search-release",
                    "--save-limit",
                    "2",
                    "release",
                    str(out_path),
                ]
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "search-release" for item in saved["knowledgeBases"]))
        index = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(index["baseId"], "search-release")
        self.assertEqual(index["documentCount"], 2)
        self.assertGreaterEqual(index["chunkCount"], 2)

    def test_web_search_list_providers(self):
        parser = qo.build_parser()
        args = parser.parse_args(["web-search", "--list-providers"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        output = buf.getvalue()
        self.assertIn("Web Search Providers", output)
        self.assertIn("duckduckgo", output)
        self.assertIn("external", output)

    def test_web_search_external_provider_and_save_to_knowledge(self):
        parser = qo.build_parser()
        search_results = [
            {
                "title": "Release Notes",
                "url": "http://example.test/release",
                "snippet": "Version 1.2 ships today.",
            },
            {
                "title": "Documentation",
                "url": "http://example.test/docs",
                "snippet": "Read the setup guide.",
            },
        ]

        def fake_fetch_web_search_results(query, *, provider, engine_url, api_key, timeout, limit):
            self.assertEqual(query, "release")
            self.assertEqual(provider, "external")
            return search_results

        with unittest.mock.patch(
            "qwen_omega.fetch_web_search_results",
            side_effect=fake_fetch_web_search_results,
        ):
            args = parser.parse_args(
                [
                    "web-search",
                    "--provider",
                    "external",
                    "--engine-url",
                    "http://example.test/search",
                    "--limit",
                    "2",
                    "release",
                ]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(args.func(args), 0)
            output = buf.getvalue()
            self.assertIn("Web Search Results", output)
            self.assertIn("Release Notes", output)
            self.assertIn("/release", output)

        settings_path = self.tmp_path / "web-search-external-settings.json"
        out_path = self.tmp_path / "web-search-external-index.json"
        doc_map = {
            "http://example.test/release": {
                "id": "release-notes",
                "name": "Release Notes",
                "content": "Release Notes Version 1.2 ships today.",
                "path": "http://example.test/release",
                "kind": "html",
                "description": "Fetched from http://example.test/release",
                "size": 123,
            },
            "http://example.test/docs": {
                "id": "documentation",
                "name": "Documentation",
                "content": "Documentation Read the setup guide.",
                "path": "http://example.test/docs",
                "kind": "html",
                "description": "Fetched from http://example.test/docs",
                "size": 123,
            },
        }

        with unittest.mock.patch(
            "qwen_omega.fetch_web_search_results",
            side_effect=fake_fetch_web_search_results,
        ), unittest.mock.patch(
            "qwen_omega.fetch_web_document",
            side_effect=lambda url, timeout: doc_map[url],
        ):
            args = parser.parse_args(
                [
                    "web-search",
                    "--provider",
                    "external",
                    "--settings",
                    str(settings_path),
                    "--engine-url",
                    "http://example.test/search",
                    "--save-to-knowledge",
                    "--base-id",
                    "search-release",
                    "--save-limit",
                    "2",
                    "release",
                    str(out_path),
                ]
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "search-release" for item in saved["knowledgeBases"]))
        index = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(index["baseId"], "search-release")
        self.assertEqual(index["documentCount"], 2)
        self.assertGreaterEqual(index["chunkCount"], 2)

    def test_web_search_merges_fallback_providers(self):
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "web-search",
                "--provider",
                "external",
                "--fallback-provider",
                "brave",
                "--engine-url",
                "http://127.0.0.1:8000/search",
                "--limit",
                "3",
                "release",
            ]
        )
        calls: list[tuple[str, str]] = []

        def fake_fetch(query, provider, engine_url, api_key, timeout, limit):
            calls.append((provider, engine_url))
            if provider == "external":
                return [
                    {"title": "Primary Release", "url": "http://example.com/release", "snippet": "primary"},
                    {"title": "Primary Duplicate", "url": "http://example.com/shared", "snippet": "dup"},
                ]
            if provider == "brave":
                return [
                    {"title": "Fallback Duplicate", "url": "http://example.com/shared", "snippet": "dup"},
                    {"title": "Fallback Docs", "url": "http://example.com/docs", "snippet": "docs"},
                ]
            return []

        buf = io.StringIO()
        with unittest.mock.patch.object(qo, "fetch_web_search_results", side_effect=fake_fetch):
            with redirect_stdout(buf):
                self.assertEqual(args.func(args), 0)

        output = buf.getvalue()
        self.assertIn("Primary Release", output)
        self.assertIn("Fallback Docs", output)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], "external")
        self.assertEqual(calls[1][0], "brave")
        self.assertNotIn("No matches found.", output)

    def test_memories_add_import_export_share(self):
        settings_path = self.tmp_path / "memories.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "memories",
                "add",
                "--settings",
                str(settings_path),
                "--title",
                "Preferences",
                "--content",
                "Prefer concise answers.",
                "--scope",
                "user",
                "--tag",
                "preference",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["memories"][0]["id"], "preferences")
        self.assertEqual(saved["memories"][0]["scope"], "user")

        args = parser.parse_args(["memories", "list", "--settings", str(settings_path)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("Memories:", buf.getvalue())
        self.assertIn("Preferences", buf.getvalue())

        source_path = self.tmp_path / "memory-source.md"
        source_path.write_text("# Travel\nPrefer window seats.\n", encoding="utf-8")
        args = parser.parse_args(
            [
                "memories",
                "import",
                "--settings",
                str(settings_path),
                str(source_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "memory-source" for item in saved["memories"]))

        export_path = self.tmp_path / "memories-export.json"
        args = parser.parse_args(
            [
                "memories",
                "export",
                "--settings",
                str(settings_path),
                str(export_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertIn("memories", exported)

        share_path = self.tmp_path / "memory-share.md"
        args = parser.parse_args(
            [
                "memories",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "preferences",
                str(share_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        self.assertIn("Prefer concise answers", share_path.read_text(encoding="utf-8"))

        share_html = self.tmp_path / "memory-share.html"
        args = parser.parse_args(
            [
                "memories",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "preferences",
                "--format",
                "html",
                str(share_html),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = share_html.read_text(encoding="utf-8")
        self.assertIn("data-memory-id=\"preferences\"", rendered_html)
        self.assertIn("Prefer concise answers", rendered_html)

        args = parser.parse_args(
            [
                "memories",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "preferences",
                "--new-id",
                "preferences-copy",
                "--title",
                "Preferences Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "preferences-copy" for item in cloned["memories"]))
        clone_item = next(item for item in cloned["memories"] if item["id"] == "preferences-copy")
        self.assertEqual(clone_item["title"], "Preferences Copy")
        self.assertEqual(clone_item["content"], "Prefer concise answers.")

    def test_webhooks_add_import_export(self):
        settings_path = self.tmp_path / "webhooks.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "webhooks",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Ops Alerts",
                "--url",
                "http://127.0.0.1:9000/webhook",
                "--event",
                "chat.created",
                "--event",
                "chat.updated",
                "--enabled",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["webhooks"][0]["id"], "ops-alerts")
        self.assertTrue(saved["webhooks"][0]["enabled"])

        args = parser.parse_args(["webhooks", "list", "--settings", str(settings_path)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("Webhooks:", buf.getvalue())
        self.assertIn("Ops Alerts", buf.getvalue())

        import_path = self.tmp_path / "webhooks-source.json"
        import_path.write_text(
            json.dumps(
                {
                    "webhooks": [
                        {
                            "id": "alerts",
                            "name": "Alerts",
                            "url": "http://127.0.0.1:9001/hook",
                            "events": ["knowledge.created"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        args = parser.parse_args(
            [
                "webhooks",
                "import",
                "--settings",
                str(settings_path),
                str(import_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "alerts" for item in saved["webhooks"]))

        args = parser.parse_args(
            [
                "webhooks",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "ops-alerts",
                "--new-id",
                "ops-alerts-copy",
                "--name",
                "Ops Alerts Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "ops-alerts-copy" for item in cloned["webhooks"]))
        clone_item = next(item for item in cloned["webhooks"] if item["id"] == "ops-alerts-copy")
        self.assertEqual(clone_item["name"], "Ops Alerts Copy")
        self.assertEqual(clone_item["url"], "http://127.0.0.1:9000/webhook")
        self.assertEqual(clone_item["events"], ["chat.created", "chat.updated"])

        export_path = self.tmp_path / "webhooks-export.json"
        args = parser.parse_args(
            [
                "webhooks",
                "export",
                "--settings",
                str(settings_path),
                str(export_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertIn("webhooks", exported)

        share_html = self.tmp_path / "webhooks-share.html"
        args = parser.parse_args(
            [
                "webhooks",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "ops-alerts",
                "--format",
                "html",
                str(share_html),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = share_html.read_text(encoding="utf-8")
        self.assertIn("data-webhook-id=\"ops-alerts\"", rendered_html)
        self.assertIn("http://127.0.0.1:9000/webhook", rendered_html)

    def test_notes_add_import_export(self):
        settings_path = self.tmp_path / "notes.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "notes",
                "add",
                "--settings",
                str(settings_path),
                "--title",
                "Review",
                "--body",
                "Check the diff for regressions.",
                "--file",
                "handoff",
                "--image",
                "preview.png",
                "--tag",
                "review",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["notes"][0]["id"], "review")
        self.assertEqual(saved["notes"][0]["title"], "Review")
        self.assertEqual(saved["notes"][0]["files"], ["handoff"])
        self.assertEqual(saved["notes"][0]["images"], ["preview.png"])

        source_path = self.tmp_path / "notes-source.md"
        source_path.write_text("# Draft\nWrite the draft.\n", encoding="utf-8")
        args = parser.parse_args(
            [
                "notes",
                "import",
                "--settings",
                str(settings_path),
                str(source_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "notes-source" for item in saved["notes"]))

        out_path = self.tmp_path / "notes-export.json"
        args = parser.parse_args(
            [
                "notes",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["notes"])

        md_path = self.tmp_path / "note-share.md"
        args = parser.parse_args(
            [
                "notes",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "review",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Review", rendered_md)
        self.assertIn("Attachments: handoff", rendered_md)
        self.assertIn("Images: preview.png", rendered_md)

        html_path = self.tmp_path / "note-share.html"
        args = parser.parse_args(
            [
                "notes",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "review",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("data-note-id=\"review\"", rendered_html)
        self.assertIn("Attachments: handoff", rendered_html)
        self.assertIn("Images: preview.png", rendered_html)

        args = parser.parse_args(
            [
                "notes",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "review",
                "--new-id",
                "review-copy",
                "--title",
                "Review Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "review-copy" for item in cloned["notes"]))
        clone_item = next(item for item in cloned["notes"] if item["id"] == "review-copy")
        self.assertEqual(clone_item["title"], "Review Copy")
        self.assertEqual(clone_item["body"], "Check the diff for regressions.")

    def test_artifacts_add_import_export(self):
        settings_path = self.tmp_path / "artifacts.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "artifacts",
                "add",
                "--settings",
                str(settings_path),
                "--title",
                "Release Notes",
                "--content",
                "Release notes content.",
                "--kind",
                "markdown",
                "--tag",
                "release",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["artifacts"][0]["id"], "release-notes")
        self.assertEqual(saved["artifacts"][0]["kind"], "markdown")

        source_path = self.tmp_path / "artifact-source.json"
        source_path.write_text(
            json.dumps(
                {
                    "artifacts": [
                        {
                            "id": "diagram",
                            "title": "Diagram",
                            "content": "<svg></svg>",
                            "kind": "svg",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        args = parser.parse_args(
            [
                "artifacts",
                "import",
                "--settings",
                str(settings_path),
                str(source_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "diagram" for item in saved["artifacts"]))

        out_path = self.tmp_path / "artifacts-export.json"
        args = parser.parse_args(
            [
                "artifacts",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["artifacts"])

        md_path = self.tmp_path / "artifact-share.md"
        args = parser.parse_args(
            [
                "artifacts",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "release-notes",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Release Notes", rendered_md)
        self.assertIn("Release notes content.", rendered_md)

        json_path = self.tmp_path / "artifact-share.json"
        args = parser.parse_args(
            [
                "artifacts",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "release-notes",
                "--format",
                "json",
                str(json_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_json = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(rendered_json["id"], "release-notes")
        self.assertEqual(rendered_json["title"], "Release Notes")

        args = parser.parse_args(
            [
                "artifacts",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "release-notes",
                "--new-id",
                "release-notes-copy",
                "--title",
                "Release Notes Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "release-notes-copy" for item in cloned["artifacts"]))
        clone_item = next(item for item in cloned["artifacts"] if item["id"] == "release-notes-copy")
        self.assertEqual(clone_item["title"], "Release Notes Copy")
        self.assertEqual(clone_item["content"], "Release notes content.")

        html_path = self.tmp_path / "artifact-share.html"
        args = parser.parse_args(
            [
                "artifacts",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "release-notes",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("data-artifact-id=\"release-notes\"", rendered_html)
        self.assertIn("Release notes content.", rendered_html)

    def test_search_across_registries(self):
        settings_path = self.tmp_path / "search.json"
        settings_path.write_text(
            json.dumps(
                {
                    "$version": 4,
                    "promptTemplates": [
                        {
                            "id": "review",
                            "name": "Review",
                            "content": "Review this diff.",
                        }
                    ],
                    "skills": [
                        {
                            "id": "planning",
                            "name": "Planning",
                            "content": "Help organize work.",
                        }
                    ],
                    "plugins": [
                        {
                            "id": "search-booster",
                            "name": "Search Booster",
                            "content": "Enhance search with external APIs.",
                        }
                    ],
                    "pipelines": [
                        {
                            "id": "moderation",
                            "name": "Moderation",
                            "content": "Review content before publishing.",
                        }
                    ],
                    "filters": [
                        {
                            "id": "safety-filter",
                            "name": "Safety Filter",
                            "content": "Block unsafe outputs before delivery.",
                        }
                    ],
                    "actions": [
                        {
                            "id": "ticket-action",
                            "name": "Ticket Action",
                            "content": "Open an issue when a user asks for escalation.",
                        }
                    ],
                    "automations": [
                        {
                            "id": "daily-summary",
                            "name": "Daily Summary",
                            "prompt": "Summarize the last 24 hours of work.",
                            "schedule": "0 9 * * *",
                            "timezone": "UTC",
                        }
                    ],
                    "files": [
                        {
                            "id": "handoff",
                            "name": "Handoff",
                            "content": "This is the handoff file.",
                        }
                    ],
                    "agents": [
                        {
                            "id": "mentor",
                            "name": "Mentor",
                            "baseModel": "qwen3-coder:latest",
                            "systemPrompt": "Help with release planning and code review.",
                            "folderId": "project-alpha",
                            "tools": ["search"],
                        }
                    ],
                    "conversations": [
                        {
                            "id": "thread-1",
                            "title": "Planning",
                            "transcript": "Discuss release planning and schedule.",
                            "folderId": "project-alpha",
                        }
                    ],
                    "channels": [
                        {
                            "id": "channel-1",
                            "title": "Planning Channel",
                            "transcript": "Discuss release planning and schedule.",
                            "folderId": "project-alpha",
                        }
                    ],
                    "folders": [
                        {
                            "id": "project-alpha",
                            "name": "Project Alpha",
                            "systemPrompt": "Be concise and project-aware.",
                        }
                    ],
                    "notes": [
                        {
                            "id": "note-1",
                            "title": "Release",
                            "body": "Release notes content.",
                        }
                    ],
                    "artifacts": [
                        {
                            "id": "artifact-1",
                            "title": "Diagram",
                            "content": "diagram content",
                        }
                    ],
                    "knowledgeBases": [
                        {
                            "id": "docs",
                            "name": "Docs",
                            "sourceDir": "/tmp/docs",
                        }
                    ],
                    "toolServers": [
                        {
                            "id": "search",
                            "name": "Search",
                            "endpoint": "http://127.0.0.1:3001/mcp",
                        }
                    ],
                    "modelProviders": {
                        "openai": [
                            {
                                "id": "qwen3-coder:latest",
                                "name": "Qwen",
                                "baseUrl": "http://localhost",
                                "envKey": "QWEN_API_KEY",
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        parser = qo.build_parser()
        args = parser.parse_args(["search", "--settings", str(settings_path), "release"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("notes", buf.getvalue())
        self.assertIn("Release", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "files", "handoff"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("files", buf.getvalue())
        self.assertIn("Handoff", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "skills", "planning"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("skills", buf.getvalue())
        self.assertIn("Planning", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "plugins", "search"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("plugins", buf.getvalue())
        self.assertIn("Search Booster", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "pipelines", "moderation"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("pipelines", buf.getvalue())
        self.assertIn("Moderation", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "filters", "safety"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("filters", buf.getvalue())
        self.assertIn("Safety Filter", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "actions", "ticket"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("actions", buf.getvalue())
        self.assertIn("Ticket Action", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "automations", "summary"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("automations", buf.getvalue())
        self.assertIn("Daily Summary", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "agents", "mentor"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("agents", buf.getvalue())
        self.assertIn("Mentor", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "conversations", "planning"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("conversations", buf.getvalue())
        self.assertIn("Planning", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "channels", "planning"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("channels", buf.getvalue())
        self.assertIn("Planning Channel", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "folders", "project"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("folders", buf.getvalue())
        self.assertIn("Project Alpha", buf.getvalue())

        args = parser.parse_args(["search", "--settings", str(settings_path), "--kind", "artifacts", "diagram"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(args.func(args), 0)
        self.assertIn("artifacts", buf.getvalue())
        self.assertIn("Diagram", buf.getvalue())

    def test_conversations_add_import_export(self):
        settings_path = self.tmp_path / "conversations.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "conversations",
                "add",
                "--settings",
                str(settings_path),
                "--title",
                "Planning",
                "--file",
                "handoff",
                "--image",
                "cover.png",
                "--transcript",
                "assistant: We should ship on Friday.\nuser: Agreed.",
                "--tag",
                "planning",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["conversations"][0]["id"], "planning")
        self.assertEqual(saved["conversations"][0]["title"], "Planning")
        self.assertIn("transcript", saved["conversations"][0])
        self.assertEqual(saved["conversations"][0]["files"], ["handoff"])
        self.assertEqual(saved["conversations"][0]["images"], ["cover.png"])

        source_path = self.tmp_path / "conversation-source.md"
        source_path.write_text("# Retro\nassistant: Review what went well.\n", encoding="utf-8")
        args = parser.parse_args(
            [
                "conversations",
                "import",
                "--settings",
                str(settings_path),
                str(source_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "conversation-source" for item in saved["conversations"]))

        out_path = self.tmp_path / "conversations-export.json"
        args = parser.parse_args(
            [
                "conversations",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["conversations"])

        md_path = self.tmp_path / "conversation-share.md"
        args = parser.parse_args(
            [
                "conversations",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "planning",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Planning", rendered_md)
        self.assertIn("assistant: We should ship on Friday.", rendered_md)
        self.assertIn("Attachments: handoff", rendered_md)
        self.assertIn("Images: cover.png", rendered_md)

        html_path = self.tmp_path / "conversation-share.html"
        args = parser.parse_args(
            [
                "conversations",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "planning",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("<title>Planning</title>", rendered_html)
        self.assertIn("assistant: We should ship on Friday.", rendered_html)
        self.assertIn("data-conversation-id=\"planning\"", rendered_html)
        self.assertIn("Attachments: handoff", rendered_html)
        self.assertIn("Images: cover.png", rendered_html)

        args = parser.parse_args(
            [
                "conversations",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "planning",
                "--new-id",
                "planning-copy",
                "--title",
                "Planning Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "planning-copy" for item in cloned["conversations"]))
        clone_item = next(item for item in cloned["conversations"] if item["id"] == "planning-copy")
        self.assertEqual(clone_item["title"], "Planning Copy")
        self.assertEqual(
            clone_item["transcript"],
            "assistant: We should ship on Friday.\nuser: Agreed.",
        )

    def test_channels_add_import_export_share(self):
        settings_path = self.tmp_path / "channels.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "channels",
                "add",
                "--settings",
                str(settings_path),
                "--title",
                "Planning Channel",
                "--file",
                "handoff",
                "--image",
                "cover.png",
                "--transcript",
                "assistant: Keep the release on track.\nuser: Confirmed.",
                "--message",
                "assistant: Keep the release on track.",
                "--message",
                "user: Confirmed.",
                "--tag",
                "planning",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["channels"][0]["id"], "planning-channel")
        self.assertEqual(saved["channels"][0]["title"], "Planning Channel")
        self.assertIn("transcript", saved["channels"][0])
        self.assertEqual(saved["channels"][0]["files"], ["handoff"])
        self.assertEqual(saved["channels"][0]["images"], ["cover.png"])
        self.assertEqual(
            saved["channels"][0]["messages"],
            [
                {"role": "assistant", "content": "Keep the release on track."},
                {"role": "user", "content": "Confirmed."},
            ],
        )

        source_path = self.tmp_path / "channel-source.md"
        source_path.write_text("# Retro\nassistant: Review what went well.\n", encoding="utf-8")
        args = parser.parse_args(
            [
                "channels",
                "import",
                "--settings",
                str(settings_path),
                str(source_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "channel-source" for item in saved["channels"]))

        out_path = self.tmp_path / "channels-export.json"
        args = parser.parse_args(
            [
                "channels",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["channels"])

        md_path = self.tmp_path / "channel-share.md"
        args = parser.parse_args(
            [
                "channels",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "planning-channel",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Planning Channel", rendered_md)
        self.assertIn("assistant: Keep the release on track.", rendered_md)
        self.assertIn("Attachments: handoff", rendered_md)
        self.assertIn("Images: cover.png", rendered_md)

        html_path = self.tmp_path / "channel-share.html"
        args = parser.parse_args(
            [
                "channels",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "planning-channel",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("<title>Planning Channel</title>", rendered_html)
        self.assertIn("Keep the release on track.", rendered_html)
        self.assertIn("data-channel-id=\"planning-channel\"", rendered_html)
        self.assertIn("Attachments: handoff", rendered_html)
        self.assertIn("Images: cover.png", rendered_html)

        args = parser.parse_args(
            [
                "channels",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "planning-channel",
                "--new-id",
                "planning-channel-copy",
                "--title",
                "Planning Channel Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(
            any(item["id"] == "planning-channel-copy" for item in cloned["channels"])
        )
        clone_item = next(
            item for item in cloned["channels"] if item["id"] == "planning-channel-copy"
        )
        self.assertEqual(clone_item["title"], "Planning Channel Copy")
        self.assertEqual(
            clone_item["transcript"],
            "assistant: Keep the release on track.\nuser: Confirmed.",
        )

    def test_folders_add_import_export_share_and_conversation_link(self):
        settings_path = self.tmp_path / "folders.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "folders",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Project Alpha",
                "--system-prompt",
                "Be concise and project-aware.",
                "--knowledge",
                "docs",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["folders"][0]["id"], "project-alpha")
        self.assertEqual(saved["folders"][0]["systemPrompt"], "Be concise and project-aware.")

        folder_import = self.tmp_path / "folders-source.json"
        folder_import.write_text(
            json.dumps(
                {
                    "folders": [
                        {
                            "id": "nested",
                            "name": "Nested",
                            "parentId": "project-alpha",
                            "description": "Nested project folder",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        args = parser.parse_args(
            [
                "folders",
                "import",
                "--settings",
                str(settings_path),
                str(folder_import),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "nested" for item in saved["folders"]))

        folder_share = self.tmp_path / "folder-share.md"
        args = parser.parse_args(
            [
                "folders",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "project-alpha",
                str(folder_share),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        self.assertIn("Project Alpha", folder_share.read_text(encoding="utf-8"))

        args = parser.parse_args(
            [
                "folders",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "project-alpha",
                "--new-id",
                "project-alpha-copy",
                "--name",
                "Project Alpha Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "project-alpha-copy" for item in cloned["folders"]))
        clone_item = next(item for item in cloned["folders"] if item["id"] == "project-alpha-copy")
        self.assertEqual(clone_item["name"], "Project Alpha Copy")
        self.assertEqual(clone_item["systemPrompt"], "Be concise and project-aware.")

        args = parser.parse_args(
            [
                "conversations",
                "add",
                "--settings",
                str(settings_path),
                "--title",
                "Alpha Chat",
                "--transcript",
                "assistant: Working in a project folder.",
                "--folder",
                "project-alpha",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        convo_saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(convo_saved["conversations"][0]["folderId"], "project-alpha")
        self.assertEqual(convo_saved["conversations"][0]["systemPrompt"], "Be concise and project-aware.")
        self.assertEqual(convo_saved["conversations"][0]["knowledge"], ["docs"])

        args = parser.parse_args(
            [
                "conversations",
                "add",
                "--settings",
                str(settings_path),
                "--title",
                "Override Chat",
                "--folder",
                "project-alpha",
                "--system-prompt",
                "Override the folder prompt.",
                "--knowledge",
                "ops",
                "--transcript",
                "assistant: Override prompt in use.",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        convo_saved = json.loads(settings_path.read_text(encoding="utf-8"))
        override = next(item for item in convo_saved["conversations"] if item["id"] == "override-chat")
        self.assertEqual(override["systemPrompt"], "Override the folder prompt.")
        self.assertEqual(override["knowledge"], ["ops"])

    def test_agents_add_import_export_share(self):
        settings_path = self.tmp_path / "agents.json"
        parser = qo.build_parser()
        args = parser.parse_args(
            [
                "agents",
                "add",
                "--settings",
                str(settings_path),
                "--name",
                "Mentor",
                "--base-model",
                "qwen3-coder:latest",
                "--system-prompt",
                "Help with release planning and code review.",
                "--tool",
                "search",
                "--knowledge",
                "docs",
                "--skill",
                "planning",
                "--param",
                "temperature=0.2",
                "--visibility",
                "private",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["agents"][0]["id"], "mentor")
        self.assertEqual(saved["agents"][0]["baseModel"], "qwen3-coder:latest")
        self.assertEqual(saved["agents"][0]["parameters"]["temperature"], "0.2")

        source_path = self.tmp_path / "agents-source.json"
        source_path.write_text(
            json.dumps(
                {
                    "agents": [
                        {
                            "id": "reviewer",
                            "name": "Reviewer",
                            "baseModel": "qwen3-coder:latest",
                            "systemPrompt": "Review changes.",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        args = parser.parse_args(
            [
                "agents",
                "import",
                "--settings",
                str(settings_path),
                str(source_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "reviewer" for item in saved["agents"]))

        out_path = self.tmp_path / "agents-export.json"
        args = parser.parse_args(
            [
                "agents",
                "export",
                "--settings",
                str(settings_path),
                str(out_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        exported = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["agents"])

        md_path = self.tmp_path / "agent-share.md"
        args = parser.parse_args(
            [
                "agents",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "mentor",
                str(md_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_md = md_path.read_text(encoding="utf-8")
        self.assertIn("# Mentor", rendered_md)
        self.assertIn("- Base model: qwen3-coder:latest", rendered_md)
        self.assertIn("Help with release planning and code review.", rendered_md)

        json_path = self.tmp_path / "agent-share.json"
        args = parser.parse_args(
            [
                "agents",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "mentor",
                "--format",
                "json",
                str(json_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_json = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(rendered_json["id"], "mentor")
        self.assertEqual(rendered_json["baseModel"], "qwen3-coder:latest")

        html_path = self.tmp_path / "agent-share.html"
        args = parser.parse_args(
            [
                "agents",
                "share",
                "--settings",
                str(settings_path),
                "--id",
                "mentor",
                "--format",
                "html",
                str(html_path),
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        rendered_html = html_path.read_text(encoding="utf-8")
        self.assertIn("data-agent-id=\"mentor\"", rendered_html)
        self.assertIn("Help with release planning and code review.", rendered_html)

        args = parser.parse_args(
            [
                "agents",
                "clone",
                "--settings",
                str(settings_path),
                "--id",
                "mentor",
                "--new-id",
                "mentor-copy",
                "--name",
                "Mentor Copy",
            ]
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)
        cloned = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["id"] == "mentor-copy" for item in cloned["agents"]))
        clone_item = next(item for item in cloned["agents"] if item["id"] == "mentor-copy")
        self.assertEqual(clone_item["name"], "Mentor Copy")
        self.assertEqual(clone_item["baseModel"], "qwen3-coder:latest")


if __name__ == "__main__":
    unittest.main()
