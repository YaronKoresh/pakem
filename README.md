# pakem

`pakem` is a repository packaging system designed to convert source trees into portable artifacts for analysis, indexing, sharing, and restoration workflows.

It supports document-oriented outputs (`xml`, `json`, `proto`) and a binary archive format (`pakem`) with optional compression, reversible encryption, split output, incremental state tracking, and delta reporting.

---

## Table of Contents

1. [Mission and Scope](#mission-and-scope)
2. [Capability Matrix](#capability-matrix)
3. [System Architecture](#system-architecture)
4. [Data Flow and Control Flow](#data-flow-and-control-flow)
5. [Installation and Environment](#installation-and-environment)
6. [CLI Reference](#cli-reference)
7. [Output Formats and File Specifications](#output-formats-and-file-specifications)
8. [State, Delta, and Restore Semantics](#state-delta-and-restore-semantics)
9. [Security and Trust Model](#security-and-trust-model)
10. [Performance and Scalability Tuning](#performance-and-scalability-tuning)
11. [Validation and Quality Gates](#validation-and-quality-gates)
12. [Python API Usage](#python-api-usage)
13. [Operational Playbooks](#operational-playbooks)
14. [Troubleshooting](#troubleshooting)
15. [Module-by-Module Internals](#module-by-module-internals)
16. [Contributing and Release Workflow](#contributing-and-release-workflow)
17. [Glossary](#glossary)
18. [License](#license)

---

## Mission and Scope

`pakem` exists to solve one problem well:

- Scan a repository deterministically.
- Analyze textual source files.
- Serialize normalized metadata and content.
- Optionally track historical state for delta-oriented operations.
- Optionally emit a binary artifact that can be restored later.

### Primary Use Cases

| Use Case | Input | Output | Typical Consumer |
|---|---|---|---|
| LLM context packaging | Source repository | XML/JSON/Proto/LLM Prompt | Prompt pipelines, RAG preprocessors |
| Incremental repository snapshots | Source + state file | XML/JSON/Proto/Pakem + updated state | CI and scheduled jobs |
| Change-only artifact generation | Source + previous state + `--delta` | Delta subset + diff manifest | Review and sync automation |
| Archive and restore workflow | Source | `.pakem` (single or split) | Backup, transfer, migration |
| Archive-to-archive change analysis | Two artifacts | Added/modified/removed report | Regression triage and release validation |
| Cloud artifact transport | Local source + cloud URI (`s3://`, `gs://`, `az://`) | Artifact read/write over object storage | Remote backup and pipeline automation |
| Archive inspection and reporting | Existing artifact(s) | TUI/plain explorer and HTML diff report | Release engineering and audits |
| Ecosystem loaders | Existing artifact(s) | LangChain documents / LlamaIndex nodes | RAG and indexing services |
| Ignore-rule diagnostics | Source + ignore patterns/files | Printed ignored list | Build engineering and DevEx |

---

## Capability Matrix

| Capability | xml | json | proto | pakem | llm-prompt |
|---|---:|---:|---:|---:|---:|
| Full repository metadata | Yes | Yes | Yes | Yes |
| File line-level content | Yes | Yes | Yes | Packed payload | Structured prompt blocks |
| Incremental state tracking (`--state`) | Yes | Yes | Yes | Yes |
| Delta mode (`--delta`) | Yes | Yes | Yes | Yes |
| Diff manifest output (`diff --diff-out`) | Yes | Yes | Yes | Yes |
| HTML diff report (`--html-diff-out` / `archive-diff --html-out`) | Yes | Yes | Yes | Yes |
| Optional compression (`--compress zlib/zstd/lz4`) | No | No | No | Yes |
| Optional reversible encryption (`--encrypt-key`) | No | No | No | Yes |
| Optional split output (`--split-size`) | No | No | No | Yes |
| Chunk-level dedup (`--dedup-chunks`) | No | No | No | Yes |
| Restore support (`restore`) | No | No | No | Yes | No |
| Semantic chunking (`--semantic-chunking`) | Yes | Yes | Yes | Yes | Yes |
| Git tracked-files mode (`--tracked-files`) | Yes | Yes | Yes | Yes | Yes |
| Distributed shard filtering (`--distributed-shards` + `--distributed-index`) | Yes | Yes | Yes | Yes | Yes |
| Analysis cache mode (`--cache-mode`) | Yes | Yes | Yes | Yes | Yes |
| Cloud URI output/input (`s3://`, `gs://`, `az://`) | Yes | Yes | Yes | Yes | Yes |

---

## System Architecture

### High-Level Module Topology

```mermaid
flowchart TB
    CLI[cli.py] --> CMD[commands.py]
    CMD --> PACKER[packer.py]
    PACKER --> FS[fs.py]
    PACKER --> ANALYZE[analyze.py]
    PACKER --> STATE[state.py]
    PACKER --> SERIALIZE[serialize.py]
    PACKER --> VALIDATE[validation.py]
    ANALYZE --> TOKEN[tokenizer.py]
    FS --> IGNORE[ignore.py]
```

### Command Dispatch Model

```mermaid
flowchart LR
    A[argv] --> B{normalize argv}
    B -->|no subcommand| C[prepend pack]
    B -->|has subcommand| D[keep argv]
    C --> E[argparse subparsers]
    D --> E[argparse subparsers]
    E --> F{command}
    F -->|pack| G[PackCommand.execute]
    F -->|diff| H[DiffCommand.execute]
    F -->|restore| I[RestoreCommand.execute]
    F -->|archive-diff| J[ArchiveDiffCommand.execute]
    F -->|explore| K[ExploreCommand.execute]
    F -->|setup-precommit| L[SetupPrecommitCommand.execute]
```

### Packing Execution Pipeline

```mermaid
flowchart TD
    START[RepoPacker.pack] --> SR[start_repository]
    SR --> WALK[walk file tree]
    WALK --> FILTER[ignore + binary filter]
    FILTER --> ANALYSIS[parallel analyze_entry]
    ANALYSIS --> STATEUPD[update current state]
    STATEUPD --> SERIAL[serializer.add_file]
    SERIAL --> PAYLOAD[optional pakem payload transforms]
    PAYLOAD --> ENDREP[end_repository]
    ENDREP --> TOTALS[update totals]
    TOTALS --> WRITE[serializer.write_to]
    WRITE --> SAVE[state save if configured]
    SAVE --> DONE[exit code 0]
```

---

## Data Flow and Control Flow

### Pack Command Data Contract

| Stage | Input | Output | Invariants |
|---|---|---|---|
| Argument resolution | CLI options | `Namespace` | Subcommand is one of `pack`, `diff`, `restore`, `archive-diff`, `explore`, `setup-precommit` |
| Output path resolution | `--out`, `--format` | concrete file path or cloud URI | If `--out` has no suffix, suffix is inferred by format |
| File walk | root + ignore rules | `FileEntry` stream | Relative paths normalized to `/` |
| Text analysis | file path | `FileMetadata` + content lines | Binary files are skipped |
| State update | previous state + file hash | current state | Each processed text file gets deterministic state entry |
| Serialization | metadata + lines | format artifact | Repository totals updated at end |

### Restore Command Data Contract

| Stage | Input | Output | Invariants |
|---|---|---|---|
| Artifact read | `.pakem` or split parts | bytes | Header must start with `PAKM` |
| Header parse | artifact bytes | metadata JSON + payload bytes | Version byte must be supported by negotiation metadata |
| Chunk reconstruction | payload stream + per-file lengths | file bytes | Transform reversal is inverse of transform order |
| Write stage | `target_dir` + relative path | restored files | Path traversal outside target is rejected |

---

## Installation and Environment

### Minimal Installation

```bash
pip install pakem
```

### Development Installation

```bash
git clone https://github.com/YaronKoresh/pakem.git
cd pakem
pip install -e ".[dev]"
```

### Optional Extras

Install optional extras when needed:

```bash
pip install -e ".[extra]"
```

Extras currently include:

| Package | Enables |
|---|---|
| `pathspec` | Advanced gitignore-style pattern matching |
| `tiktoken` | Model-aware token counting |
| `protobuf` | Proto serializer support |
| `dulwich` | Git-native tracked-files and metadata enrichment |
| `zstandard` | zstd compression profile |
| `lz4` | lz4 compression profile |
| `fsspec` + cloud FS plugins (`s3fs`, `gcsfs`, `adlfs`) | Cloud URI read/write for artifacts and reports |
| `langchain` | LangChain loader adapter |
| `llama-index` | LlamaIndex reader adapter |

### Runtime Requirements

| Requirement | Value |
|---|---|
| Python | `>=3.10` |
| Project version | `2.0.0` |
| Entry point | `pakem = pakem.cli:main` |

---

## CLI Reference

## Global Invocation Forms

```bash
pakem <subcommand> [options]
python -m pakem <subcommand> [options]
```

If no subcommand is supplied, `pack` is implicitly used.

## `pack` Command

```bash
pakem pack [--path PATH] [--out OUT] [--format {xml,json,proto,pakem,llm-prompt}]
```

### `pack` Options Table

| Option | Type | Default | Description |
|---|---|---|---|
| `--path` | string | `.` | Root directory to process |
| `--out` | string | `repo` | Output path or base name |
| `--ignore` | list[string] | none | Additional ignore patterns |
| `--include` | list[string] | none | Allowlist patterns; only matching paths are considered |
| `--tracked-files` | flag | `false` | Only include files tracked in git index |
| `--git-metadata` | flag | `false` | Enrich file metadata with commit hash/author/date |
| `--semantic-chunking` | flag | `false` | Preserve class/function boundaries when rendering file content |
| `--summary-mode` | enum | `off` | Optional low-priority summarization mode |
| `--plugin` | list[string] | none | Optional plugin module paths loaded before execution |
| `--cache-mode` | enum | `off` | Analysis cache mode (`off|local|memory`) |
| `--dedup-chunks` | flag | `false` | Enable chunk-level deduplication for pakem payloads |
| `--distributed-shards` | int | none | Total number of shards for distributed packing |
| `--distributed-index` | int | none | Zero-based shard index for this run |
| `--ignore-file` | string | none | Path to extra ignore file |
| `--state` | string | none | JSON state file path |
| `--delta` | flag | `false` | Include only changed files |
| `--max-file-size` | size | none | Skip files larger than this threshold (`512KB`, `10MB`, `1GB`) |
| `--max-total-tokens` | int | none | Cap packaged token total across selected files |
| `--dry-run` | flag | `false` | Analyze and report without writing package/state/report files |
| `--focus-ranking` | enum | `basic` | Ranking strategy used when token budget is constrained |
| `--list-ignored` | flag | `false` | Print ignored entries and exit |
| `--model` | string | none | Tokenization model hint |
| `--workers` | int | auto | Analysis worker count (positive integer) |
| `--format` | enum | `xml` | Output format |
| `--emit-schema` | string | none | Schema output path |
| `--schema-format` | enum | `xml` | Schema format |
| `--compress` | enum | `none` | pakem payload compression |
| `--encrypt-key` | string | none | pakem reversible key |
| `--cipher` | enum | `aes-gcm` | Encryption profile for pakem payload encryption |
| `--sign-key` | string | none | Optional provenance signature key (`hmac-sha256`) |
| `--split-size` | size | none | pakem split threshold (`1MB`, `512KB`, `2GB`) |
| `--sensitive-data-policy` | enum | `off` | Sensitive data handling mode (`off|warn|redact|block`) |
| `--secret-scanner` | enum | `builtin` | Secret scanner integration mode (`builtin|gitleaks|trufflehog|auto|off`) |
| `--sensitive-report-out` | string | none | Optional JSON report output for sensitive-data findings |
| `--selection-report-out` | string | none | Optional JSON report with selected and skipped paths |

### `pack` Examples

```bash
# Default pack in current directory (implicit .xml suffix)
pakem pack

# Explicit format with auto extension
pakem pack --path ./repo --format json --out snapshot

# Delta pack using state file
pakem pack --path ./repo --state .pakem-state.json --delta --out delta-report

# Focused pack with include allowlist and token budget
pakem pack --path ./repo --include "src/**" --max-total-tokens 20000 --focus-ranking basic --out focused

# Analysis-only pass with no artifact writes
pakem pack --path ./repo --dry-run --max-file-size 1048576

# pakem archive with payload transforms and splitting
pakem pack --path ./repo --format pakem --compress zlib --encrypt-key key123 --split-size 1048576 --out archive

# LLM prompt profile with semantic chunking
pakem pack --path ./repo --format llm-prompt --semantic-chunking --summary-mode basic --out prompt
```

## `diff` Command

```bash
pakem diff --state STATE [--path PATH] [--out OUT] [--diff-out FILE]
```

### `diff` Options Table

| Option | Type | Required | Description |
|---|---|---:|---|
| `--state` | string | Yes | Existing state file to compare against |
| `--path` | string | No | Root directory (default `.`) |
| `--out` | string | No | Artifact output base/path |
| `--diff-out` | string | No | JSON diff manifest output path |
| `--html-diff-out` | string | No | HTML diff report output path |
| `--ignore` | list[string] | No | Additional ignore patterns |
| `--include` | list[string] | No | Allowlist patterns; only matching paths are considered |
| `--tracked-files` | flag | No | Only include files tracked in git index |
| `--git-metadata` | flag | No | Enrich file metadata with commit hash/author/date |
| `--semantic-chunking` | flag | No | Preserve class/function boundaries when rendering file content |
| `--summary-mode` | enum | No | Optional low-priority summarization mode |
| `--plugin` | list[string] | No | Optional plugin module paths loaded before execution |
| `--cache-mode` | enum | No | Analysis cache mode (`off|local|memory`) |
| `--dedup-chunks` | flag | No | Enable chunk-level deduplication for pakem payloads |
| `--distributed-shards` | int | No | Total number of shards for distributed packing |
| `--distributed-index` | int | No | Zero-based shard index for this run |
| `--ignore-file` | string | No | Extra ignore file |
| `--format` | enum | No | Output format |
| `--max-file-size` | size | No | Skip files larger than this threshold (`512KB`, `10MB`, `1GB`) |
| `--max-total-tokens` | int | No | Cap packaged token total across selected files |
| `--dry-run` | flag | No | Analyze without writing package or diff output files |
| `--focus-ranking` | enum | No | Ranking strategy used when token budget is constrained |
| `--selection-report-out` | string | No | Optional JSON report with selected and skipped paths |
| `--secret-scanner` | enum | No | Secret scanner integration mode (`builtin|gitleaks|trufflehog|auto|off`) |

Constraint semantics:

- `--max-file-size` and `--max-total-tokens` define the selected scope.
- Selected scope is used consistently for artifact content, persisted state entries, and `diff` output.
- Runtime stats include skip counters for max-file-size and token-budget exclusions.
- `--selection-report-out` emits selected paths and skip reasons for automation and audits.
- Size arguments accept case-insensitive suffixes: `B`, `KB`, `MB`, `GB`, `TB`.

State backend semantics:

- File backend (default): pass a normal path to `--state`.
- Memory backend: `--state memory://<key>`.
- SQLite backend: `--state sqlite:///path/to/state.db?key=<state-key>`.

Archive negotiation and provenance:

- pakem archives include `min_reader_version` and `max_reader_version` metadata.
- Optional signatures use `--sign-key` during pack and `--verify-signature-key` during restore.
- Restore rejects signature mismatches and incompatible negotiation ranges.

Pack option compatibility:

- `--compress`, `--encrypt-key`, and `--split-size` are valid only with `--format pakem`.
- `--cipher` customization is valid only with `--format pakem`.
- `--cipher none` cannot be combined with `--encrypt-key`.

### `diff` Output Schema

If `--diff-out` is provided, JSON shape is:

```json
{
  "added": ["..."],
  "modified": ["..."],
  "removed": ["..."]
}
```

## `restore` Command

```bash
pakem restore --in ARCHIVE --target TARGET [--format pakem] [--compress {none,zlib,zstd,lz4}] [--encrypt-key KEY]
```

### `restore` Notes

- Supports `.pakem` artifacts and split sequences (`.pakem.part001`, `.part002`, ...).
- Uses metadata `payload_length` values to reconstruct file payload boundaries.
- Rejects writes that resolve outside `--target`.

## `archive-diff` Command

```bash
pakem archive-diff --left OLD --right NEW [--left-format FMT] [--right-format FMT] [--out OUT] [--html-out REPORT.html]
```

Produces deterministic added/modified/removed results without scanning a live repository.

## `explore` Command

```bash
pakem explore --in ARCHIVE [--tui]
```

Inspects archive entries either with plain terminal output or a curses-based TUI (`--tui`).

## `setup-precommit` Command

```bash
pakem setup-precommit [--path PATH] [--force]
```

Generates `.pre-commit-config.yaml` with `ruff`, `ruff-format`, and a local `poe check` hook.

---

## Output Formats and File Specifications

## Extension Auto-Selection

When `--out` has no suffix:

| Format | Applied Suffix |
|---|---|
| `xml` | `.xml` |
| `json` | `.json` |
| `proto` | `.pb` |
| `pakem` | `.pakem` |
| `llm-prompt` | `.prompt.md` |

If `--out` already has a suffix, it is preserved.

## XML and JSON

Both represent repository metadata, directory records, and file records. XML uses nested elements, JSON uses structured objects.

## Protobuf

Protobuf uses dynamic message generation from `pakem.proto` descriptor construction at runtime.

## pakem Binary Container

### Binary Layout

| Segment | Size | Description |
|---|---:|---|
| Magic | 4 bytes | ASCII `PAKM` |
| Version | 1 byte | Current value: `2` |
| Header length | 4 bytes (big-endian) | Byte length of metadata JSON |
| Metadata | variable | UTF-8 JSON with repository/file descriptors |
| Payload | variable | Concatenated file payload chunks |

### Metadata Core Keys

| Key | Type | Description |
|---|---|---|
| `repository` | object | Root metadata, totals, timestamp |
| `directories` | array | Optional directory entries |
| `files` | array | File descriptors including `payload_length` |
| `payload_size` | int | Total payload bytes |

### Split Output Behavior

If final blob size exceeds `--split-size`, writer emits:

- `name.pakem.part001`
- `name.pakem.part002`
- ...

No root `.pakem` file is emitted in split mode.

---

## State, Delta, and Restore Semantics

## State Model

State file stores:

| Field | Type | Description |
|---|---|---|
| `version` | int | Schema version, current default is `2` |
| `files` | object map | `rel_path -> {mtime, size, sha256}` |

Legacy state without `version` loads as version `1`.

## Delta Computation

`RepoState.diff_paths(new_state)` returns sorted path lists for:

- `added`
- `modified`
- `removed`

In delta mode:

- unchanged files are not serialized into output payload
- serializer repository metadata can include a `delta` block

## Restore Semantics

Restore requires `pakem` format and follows this inversion logic:

1. Parse header and metadata.
2. Slice payload by `payload_length` per file.
3. Reverse encryption (if key supplied).
4. Reverse compression (`zlib`) if enabled.
5. Validate target path safety.
6. Write file bytes.

---

## Security and Trust Model

## Current Security Controls

| Control | Status | Description |
|---|---|---|
| Path traversal prevention | Enabled | Restore checks target path boundaries via realpath/commonpath logic |
| Format sanity checks | Enabled | `validate_pakem` checks magic/version/header consistency |
| Binary detection | Enabled | Binary files skipped during source pack stage |

## Important Cryptography Note

Default encryption profiles are authenticated encryption (`aes-gcm` and `chacha20-poly1305`) with metadata-bound authentication.

Legacy reversible xor mode is available only under explicit legacy mode for restoration compatibility paths.

---

## Performance and Scalability Tuning

## Worker Strategy

By default, worker count is derived from CPU count (`cpu_count * 4` minimum 1).

Guidance:

| Repository profile | Suggested `--workers` |
|---|---:|
| Small (<5k files) | auto |
| Medium (5k-50k files) | 8-16 |
| Large monorepo | 16-32 (validate host IO limits) |

## Throughput Considerations

| Factor | Impact |
|---|---|
| Binary file prevalence | More binaries means faster total run due to skip behavior |
| Tokenizer backend | `tiktoken` can improve model parity; regex fallback avoids dependency |
| State availability | Existing state can reduce expensive hash recompute paths |
| Analysis cache mode | `local` and `memory` cache reduce repeated analysis work |
| mmap hashing | Large-file hashing uses mmap when available for lower memory churn |
| Pakem transforms | Compression and encryption increase CPU load |

## Flowchart: Performance Path

```mermaid
flowchart TD
    A[File discovered] --> B{binary?}
    B -->|yes| C[skip]
    B -->|no| D[analyze + hash]
    D --> E{delta + unchanged?}
    E -->|yes| F[exclude from artifact]
    E -->|no| G[serialize]
    G --> H{format pakem?}
    H -->|no| I[write structured output]
    H -->|yes| J[compress/encrypt/split]
```

---

## Validation and Quality Gates

## Built-in Validators

| Validator | Target |
|---|---|
| `validate_xml(path)` | XML artifacts |
| `validate_json(path)` | JSON artifacts |
| `validate_proto(path)` | Proto artifacts |
| `validate_pakem(path)` | pakem binary artifacts |
| `validate(path, format=None)` | Format inference + dispatch |

## Project Quality Commands

| Goal | Command |
|---|---|
| Run tests | `pytest -q` |
| Run linter | `ruff check .` |
| Compile check | `python -m compileall -q .` |
| All checks (poe) | `poe check` |

---

## Python API Usage

## Basic Pack

```python
from pakem import IgnoreRules, RepoPacker
from pakem.fs import FileWalker

root = "/path/to/repo"
out = "repo.xml"

rules = IgnoreRules.from_defaults(root, extra_patterns=["*.tmp"])
walker = FileWalker(root, rules, output_path=out)

packer = RepoPacker(
    root_dir=root,
    output_file=out,
    ignore_rules=rules,
    walker=walker,
    output_format="xml",
)

exit_code = packer.pack()
print(exit_code)
```

## Advanced Pack (pakem)

```python
from pakem import IgnoreRules, RepoPacker
from pakem.fs import FileWalker

root = "/path/to/repo"
out = "archive.pakem"

rules = IgnoreRules.from_defaults(root)
walker = FileWalker(root, rules, output_path=out)

packer = RepoPacker(
    root_dir=root,
    output_file=out,
    ignore_rules=rules,
    walker=walker,
    state_path=".pakem-state.json",
    delta=True,
    output_format="pakem",
    compression="zlib",
    encryption_key="demo-key",
    split_size=2_000_000,
)

packer.pack()
```

## Restore via API

```python
from pakem import IgnoreRules, RepoPacker
from pakem.fs import FileWalker

target = "./restored"
rules = IgnoreRules.from_defaults(target)

packer = RepoPacker(
    root_dir=target,
    output_file="archive.pakem",
    ignore_rules=rules,
    walker=FileWalker(target, rules),
    output_format="pakem",
    compression="zlib",
    encryption_key="demo-key",
)

packer.restore("archive.pakem", target)
```

---

## Operational Playbooks

## Playbook A: Daily Incremental Snapshot

```mermaid
flowchart LR
    A[Load previous state] --> B[Run pack --delta]
    B --> C[Publish artifact]
    C --> D[Store new state]
    D --> E[Run validate]
```

Steps:

1. Keep a persistent state file per repository.
2. Run `pakem pack --state state.json --delta`.
3. Store resulting artifact and updated state file together.
4. Optionally run `pakem diff --state state.json --diff-out diff.json` for change reports.

## Playbook B: Transfer as Split Binary

1. `pakem pack --format pakem --split-size 1048576 --out archive`
2. Transfer all `.partNNN` files.
3. Restore with:
   `pakem restore --in archive.pakem --target ./target`

## Playbook C: Ignore Rules Debug Session

1. Add new patterns via `--ignore` or `--ignore-file`.
2. Execute `pakem pack --list-ignored --path ...`.
3. Validate expected paths appear in output list.

---

## Troubleshooting

| Symptom | Likely Cause | Corrective Action |
|---|---|---|
| `restore` returns `1` with no files | Wrong format or invalid magic/header | Verify archive starts with `PAKM`, run `validate_pakem` |
| Missing expected files in output | Ignore rules filtering them | Use `--list-ignored` and adjust patterns |
| Output extension not what you expected | `--out` had explicit suffix | Remove suffix from `--out` to use auto-extension |
| Token counts seem generic | `tiktoken` not installed or model unsupported | Install extras and pass `--model` |
| Delta output too large | State file missing or stale | Keep state persisted and scoped per repository |
| Split archive not restoring | Part files missing/out of order | Ensure contiguous `.partNNN` files are present |

### Diagnostic Commands

```bash
# Check lints and imports
ruff check .

# Verify runtime behavior
pytest -q

# Validate artifact (Python snippet)
python -c "from pakem.validation import validate; validate('archive.pakem', 'pakem')"
```

---

## Module-by-Module Internals

| Module | Responsibility | Key Types/Functions |
|---|---|---|
| `pakem/cli.py` | Argument parsing and subcommand routing | `main`, `resolve_output_path` |
| `pakem/commands.py` | Command execution adapters | `PackCommand`, `DiffCommand`, `RestoreCommand`, `ArchiveDiffCommand`, `ExploreCommand`, `SetupPrecommitCommand` |
| `pakem/packer.py` | Core orchestration pipeline | `RepoPacker.pack`, `RepoPacker.diff`, `RepoPacker.restore` |
| `pakem/fs.py` | Deterministic file traversal | `FileWalker`, `FileEntry` |
| `pakem/ignore.py` | Ignore pattern loading and matching | `IgnoreRules` |
| `pakem/analyze.py` | Metadata extraction and token/line counting | `FileMetadata`, `analyze_text` |
| `pakem/tokenizer.py` | Token counting backends | `RegexTokenCounter`, `TiktokenTokenCounter` |
| `pakem/state.py` | Incremental file state and diffs | `RepoState`, `FileState`, `diff_paths` |
| `pakem/serialize.py` | XML/JSON/Proto/Pakem serializers | `XmlSerializer`, `JsonSerializer`, `ProtoSerializer`, `PakemSerializer` |
| `pakem/cloud_io.py` | Local/cloud read-write abstraction | `read_bytes`, `write_text`, `write_bytes` |
| `pakem/cache.py` | Analysis cache backends | `AnalysisCache`, `create_cache` |
| `pakem/plugins.py` | Runtime plugin loading | `load_plugins`, `register_analyzer` |
| `pakem/reports.py` | HTML reporting | `render_html_diff_report` |
| `pakem/loaders.py` | Ecosystem data loaders | `PakemLangChainLoader`, `PakemLlamaIndexReader` |
| `pakem/tui.py` | Archive exploration UI | `explore_archive` |
| `pakem/validation.py` | Artifact validation and path safety | `validate`, `validate_pakem`, `is_path_safe` |
| `pakem/proto.py` | Dynamic protobuf schema descriptor | `get_repository_message_class` |

---

## Contributing and Release Workflow

## Development Workflow

```bash
pip install -e ".[dev,extra]"
ruff check .
pytest -q
```

## Suggested Pull Request Checklist

| Check | Status |
|---|---|
| New behavior covered by tests | Required |
| Lint passes (`ruff check .`) | Required |
| README updated for CLI/API changes | Required |
| Backward compatibility considered | Recommended |
| State/format migrations documented | Recommended |

## Packaging Tasks

| Task | Command |
|---|---|
| Build source + wheel | `poe build` |
| Build wheel only | `poe build-wheel` |
| Install pre-commit hooks | `poe hook` |

---

## Glossary

| Term | Meaning |
|---|---|
| Artifact | Final output file(s) produced by a run |
| Delta mode | Serialization of only changed files relative to previous state |
| State file | JSON map of file path to mtime/size/hash used for incremental processing |
| Payload length | Byte length of one file's serialized bytes inside pakem payload stream |
| Split archive | Multi-part output generated when blob exceeds `--split-size` |

---

## License

This project is licensed under the GNU General Public License v3.0 or later.

See [LICENSE](LICENSE) for full terms.
