"""Tests for the pakem package."""

from pakem import RepoPacker, count_tokens, get_ignore_patterns, is_binary, should_ignore


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


class TestShouldIgnore:
    def test_gitignore_pattern(self):
        assert should_ignore("/root/__pycache__", "/root", ["__pycache__"]) is True

    def test_no_match(self):
        assert should_ignore("/root/src/main.py", "/root", ["__pycache__"]) is False

    def test_glob_pattern(self):
        assert should_ignore("/root/test.pyc", "/root", ["*.pyc"]) is True

    def test_directory_pattern(self):
        assert should_ignore("/root/build", "/root", ["build/"]) is True


class TestGetIgnorePatterns:
    def test_default_patterns(self, tmp_path):
        patterns = get_ignore_patterns(str(tmp_path), None)
        assert ".git" in patterns
        assert "__pycache__" in patterns

    def test_with_gitignore(self, tmp_path):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\ntemp/\n")
        patterns = get_ignore_patterns(str(tmp_path), None)
        assert "*.log" in patterns
        assert "temp/" in patterns

    def test_user_ignores(self, tmp_path):
        patterns = get_ignore_patterns(str(tmp_path), ["custom_pattern"])
        assert "custom_pattern" in patterns


class TestRepoPacker:
    def test_pack_creates_output(self, tmp_path):
        # Create a simple repo structure
        src = tmp_path / "src"
        src.mkdir()
        (src / "hello.py").write_text("print('hello')\n")
        out = tmp_path / "output.xml"

        packer = RepoPacker(str(tmp_path), str(out), None)
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

        packer = RepoPacker(str(tmp_path), str(out), None)
        packer.pack()

        content = out.read_text()
        assert "text.txt" in content
        assert "binary.bin" not in content

    def test_pack_respects_ignores(self, tmp_path):
        (tmp_path / "keep.py").write_text("keep")
        (tmp_path / "skip.log").write_text("skip")
        out = tmp_path / "output.xml"

        packer = RepoPacker(str(tmp_path), str(out), ["*.log"])
        packer.pack()

        content = out.read_text()
        assert "keep.py" in content
        assert "skip.log" not in content

    def test_pack_includes_metadata(self, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        out = tmp_path / "output.xml"

        packer = RepoPacker(str(tmp_path), str(out), None)
        packer.pack()

        content = out.read_text()
        assert 'total_files="1"' in content
        assert "tokens=" in content
        assert "lines=" in content
