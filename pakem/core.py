import argparse
import datetime
import fnmatch
import os
import re


def get_ignore_patterns(root_dir, user_ignores):
    patterns = [
        ".git",
        ".vscode",
        ".idea",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "venv",
        ".env",
        ".DS_Store",
        "*.lock",
        "*.log",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.gif",
        "*.svg",
        "*.ico",
        "*.zip",
        "*.tar",
        "*.gz",
        "*.pdf",
        "*.bin",
        "*.exe",
        "*.pyc",
        "*.so",
        "*.dll",
        "*.class",
    ]

    gitignore_path = os.path.join(root_dir, ".gitignore")
    if os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception:
            pass

    if user_ignores:
        patterns.extend(user_ignores)
    return patterns


def should_ignore(path, root_dir, patterns):
    rel_path = os.path.relpath(path, root_dir)
    name = os.path.basename(path)

    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path, pattern):
            return True
        if pattern.endswith("/") and fnmatch.fnmatch(rel_path + "/", pattern):
            return True
    return False


def is_binary(file_path):
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            return b"\0" in chunk
    except Exception:
        return True


def count_tokens(text):
    if not text:
        return 0

    pat = re.compile(
        r"""(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\w]?(?:[a-zA-Z_]\w*)+"""
        r"""|\d{1,3}| ?[^\s\w]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"""
    )

    return len(pat.findall(text))


def get_file_info(path):
    stats = os.stat(path)
    return {
        "size": stats.st_size,
        "mtime": datetime.datetime.fromtimestamp(stats.st_mtime).isoformat(),
    }


class RepoPacker:
    def __init__(self, root_dir, output_file, ignores):
        self.root_dir = os.path.abspath(root_dir)
        self.output_file = os.path.abspath(output_file)
        self.patterns = get_ignore_patterns(self.root_dir, ignores)
        self.total_files = 0
        self.total_tokens = 0
        self.total_size = 0
        self.xml_content = []

    def pack(self):
        print(f"📦 Packing repository: {self.root_dir}")

        self.xml_content.append('<?xml version="1.0" encoding="UTF-8"?>\n')
        self.xml_content.append(f'<repository root="{self.root_dir}">\n')

        self._process_directory(self.root_dir, depth=1)

        self.xml_content.append("</repository>")

        full_content_temp = "".join(self.xml_content)
        self.total_size = len(full_content_temp.encode("utf-8"))
        self.total_tokens = count_tokens(full_content_temp)

        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S GMT"
        )
        self.xml_content[1] = (
            f'<repository root="{self.root_dir}" '
            f'timestamp="{timestamp}" '
            f'total_files="{self.total_files}" '
            f'total_size="{self.total_size}" '
            f'total_tokens="{self.total_tokens}">\n'
        )

        full_content = "".join(self.xml_content)

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(full_content)

        print("✅ Done! Stats:")
        print(f"   Files:  {self.total_files}")
        print(f"   Size:   {self.total_size / 1024:.2f} KB")
        print(f"   Tokens: {self.total_tokens}")
        print(f"   Output: {self.output_file}")

    def _process_directory(self, current_path, depth):
        try:
            items = os.listdir(current_path)
        except PermissionError:
            return

        items.sort()
        indent = "  " * depth

        for item in items:
            full_path = os.path.join(current_path, item)

            if full_path == self.output_file:
                continue
            if should_ignore(full_path, self.root_dir, self.patterns):
                continue

            rel_path = os.path.relpath(full_path, self.root_dir)

            if os.path.isdir(full_path):
                self.xml_content.append(
                    f'{indent}<directory name="{item}" path="{rel_path}" depth="{depth}">\n'
                )
                self._process_directory(full_path, depth + 1)
                self.xml_content.append(f"{indent}</directory>\n")

            elif os.path.isfile(full_path):
                if is_binary(full_path):
                    continue
                self._process_file(full_path, item, rel_path, indent, depth)

    def _process_file(self, path, name, rel_path, indent, depth):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()

            info = get_file_info(path)
            tokens = count_tokens(content)
            lines = content.splitlines()
            extension = os.path.splitext(name)[1].lower()

            self.total_files += 1

            file_attrs = (
                f'name="{name}" path="{rel_path}" size="{info["size"]}"'
                f' tokens="{tokens}" type="file" extension="{extension}"'
                f' lines="{len(lines)}" depth="{depth}"'
            )
            self.xml_content.append(f"{indent}<file {file_attrs}>\n")

            for i, line in enumerate(lines, 1):
                safe_line = line.replace("]]>", "]]]]><![CDATA[>")
                length = len(line)
                leading_ws = length - len(line.lstrip())

                line_attrs = (
                    f'index="{i}" length="{length}" indentation="{leading_ws}"'
                )
                self.xml_content.append(
                    f"{indent}  <line {line_attrs}><![CDATA[{safe_line}]]></line>\n"
                )

            self.xml_content.append(f"{indent}</file>\n")

        except Exception as e:
            print(f"⚠️ Error reading {path}: {e}")


def main():
    """CLI entry point for pakem."""
    parser = argparse.ArgumentParser(
        description="Pack a repository into an XML representation."
    )
    parser.add_argument("--path", default=".", help="Root directory to pack")
    parser.add_argument(
        "--out", default="repo.xml", help="Output XML file path"
    )
    parser.add_argument(
        "--ignore", nargs="*", help="Additional ignore patterns"
    )
    args = parser.parse_args()

    packer = RepoPacker(args.path, args.out, args.ignore)
    packer.pack()


if __name__ == "__main__":
    main()
