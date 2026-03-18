import argparse
import json

import pytest

from pakem import (
    IgnoreRules,
    RepoPacker,
    count_tokens,
    is_binary,
)
from pakem.cli import (
    _normalize_argv,
    parse_byte_size,
    parse_positive_int,
    resolve_output_path,
)
from pakem.commands import (
    ArchiveDiffCommand,
    DiffCommand,
    RestoreCommand,
    SetupPrecommitCommand,
)
from pakem.fs import FileWalker
from pakem.gitinfo import GitFileMetadata
from pakem.state import RepoState
from pakem.validation import validate_pakem


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_none(self):
        assert count_tokens(None) == 0

    def test_simple_text(self):
        tokens = count_tokens("hello world")
        assert tokens > 0

    def test_code_snippet(self):
        code = "def foo():\n    return 42\n"
        tokens = count_tokens(code)
        assert tokens > 0

    def test_model_argument_does_not_fail(self):
        tokens = count_tokens("hello world", model="gpt-4")
        assert tokens > 0


class TestIsBinary:
    def test_text_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        assert is_binary(str(f)) is False

    def test_binary_file(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        assert is_binary(str(f)) is True

    def test_nonexistent_file(self):
        assert is_binary("/nonexistent/path") is True


class TestIgnoreRules:
    def test_default_patterns(self, tmp_path):
        rules = IgnoreRules.from_defaults(str(tmp_path), None)
        assert ".git" in rules.patterns
        assert "__pycache__" in rules.patterns

    def test_gitignore_patterns(self, tmp_path):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\ntemp/\n")
        rules = IgnoreRules.from_defaults(str(tmp_path), None)
        assert "*.log" in rules.patterns
        assert "temp/" in rules.patterns

    def test_should_ignore_glob(self):
        rules = IgnoreRules.from_defaults("/root", ["*.pyc"])
        assert rules.should_ignore("/root/test.pyc", "/root") is True

    def test_should_ignore_directory(self):
        rules = IgnoreRules.from_defaults("/root", ["build/"])
        assert rules.should_ignore("/root/build", "/root") is True

    def test_ignore_file_is_used(self, tmp_path):
        ignore_file = tmp_path / ".myignore"
        ignore_file.write_text("*.secret\n")

        rules = IgnoreRules.from_defaults(
            str(tmp_path), None, extra_ignore_file=str(ignore_file)
        )
        assert (
            rules.should_ignore(str(tmp_path / "bad.secret"), str(tmp_path))
            is True
        )


class TestRepoPacker:
    def test_pack_creates_output(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "hello.py").write_text("print('hello')\n")
        out = tmp_path / "output.xml"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(str(tmp_path), str(out), ignore_rules, walker)
        packer.pack()

        assert out.exists()
        content = out.read_text()
        assert '<?xml version="1.0"' in content
        assert "<repository" in content
        assert "hello.py" in content

    def test_pack_skips_binary(self, tmp_path):
        (tmp_path / "text.txt").write_text("hello")
        (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02")
        out = tmp_path / "output.xml"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(str(tmp_path), str(out), ignore_rules, walker)
        packer.pack()

        content = out.read_text()
        assert "text.txt" in content
        assert "binary.bin" not in content

    def test_pack_respects_ignores(self, tmp_path):
        (tmp_path / "keep.py").write_text("keep")
        (tmp_path / "skip.log").write_text("skip")
        out = tmp_path / "output.xml"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), ["*.log"])
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(str(tmp_path), str(out), ignore_rules, walker)
        packer.pack()

        content = out.read_text()
        assert "keep.py" in content
        assert "skip.log" not in content

    def test_pack_with_include_filters_paths(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "docs").mkdir()
        (tmp_path / "src" / "keep.py").write_text("keep")
        (tmp_path / "docs" / "drop.md").write_text("drop")
        out = tmp_path / "output.xml"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(
            str(tmp_path),
            ignore_rules,
            output_path=str(out),
            include_patterns=["src/"],
        )
        packer = RepoPacker(str(tmp_path), str(out), ignore_rules, walker)
        packer.pack()

        content = out.read_text()
        assert "keep.py" in content
        assert "drop.md" not in content

    def test_pack_with_tracked_paths_filters_untracked(self, tmp_path):
        (tmp_path / "tracked.py").write_text("print(1)")
        (tmp_path / "untracked.py").write_text("print(2)")
        out = tmp_path / "output.json"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(
            str(tmp_path),
            ignore_rules,
            output_path=str(out),
            tracked_paths={"tracked.py"},
        )
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
        )
        assert packer.pack() == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        paths = [item["path"] for item in payload["files"]]
        assert "tracked.py" in paths
        assert "untracked.py" not in paths

    def test_include_overrides_default_ignore(self, tmp_path):
        (tmp_path / "build").mkdir()
        (tmp_path / "build" / "forced.py").write_text("x=1")
        out = tmp_path / "output.xml"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(
            str(tmp_path),
            ignore_rules,
            output_path=str(out),
            include_patterns=["build/"],
        )
        packer = RepoPacker(str(tmp_path), str(out), ignore_rules, walker)
        packer.pack()

        content = out.read_text()
        assert "forced.py" in content

    def test_pack_includes_metadata(self, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        out = tmp_path / "output.xml"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(str(tmp_path), str(out), ignore_rules, walker)
        packer.pack()

        content = out.read_text()
        assert 'total_files="1"' in content
        assert "tokens=" in content
        assert "lines=" in content

    def test_pack_respects_max_file_size(self, tmp_path):
        (tmp_path / "small.py").write_text("print(1)\n")
        (tmp_path / "large.py").write_text("x" * 2048)
        out = tmp_path / "output.json"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            max_file_size=256,
        )
        assert packer.pack() == 0

        payload = __import__("json").loads(out.read_text(encoding="utf-8"))
        paths = [item["path"] for item in payload["files"]]
        assert "small.py" in paths
        assert "large.py" not in paths

    def test_state_excludes_files_skipped_by_max_file_size(self, tmp_path):
        (tmp_path / "small.py").write_text("print(1)\n")
        (tmp_path / "large.py").write_text("x" * 2048)
        out = tmp_path / "output.json"
        state = tmp_path / "state.json"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            state_path=str(state),
            max_file_size=256,
        )
        assert packer.pack() == 0

        loaded = RepoState.load(str(state))
        assert "small.py" in loaded.files
        assert "large.py" not in loaded.files

    def test_pack_respects_max_total_tokens_with_focus_ranking(self, tmp_path):
        class WordTokenCounter:
            def count(self, text, model=None):
                return len(text.split())

        (tmp_path / "main.py").write_text("run")
        (tmp_path / "notes.md").write_text("one two three four five six")
        out = tmp_path / "output.json"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            token_counter=WordTokenCounter(),
            max_total_tokens=1,
            focus_ranking="basic",
        )
        assert packer.pack() == 0

        payload = __import__("json").loads(out.read_text(encoding="utf-8"))
        paths = [item["path"] for item in payload["files"]]
        assert "main.py" in paths
        assert "notes.md" not in paths

    def test_state_excludes_files_skipped_by_token_budget(self, tmp_path):
        class WordTokenCounter:
            def count(self, text, model=None):
                return len(text.split())

        (tmp_path / "main.py").write_text("run")
        (tmp_path / "notes.md").write_text("one two three four five six")
        out = tmp_path / "output.json"
        state = tmp_path / "state.json"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            state_path=str(state),
            token_counter=WordTokenCounter(),
            max_total_tokens=1,
            focus_ranking="basic",
        )
        assert packer.pack() == 0
        assert packer.skipped_token_budget == 1

        loaded = RepoState.load(str(state))
        assert "main.py" in loaded.files
        assert "notes.md" not in loaded.files

    def test_pack_dry_run_writes_no_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        secret = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        (src / "token.txt").write_text(secret)
        out = tmp_path / "output.json"
        state = tmp_path / "state.json"
        report = tmp_path / "report.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            state_path=str(state),
            sensitive_data_policy="warn",
            sensitive_report_out=str(report),
            dry_run=True,
        )
        assert packer.pack() == 0
        assert not out.exists()
        assert not state.exists()
        assert not report.exists()

    def test_llm_prompt_output_with_semantic_chunking_and_summary(
        self, tmp_path
    ):
        src = tmp_path / "src"
        src.mkdir()
        (src / "module.py").write_text(
            "def alpha():\n    return 1\n\nclass Beta:\n    pass\n"
        )
        out = tmp_path / "prompt"

        from pakem.cli import main

        code = main(
            [
                "pack",
                "--path",
                str(src),
                "--format",
                "llm-prompt",
                "--semantic-chunking",
                "--summary-mode",
                "basic",
                "--out",
                str(out),
            ]
        )
        assert code == 0
        prompt_path = out.with_suffix(".prompt.md")
        assert prompt_path.exists()
        text = prompt_path.read_text(encoding="utf-8")
        assert "LLM Prompt Profile" in text
        assert "### function: alpha" in text
        assert "Summary:" in text

    def test_git_metadata_enrichment_in_json(self, tmp_path, monkeypatch):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("print(1)\n")
        out = tmp_path / "out.json"

        monkeypatch.setattr(
            "pakem.packer.get_git_metadata_for_path",
            lambda root, rel: GitFileMetadata(
                commit="abc123",
                author="dev <dev@example.com>",
                date="1710000000",
            ),
        )

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        from pakem.policy import PackagingPolicy

        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            policy=PackagingPolicy(git_metadata=True),
        )
        assert packer.pack() == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        item = payload["files"][0]
        assert item["git_commit"] == "abc123"
        assert "dev" in item["git_author"]

    def test_selection_report_written_with_skip_reasons(self, tmp_path):
        (tmp_path / "small.py").write_text("print(1)\n")
        (tmp_path / "large.py").write_text("x" * 2048)
        out = tmp_path / "output.json"
        selection_report = tmp_path / "selection-report.json"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            max_file_size=256,
            selection_report_out=str(selection_report),
        )
        assert packer.pack() == 0
        assert selection_report.exists()

        report = __import__("json").loads(
            selection_report.read_text(encoding="utf-8")
        )
        assert report["status"] == "ok"
        assert "small.py" in report["selected_paths"]
        assert "large.py" in report["skipped"]["max_file_size"]["paths"]

    def test_selection_report_not_written_in_dry_run(self, tmp_path):
        (tmp_path / "a.py").write_text("print(1)\n")
        out = tmp_path / "output.json"
        selection_report = tmp_path / "selection-report.json"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            dry_run=True,
            selection_report_out=str(selection_report),
        )
        assert packer.pack() == 0
        assert not selection_report.exists()

    def test_incremental_state_and_delta(self, tmp_path):
        state = tmp_path / "state.json"
        out = tmp_path / "output.xml"

        (tmp_path / "a.txt").write_text("first")
        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            state_path=str(state),
        )
        packer.pack()

        assert state.exists()
        data = state.read_text()
        assert "a.txt" in data

        (tmp_path / "a.txt").write_text("second")
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            state_path=str(state),
            delta=True,
        )
        packer.pack()

        content = out.read_text()
        assert 'status="modified"' in content

    def test_json_output_format(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "hello.py").write_text("print('hello')\n")
        out = tmp_path / "output.json"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
        )
        packer.pack()

        assert out.exists()
        import json

        data = json.loads(out.read_text())
        assert data["repository"]["total_files"] == 1
        assert data["files"][0]["name"] == "hello.py"

    def test_proto_output_format(self, tmp_path):
        try:
            import pakem.proto
        except ImportError:
            import pytest

            pytest.skip("protobuf not installed")

        src = tmp_path / "src"
        src.mkdir()
        (src / "hello.py").write_text("print('hello')\n")
        out = tmp_path / "output.pb"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="proto",
        )
        packer.pack()

        assert out.exists()
        from pakem.proto import get_repository_message_class

        data = get_repository_message_class().FromString(out.read_bytes())
        assert data.total_files == 1
        assert data.files[0].name == "hello.py"

    def test_pakem_output_format(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "hello.py").write_text("print('hello')\n")
        out = tmp_path / "output.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(tmp_path), None)
        walker = FileWalker(str(tmp_path), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(tmp_path),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
        )
        packer.pack()

        assert out.exists()
        assert out.read_bytes()[:4] == b"PAKM"

    def test_pakem_dedup_chunks_sets_offsets(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        content = "same-content\n"
        (src / "a.txt").write_text(content)
        (src / "b.txt").write_text(content)
        out = tmp_path / "dedup.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
            dedup_chunks=True,
        )
        assert packer.pack() == 0

        raw = out.read_bytes()
        header_len = int.from_bytes(raw[5:9], "big")
        metadata = json.loads(raw[9 : 9 + header_len].decode("utf-8"))
        files = metadata["files"]
        assert all("payload_offset" in item for item in files)
        offsets = {item["payload_offset"] for item in files}
        assert len(offsets) == 1

    def test_distributed_shard_filters_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(6):
            (src / f"f{i}.py").write_text(f"print({i})\n")
        out = tmp_path / "shard.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            distributed_shards=2,
            distributed_index=0,
        )
        assert packer.pack() == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        shard_paths = [item["path"] for item in payload["files"]]
        assert 0 < len(shard_paths) < 6

    def test_local_cache_mode_writes_cache_file(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("print(1)\n")
        out = tmp_path / "cache.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            cache_mode="local",
        )
        assert packer.pack() == 0
        cache_file = src / ".pakem-cache" / "analysis-cache.json"
        assert cache_file.exists()

    def test_sensitive_data_redaction_policy_redact(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        secret = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        (src / "secrets.txt").write_text(f"TOKEN = '{secret}'\n")
        out = tmp_path / "output.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            sensitive_data_policy="redact",
        )
        assert packer.pack() == 0
        payload = out.read_text(encoding="utf-8")
        assert secret not in payload
        assert (
            "[REDACTED_GITHUB_TOKEN]" in payload
            or "[REDACTED_SECRET_ASSIGNMENT]" in payload
        )

    def test_sensitive_data_redaction_policy_warn(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        secret = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        (src / "secrets.txt").write_text(f"TOKEN = '{secret}'\n")
        out = tmp_path / "output.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            sensitive_data_policy="warn",
        )
        assert packer.pack() == 0
        payload = out.read_text(encoding="utf-8")
        assert secret in payload

    def test_sensitive_data_warn_report_written(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        secret = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        (src / "secrets.txt").write_text(f"TOKEN = '{secret}'\n")
        out = tmp_path / "output.json"
        report = tmp_path / "sensitive-report.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            sensitive_data_policy="warn",
            sensitive_report_out=str(report),
        )
        assert packer.pack() == 0
        assert report.exists()
        data = __import__("json").loads(report.read_text(encoding="utf-8"))
        assert data["status"] == "ok"
        assert data["policy"] == "warn"
        assert data["total_findings"] >= 1
        assert data["files"]

    def test_sensitive_data_redaction_policy_block(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        secret = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        (src / "secrets.txt").write_text(f"TOKEN = '{secret}'\n")
        out = tmp_path / "output.json"
        report = tmp_path / "sensitive-report.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            sensitive_data_policy="block",
            sensitive_report_out=str(report),
        )
        assert packer.pack() == 1
        assert not out.exists()
        assert report.exists()
        data = __import__("json").loads(report.read_text(encoding="utf-8"))
        assert data["status"] == "blocked"
        assert data["policy"] == "block"
        assert data["total_findings"] >= 1


