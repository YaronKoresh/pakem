from pakem import (
    IgnoreRules,
    RepoPacker,
    count_tokens,
    is_binary,
)
from pakem.cli import _normalize_argv, resolve_output_path
from pakem.fs import FileWalker
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


class TestCliBehavior:
    def test_format_changes_default_extension(self):
        assert resolve_output_path("repo", "json") == "repo.json"
        assert resolve_output_path("repo", "xml") == "repo.xml"
        assert resolve_output_path("repo", "proto") == "repo.pb"
        assert resolve_output_path("repo", "pakem") == "repo.pakem"

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


class TestPakemValidation:
    def test_validate_pakem_success(self, tmp_path):
        out = tmp_path / "ok.pakem"
        metadata = b'{"repository":{},"files":[],"directories":[]}'
        out.write_bytes(
            b"PAKM" + bytes([1]) + len(metadata).to_bytes(4, "big") + metadata
        )
        validate_pakem(str(out))

    def test_validate_pakem_failure(self, tmp_path):
        import pytest

        out = tmp_path / "bad.pakem"
        out.write_bytes(b"BAD!" + bytes([1]) + (2).to_bytes(4, "big") + b"{}")
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
        )
        assert restore_packer.restore(str(out), str(restored)) == 0
        assert (restored / "a.txt").read_text() == "alpha"
        assert (restored / "b.txt").read_text() == "beta"

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
