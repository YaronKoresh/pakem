# pakem

A repository packer that generates XML representations of codebases for use with LLMs and code analysis tools.

## Features

- Packs an entire repository into a single XML file
- Respects `.gitignore` patterns and common ignore rules
- Skips binary files automatically
- Includes file metadata (size, tokens, line count)
- Token counting for LLM context estimation

## Installation

```bash
pip install pakem
```

## Usage

### Command Line

```bash
# Pack the current directory
pakem

# Pack a specific directory
pakem --path /path/to/repo

# Specify output file
pakem --path /path/to/repo --out output.xml

# Add additional ignore patterns
pakem --ignore "*.tmp" "secret_*"
```

You can also run it as a module:

```bash
python -m pakem --path /path/to/repo --out output.xml
```

### Python API

```python
from pakem import RepoPacker

packer = RepoPacker(
    root_dir="/path/to/repo",
    output_file="repo.xml",
    ignores=["*.tmp"]
)
packer.pack()
```

## Development

### Setup

```bash
git clone https://github.com/YaronKoresh/pakem.git
cd pakem
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Linting

```bash
ruff check .
```

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