class TestCliBehavior:
    @staticmethod
    def _normalize_spaces(text: str) -> str:
        return " ".join(text.split())

    def test_format_changes_default_extension(self):
        assert resolve_output_path("repo", "json") == "repo.json"
        assert resolve_output_path("repo", "xml") == "repo.xml"
        assert resolve_output_path("repo", "proto") == "repo.pb"
        assert resolve_output_path("repo", "pakem") == "repo.pakem"

    def test_parse_positive_int(self):
        assert parse_positive_int("1") == 1
        assert parse_positive_int("32") == 32

    def test_parse_positive_int_rejects_non_positive(self):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_positive_int("0")
        with pytest.raises(argparse.ArgumentTypeError):
            parse_positive_int("-2")

    def test_parse_byte_size(self):
        assert parse_byte_size("1024") == 1024
        assert parse_byte_size("2KB") == 2 * 1024
        assert parse_byte_size("3mb") == 3 * 1024 * 1024
        assert parse_byte_size("1 GB") == 1024 * 1024 * 1024

    def test_parse_byte_size_rejects_invalid(self):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_byte_size("0")
        with pytest.raises(argparse.ArgumentTypeError):
            parse_byte_size("12XB")

    def test_normalize_argv_from_sys_argv(self, monkeypatch):
        monkeypatch.setattr(
            "pakem.cli.sys.argv",
            ["pakem", "--format", "pakem", "--out", "repo.pakem"],
        )
        assert _normalize_argv(None) == [
            "pack",
            "--format",
            "pakem",
            "--out",
            "repo.pakem",
        ]

    def test_normalize_argv_explicit_values(self):
        assert _normalize_argv(
            ["--format", "pakem", "--out", "repo.pakem"]
        ) == [
            "pack",
            "--format",
            "pakem",
            "--out",
            "repo.pakem",
        ]

    def test_pack_help_has_descriptions(self, capsys):
        from pakem.cli import main

        with pytest.raises(SystemExit):
            main(["pack", "--help"])
        output = self._normalize_spaces(capsys.readouterr().out)
        assert "Repository root to pack" in output
        assert "Split output into parts of this size" in output
        assert "Encryption cipher profile used with --encrypt-key" in output
        assert "off, warn, redact, or block" in output
        assert "sensitive-data findings report" in output

    def test_diff_help_has_descriptions(self, capsys):
        from pakem.cli import main

        with pytest.raises(SystemExit):
            main(["diff", "--help"])
        output = self._normalize_spaces(capsys.readouterr().out)
        assert "Existing state file used as diff baseline" in output
        assert "added/modified/removed summary" in output

    def test_diff_command_dry_run_skips_diff_out_file(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("v1")
        state = tmp_path / "state.json"
        initial_out = tmp_path / "initial.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(
            str(src), ignore_rules, output_path=str(initial_out)
        )
        initial = RepoPacker(
            str(src),
            str(initial_out),
            ignore_rules,
            walker,
            output_format="json",
            state_path=str(state),
        )
        assert initial.pack() == 0

        (src / "a.txt").write_text("v2")
        dry_out = tmp_path / "dry.json"
        diff_out = tmp_path / "diff.json"
        args = argparse.Namespace(
            path=str(src),
            state=str(state),
            out=str(dry_out),
            diff_out=str(diff_out),
            ignore=None,
            include=None,
            ignore_file=None,
            format="json",
            sensitive_data_policy="off",
            sensitive_report_out=None,
            selection_report_out=None,
            max_file_size=None,
            max_total_tokens=None,
            dry_run=True,
            focus_ranking="basic",
        )
        assert DiffCommand(args).execute() == 0
        assert not dry_out.exists()
        assert not diff_out.exists()

    def test_diff_command_writes_selection_report(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "small.py").write_text("print(1)\n")
        (src / "large.py").write_text("x" * 2048)
        state = tmp_path / "state.json"
        initial_out = tmp_path / "initial.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(
            str(src), ignore_rules, output_path=str(initial_out)
        )
        initial = RepoPacker(
            str(src),
            str(initial_out),
            ignore_rules,
            walker,
            output_format="json",
            state_path=str(state),
        )
        assert initial.pack() == 0

        (src / "small.py").write_text("print(2)\n")
        out = tmp_path / "diff-pack.json"
        selection_report = tmp_path / "selection-report.json"
        args = argparse.Namespace(
            path=str(src),
            state=str(state),
            out=str(out),
            diff_out=None,
            ignore=None,
            include=None,
            ignore_file=None,
            format="json",
            sensitive_data_policy="off",
            sensitive_report_out=None,
            selection_report_out=str(selection_report),
            max_file_size=256,
            max_total_tokens=None,
            dry_run=False,
            focus_ranking="basic",
        )
        assert DiffCommand(args).execute() == 0
        assert selection_report.exists()

    def test_archive_diff_command_outputs_changes(self, tmp_path):
        left = tmp_path / "left.json"
        right = tmp_path / "right.json"
        left.write_text(
            json.dumps(
                {
                    "repository": {
                        "root": "r",
                        "timestamp": "t",
                        "total_files": 1,
                        "total_size": 1,
                        "total_tokens": 1,
                    },
                    "directories": [],
                    "files": [
                        {
                            "path": "a.py",
                            "name": "a.py",
                            "size": 1,
                            "tokens": 1,
                            "type": "file",
                            "extension": ".py",
                            "lines": 1,
                            "depth": 1,
                            "content": ["x"],
                            "hash": "h1",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        right.write_text(
            json.dumps(
                {
                    "repository": {
                        "root": "r",
                        "timestamp": "t",
                        "total_files": 2,
                        "total_size": 2,
                        "total_tokens": 2,
                    },
                    "directories": [],
                    "files": [
                        {
                            "path": "a.py",
                            "name": "a.py",
                            "size": 1,
                            "tokens": 1,
                            "type": "file",
                            "extension": ".py",
                            "lines": 1,
                            "depth": 1,
                            "content": ["x"],
                            "hash": "h2",
                        },
                        {
                            "path": "b.py",
                            "name": "b.py",
                            "size": 1,
                            "tokens": 1,
                            "type": "file",
                            "extension": ".py",
                            "lines": 1,
                            "depth": 1,
                            "content": ["y"],
                            "hash": "h3",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        out = tmp_path / "diff.json"
        args = argparse.Namespace(
            left=str(left),
            right=str(right),
            left_format="json",
            right_format="json",
            out=str(out),
        )
        assert ArchiveDiffCommand(args).execute() == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["added"] == ["b.py"]
        assert payload["modified"] == ["a.py"]
        assert payload["removed"] == []

    def test_archive_diff_command_writes_html_report(self, tmp_path):
        left = tmp_path / "left.json"
        right = tmp_path / "right.json"
        left.write_text(
            json.dumps(
                {
                    "repository": {
                        "root": "r",
                        "timestamp": "t",
                        "total_files": 0,
                        "total_size": 0,
                        "total_tokens": 0,
                    },
                    "directories": [],
                    "files": [],
                }
            ),
            encoding="utf-8",
        )
        right.write_text(
            json.dumps(
                {
                    "repository": {
                        "root": "r",
                        "timestamp": "t",
                        "total_files": 1,
                        "total_size": 1,
                        "total_tokens": 1,
                    },
                    "directories": [],
                    "files": [
                        {
                            "path": "x.py",
                            "name": "x.py",
                            "size": 1,
                            "tokens": 1,
                            "type": "file",
                            "extension": ".py",
                            "lines": 1,
                            "depth": 1,
                            "content": ["x"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        html_out = tmp_path / "report.html"
        args = argparse.Namespace(
            left=str(left),
            right=str(right),
            left_format="json",
            right_format="json",
            out=None,
            html_out=str(html_out),
        )
        assert ArchiveDiffCommand(args).execute() == 0
        assert html_out.exists()
        assert "pakem Diff Report" in html_out.read_text(encoding="utf-8")

    def test_setup_precommit_command_creates_config(self, tmp_path):
        args = argparse.Namespace(path=str(tmp_path), force=False)
        assert SetupPrecommitCommand(args).execute() == 0
        cfg = tmp_path / ".pre-commit-config.yaml"
        assert cfg.exists()
        assert "ruff" in cfg.read_text(encoding="utf-8")

    def test_cloud_output_path_suffix_resolution(self):
        assert (
            resolve_output_path("s3://bucket/archive", "json")
            == "s3://bucket/archive.json"
        )

    def test_pack_rejects_compress_for_non_pakem(self, tmp_path):
        from pakem.cli import main

        output = tmp_path / "out"
        code = main(
            [
                "pack",
                "--path",
                str(tmp_path),
                "--format",
                "json",
                "--compress",
                "zlib",
                "--out",
                str(output),
            ]
        )
        assert code == 2
        assert not output.with_suffix(".json").exists()

    def test_pack_rejects_split_size_for_non_pakem(self, tmp_path):
        from pakem.cli import main

        output = tmp_path / "out"
        code = main(
            [
                "pack",
                "--path",
                str(tmp_path),
                "--format",
                "xml",
                "--split-size",
                "1MB",
                "--out",
                str(output),
            ]
        )
        assert code == 2
        assert not output.with_suffix(".xml").exists()

    def test_pack_rejects_encrypt_with_cipher_none(self, tmp_path):
        from pakem.cli import main

        output = tmp_path / "out"
        code = main(
            [
                "pack",
                "--path",
                str(tmp_path),
                "--format",
                "pakem",
                "--cipher",
                "none",
                "--encrypt-key",
                "secret",
                "--out",
                str(output),
            ]
        )
        assert code == 2
        assert not output.with_suffix(".pakem").exists()

    def test_restore_help_has_descriptions(self, capsys):
        from pakem.cli import main

        with pytest.raises(SystemExit):
            main(["restore", "--help"])
        output = self._normalize_spaces(capsys.readouterr().out)
        assert "Input pakem archive path" in output
        assert "Destination directory for restored files" in output


class TestStateCompatibility:
    def test_load_legacy_state_without_version(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text(
            '{"files":{"a.txt":{"mtime":1.0,"size":4,"sha256":"x"}}}',
            encoding="utf-8",
        )
        loaded = RepoState.load(str(state))
        assert loaded.version == 1
        assert "a.txt" in loaded.files

    def test_memory_state_backend_roundtrip(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("alpha")
        out = tmp_path / "output.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            state_path="memory://phase-a",
        )
        assert packer.pack() == 0

        restored = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            state_path="memory://phase-a",
            delta=True,
        )
        assert restored.pack() == 0

    def test_sqlite_state_backend_roundtrip(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("alpha")
        out = tmp_path / "output.json"
        state_spec = f"sqlite:///{tmp_path / 'state.db'}?key=repo-a"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        first = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            state_path=state_spec,
        )
        assert first.pack() == 0

        second = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
            state_path=state_spec,
            delta=True,
        )
        assert second.pack() == 0


class TestLoaders:
    def test_langchain_loader_reads_json(self, tmp_path):
        from pakem.loaders import PakemLangChainLoader

        payload = {
            "repository": {
                "root": "r",
                "timestamp": "t",
                "total_files": 1,
                "total_size": 1,
                "total_tokens": 1,
            },
            "directories": [],
            "files": [
                {
                    "path": "a.py",
                    "name": "a.py",
                    "size": 1,
                    "tokens": 1,
                    "type": "file",
                    "extension": ".py",
                    "lines": 1,
                    "depth": 1,
                    "content": ["print(1)"],
                }
            ],
        }
        p = tmp_path / "repo.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        docs = PakemLangChainLoader(str(p)).load()
        assert docs
        assert "print(1)" in docs[0]["page_content"]

    def test_llamaindex_reader_reads_json(self, tmp_path):
        from pakem.loaders import PakemLlamaIndexReader

        payload = {
            "repository": {
                "root": "r",
                "timestamp": "t",
                "total_files": 1,
                "total_size": 1,
                "total_tokens": 1,
            },
            "directories": [],
            "files": [
                {
                    "path": "a.py",
                    "name": "a.py",
                    "size": 1,
                    "tokens": 1,
                    "type": "file",
                    "extension": ".py",
                    "lines": 1,
                    "depth": 1,
                    "content": ["print(1)"],
                }
            ],
        }
        p = tmp_path / "repo.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        nodes = PakemLlamaIndexReader().load_data(str(p))
        assert nodes
        assert "print(1)" in nodes[0]["text"]


class TestPakemValidation:
    def test_validate_pakem_success(self, tmp_path):
        out = tmp_path / "ok.pakem"
        metadata = b'{"repository":{},"files":[],"directories":[]}'
        out.write_bytes(
            b"PAKM" + bytes([2]) + len(metadata).to_bytes(4, "big") + metadata
        )
        validate_pakem(str(out))

    def test_validate_pakem_failure(self, tmp_path):
        import pytest

        out = tmp_path / "bad.pakem"
        out.write_bytes(b"BAD!" + bytes([2]) + (2).to_bytes(4, "big") + b"{}")
        with pytest.raises(ValueError):
            validate_pakem(str(out))


class TestPakemRestore:
    def test_restore_with_compression_and_encryption(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("alpha")
        (src / "b.txt").write_text("beta")
        out = tmp_path / "archive.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
            compression="zlib",
            encryption_key="secret",
            encryption_cipher="aes-gcm",
        )
        assert packer.pack() == 0

        restored = tmp_path / "restored"
        restore_packer = RepoPacker(
            str(restored),
            str(out),
            IgnoreRules.from_defaults(str(restored), None),
            FileWalker(
                str(restored), IgnoreRules.from_defaults(str(restored), None)
            ),
            output_format="pakem",
            compression="zlib",
            encryption_key="secret",
            encryption_cipher="aes-gcm",
        )
        assert restore_packer.restore(str(out), str(restored)) == 0
        assert (restored / "a.txt").read_text() == "alpha"
        assert (restored / "b.txt").read_text() == "beta"

    def test_restore_with_archive_signature_verification(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("alpha")
        out = tmp_path / "signed.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
            signing_key="sign-key",
        )
        assert packer.pack() == 0

        restored = tmp_path / "restored"
        restore_packer = RepoPacker(
            str(restored),
            str(out),
            IgnoreRules.from_defaults(str(restored), None),
            FileWalker(
                str(restored), IgnoreRules.from_defaults(str(restored), None)
            ),
            output_format="pakem",
            verify_signature_key="sign-key",
        )
        assert restore_packer.restore(str(out), str(restored)) == 0
        assert (restored / "a.txt").read_text() == "alpha"

    def test_restore_with_wrong_signature_key_fails(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("alpha")
        out = tmp_path / "signed.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
            signing_key="sign-key",
        )
        assert packer.pack() == 0

        restored = tmp_path / "restored"
        restore_packer = RepoPacker(
            str(restored),
            str(out),
            IgnoreRules.from_defaults(str(restored), None),
            FileWalker(
                str(restored), IgnoreRules.from_defaults(str(restored), None)
            ),
            output_format="pakem",
            verify_signature_key="wrong-key",
        )
        assert restore_packer.restore(str(out), str(restored)) == 1

    def test_restore_legacy_xor_requires_legacy_mode(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("legacy")
        out = tmp_path / "legacy.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
            encryption_key="k",
            encryption_cipher="legacy-xor",
        )
        assert packer.pack() == 0

        restore_fail = RepoPacker(
            str(tmp_path / "restore-no-legacy"),
            str(out),
            IgnoreRules.from_defaults(
                str(tmp_path / "restore-no-legacy"), None
            ),
            FileWalker(
                str(tmp_path / "restore-no-legacy"),
                IgnoreRules.from_defaults(
                    str(tmp_path / "restore-no-legacy"), None
                ),
            ),
            output_format="pakem",
            encryption_key="k",
        )
        assert (
            restore_fail.restore(str(out), str(tmp_path / "restore-no-legacy"))
            == 1
        )

        restore_ok = RepoPacker(
            str(tmp_path / "restore-legacy"),
            str(out),
            IgnoreRules.from_defaults(str(tmp_path / "restore-legacy"), None),
            FileWalker(
                str(tmp_path / "restore-legacy"),
                IgnoreRules.from_defaults(
                    str(tmp_path / "restore-legacy"), None
                ),
            ),
            output_format="pakem",
            encryption_key="k",
            legacy_mode=True,
        )
        assert (
            restore_ok.restore(str(out), str(tmp_path / "restore-legacy")) == 0
        )
        assert (tmp_path / "restore-legacy" / "a.txt").read_text() == "legacy"

    def test_pakem_metadata_includes_negotiation_fields(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("alpha")
        out = tmp_path / "archive.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
        )
        assert packer.pack() == 0

        raw = out.read_bytes()
        header_len = int.from_bytes(raw[5:9], "big")
        metadata = __import__("json").loads(
            raw[9 : 9 + header_len].decode("utf-8")
        )
        repo = metadata["repository"]
        assert repo["min_reader_version"] == 2
        assert repo["max_reader_version"] == 2

    def test_restore_with_wrong_key_fails(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "secret.txt").write_text("very-secret-content")
        out = tmp_path / "archive.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
            compression="zlib",
            encryption_key="correct-key",
            encryption_cipher="aes-gcm",
        )
        assert packer.pack() == 0

        restored = tmp_path / "restored"
        restore_packer = RepoPacker(
            str(restored),
            str(out),
            IgnoreRules.from_defaults(str(restored), None),
            FileWalker(
                str(restored), IgnoreRules.from_defaults(str(restored), None)
            ),
            output_format="pakem",
            compression="zlib",
            encryption_key="wrong-key",
            encryption_cipher="aes-gcm",
        )
        assert restore_packer.restore(str(out), str(restored)) == 1
        assert not (restored / "secret.txt").exists()

    def test_restore_command_sanitizes_target_path(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("alpha")
        out = tmp_path / "archive.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
        )
        assert packer.pack() == 0

        target_with_quote = str(tmp_path / "restored folder") + '"'
        args = argparse.Namespace(
            input_file=str(out),
            target=target_with_quote,
            format="pakem",
            compress="none",
            encrypt_key=None,
            cipher="aes-gcm",
        )
        assert RestoreCommand(args).execute() == 0
        assert (tmp_path / "restored folder" / "a.txt").read_text() == "alpha"

    def test_artifact_size_matches_real_file_size(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("A" * 4000)
        out = tmp_path / "output.json"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="json",
        )
        assert packer.pack() == 0
        assert packer.total_artifact_size == out.stat().st_size
        assert packer.total_content_size > 0

    def test_split_artifact_size_matches_parts_total(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("B" * 6000)
        out = tmp_path / "archive.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
            split_size=512,
            compression="zlib",
        )
        assert packer.pack() == 0
        parts = sorted(tmp_path.glob("archive.pakem.part*"))
        assert parts
        total_parts = sum(part.stat().st_size for part in parts)
        assert packer.total_artifact_size == total_parts

    def test_restore_from_split_parts(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("A" * 3000)
        out = tmp_path / "archive.pakem"

        ignore_rules = IgnoreRules.from_defaults(str(src), None)
        walker = FileWalker(str(src), ignore_rules, output_path=str(out))
        packer = RepoPacker(
            str(src),
            str(out),
            ignore_rules,
            walker,
            output_format="pakem",
            split_size=512,
        )
        assert packer.pack() == 0
        assert not out.exists()
        assert (tmp_path / "archive.pakem.part001").exists()

        restored = tmp_path / "restored"
        restore_packer = RepoPacker(
            str(restored),
            str(out),
            IgnoreRules.from_defaults(str(restored), None),
            FileWalker(
                str(restored), IgnoreRules.from_defaults(str(restored), None)
            ),
            output_format="pakem",
        )
        assert restore_packer.restore(str(out), str(restored)) == 0
        assert (restored / "a.txt").read_text() == "A" * 3000

    def test_restore_blocks_path_traversal(self, tmp_path):
        metadata = b'{"repository":{},"files":[{"path":"../evil.txt","payload_length":4}],"directories":[]}'
        payload = b"evil"
        out = tmp_path / "bad.pakem"
        out.write_bytes(
            b"PAKM"
            + bytes([1])
            + len(metadata).to_bytes(4, "big")
            + metadata
            + payload
        )

        restored = tmp_path / "restore"
        restore_packer = RepoPacker(
            str(restored),
            str(out),
            IgnoreRules.from_defaults(str(restored), None),
            FileWalker(
                str(restored), IgnoreRules.from_defaults(str(restored), None)
            ),
            output_format="pakem",
        )
        assert restore_packer.restore(str(out), str(restored)) == 1
        assert not (tmp_path / "evil.txt").exists()
