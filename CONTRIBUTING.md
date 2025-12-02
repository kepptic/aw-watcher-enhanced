# Contributing to aw-watcher-enhanced

Thank you for your interest in contributing to aw-watcher-enhanced! This document provides guidelines and information for contributors.

## Getting Started

### Development Setup

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/aw-watcher-enhanced.git
   cd aw-watcher-enhanced
   ```

3. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
   ```

4. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   
   # Platform-specific
   pip install -e ".[macos]"   # macOS
   pip install -e ".[windows]" # Windows
   ```

5. Install pre-commit hooks (optional but recommended):
   ```bash
   pip install pre-commit
   pre-commit install
   ```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=aw_watcher_enhanced

# Run specific test file
pytest tests/test_ocr.py
```

### Code Style

We use the following tools for code quality:

- **Black** for code formatting
- **Ruff** for linting
- **MyPy** for type checking

```bash
# Format code
black aw_watcher_enhanced

# Lint
ruff check aw_watcher_enhanced

# Type check
mypy aw_watcher_enhanced
```

## How to Contribute

### Reporting Bugs

1. Check existing [issues](https://github.com/kepptic/aw-watcher-enhanced/issues) to avoid duplicates
2. Use the bug report template
3. Include:
   - OS and version
   - Python version
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant logs (with `--verbose` flag)

### Suggesting Features

1. Check existing issues and discussions
2. Open a new issue with the "feature request" label
3. Describe:
   - The problem you're trying to solve
   - Your proposed solution
   - Alternative solutions considered

### Pull Requests

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following our code style

3. Add tests for new functionality

4. Update documentation if needed

5. Run tests and linting:
   ```bash
   pytest
   black aw_watcher_enhanced
   ruff check aw_watcher_enhanced
   ```

6. Commit with clear messages:
   ```bash
   git commit -m "Add feature: description of what was added"
   ```

7. Push and create a pull request

### Commit Message Format

Use clear, descriptive commit messages:

```
<type>: <short summary>

<optional longer description>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat: Add RapidOCR support for Windows
fix: Handle empty OCR results gracefully
docs: Update Windows installation guide
```

## Project Structure

```
aw-watcher-enhanced/
├── aw_watcher_enhanced/     # Main package
│   ├── __init__.py
│   ├── main.py              # Entry point and main loop
│   ├── config.py            # Configuration management
│   ├── window.py            # Window capture (cross-platform)
│   ├── ocr.py               # OCR engines and capture
│   ├── llm_ocr.py           # LLM integration (Ollama)
│   ├── smart_capture.py     # Idle detection, diff detection
│   ├── document.py          # Document context extraction
│   ├── categorizer.py       # Activity categorization
│   ├── privacy.py           # Privacy filtering
│   ├── rag_client.py        # RAG database integration
│   └── rules/               # Categorization rules
├── browser-extension/       # Chrome/Firefox extension
├── docs/                    # Documentation
├── installer/               # Platform installers
├── tests/                   # Unit tests
├── pyproject.toml           # Project configuration
└── README.md
```

## Adding a New OCR Engine

1. Add detection logic in `ocr.py`:
   ```python
   if not OCR_AVAILABLE:
       try:
           from your_ocr_library import OCR
           OCR_AVAILABLE = True
           OCR_ENGINE = "your_engine"
           logger.info("Using Your OCR Engine")
       except ImportError:
           pass
   ```

2. Implement the OCR function:
   ```python
   def _ocr_your_engine(image) -> str:
       """OCR using Your Engine."""
       try:
           # Your implementation
           return text
       except Exception as e:
           logger.error(f"Your OCR failed: {e}")
           return ""
   ```

3. Add to `ocr_image()` function:
   ```python
   elif engine == "your_engine":
       return _ocr_your_engine(image)
   ```

4. Add to config options in `config.py`

5. Add tests in `tests/test_ocr.py`

6. Update documentation

## Adding Platform Support

When adding support for a new platform:

1. Add platform detection in relevant modules
2. Implement platform-specific functions with `_function_platform()` naming
3. Add optional dependencies in `pyproject.toml`
4. Create installation documentation in `docs/INSTALL-<platform>.md`
5. Add tests with platform skips where needed

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help newcomers learn
- Keep discussions on-topic

## Questions?

- Open a [Discussion](https://github.com/kepptic/aw-watcher-enhanced/discussions) for questions
- Check existing documentation first
- Tag maintainers if urgent

Thank you for contributing!
