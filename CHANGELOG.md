# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-12-02

### Added
- Initial release
- Window tracking with rich metadata extraction
- OCR screen capture with multiple engine support:
  - Apple Vision (macOS) - Neural Engine accelerated
  - Windows OCR API (Windows) - Built-in, fast
  - RapidOCR - ONNX-based, cross-platform
  - Tesseract - Fallback option
- LLM-powered context extraction via Ollama:
  - Document name detection
  - Client code extraction
  - Project identification
  - URL and breadcrumb extraction
- Smart capture features:
  - Idle detection (macOS Quartz / Windows API)
  - OCR diff detection (skip unchanged content)
  - Adaptive polling (slower when idle)
  - Remote desktop detection with periodic capture
- Multi-monitor support
- Privacy controls:
  - App exclusions
  - Title pattern exclusions
  - Content redaction
- 150+ categorization rules
- RAG database integration (Qdrant) for client detection
- Browser extension for URL tracking
- Cross-platform support (macOS, Windows)
- Comprehensive documentation

### Supported Platforms
- macOS 11.0+ (Intel and Apple Silicon)
- Windows 10 (1903+) and Windows 11

### Dependencies
- Python 3.9+
- ActivityWatch
- Optional: Ollama for LLM enhancement
- Optional: Qdrant for RAG-based client detection
