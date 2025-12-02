"""
LLM-based screen analysis for aw-watcher-enhanced.

Uses vision LLMs to extract rich context from screen captures:
- What application/task is the user working on
- Document names, project context
- Key activities being performed
- Client/project detection

Supports multiple backends:
- Ollama (local, free) - moondream, llava, etc.
- Claude Haiku (fast cloud option)
- OpenAI GPT-4o-mini (fast cloud option)
"""

import base64
import json
import logging
import os
import time
from io import BytesIO
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Available LLM backends
LLM_BACKENDS = {
    "ollama": {
        "models": ["moondream", "llava", "llava-llama3", "bakllava"],
        "default": "moondream",
    },
    "claude": {
        "models": ["claude-3-haiku-20240307", "claude-3-5-sonnet-20241022"],
        "default": "claude-3-haiku-20240307",
    },
    "openai": {
        "models": ["gpt-4o-mini", "gpt-4o"],
        "default": "gpt-4o-mini",
    },
}

# Fast prompt for screen analysis
SCREEN_ANALYSIS_PROMPT = """Analyze this screenshot and respond with ONLY a JSON object (no markdown, no explanation):

{
  "app": "main application name",
  "task": "brief task description (2-5 words)",
  "document": "document/file name if visible",
  "project": "project name if identifiable",
  "client": "client name if visible",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "category": "Work/Development|Work/Communication|Work/Documentation|Personal|Other"
}

Be concise. If something is not visible, use null."""

# Prompt for text-based LLM to summarize OCR output (few-shot for better accuracy)
TEXT_SUMMARIZE_PROMPT = """Extract what the user is working on from screen text.

- document: filename, webpage title, repo name, or task from [TITLE BAR]
- client: Client Code, CLIENT:, company in breadcrumb/URL, or organization name
- project: Project name, repo name, ticket ID, or task being worked on
- url: Full URL if visible (browser address bar, links)
- breadcrumb: Navigation path if visible (e.g., "Companies / ClientName / Section")
- keywords: 3-5 topic words describing the work

Examples:

Text: [TITLE BAR: Project Budget.xlsx] CLIENT: Acme Inc Total: $50,000
Answer: {{"document": "Project Budget.xlsx", "client": "Acme Inc", "project": null, "keywords": ["budget", "finance"]}}

Text: [TITLE BAR: Resource Planner.xlsx] DAG Tech BILL OF MATERIALS CLIENT: SWTLNE01 Total Labor $24,400
Answer: {{"document": "Resource Planner.xlsx", "client": "SWTLNE01", "project": null, "keywords": ["resource", "labor", "billing"]}}

Text: [TITLE BAR: Pitch Outline.docx - Word] Client Code: KHHTH01 Project Title: Slack to Microsoft Teams Migration
Answer: {{"document": "Pitch Outline.docx", "client": "KHHTH01", "project": "Slack to Microsoft Teams Migration", "keywords": ["migration", "slack", "teams"]}}

Text: [TITLE BAR: main.py - aw-watcher-enhanced - Visual Studio Code] def capture_screen(): import mss git commit -m "Add OCR"
Answer: {{"document": "main.py", "client": null, "project": "aw-watcher-enhanced", "keywords": ["python", "ocr", "screen capture"]}}

Text: [TITLE BAR: Terminal - zsh] cd ~/dagtech/acme-portal npm run build Successfully compiled 147 modules
Answer: {{"document": "Terminal", "client": "Acme", "project": "acme-portal", "keywords": ["build", "npm", "terminal"]}}

Text: [TITLE BAR: PR #42 - dagtech/meridian-migration - GitHub] https://github.com/dagtech/meridian-migration/pull/42 feat: add SSO integration Files changed: 12
Answer: {{"document": "GitHub PR #42", "client": "Meridian", "project": "meridian-migration", "url": "https://github.com/dagtech/meridian-migration/pull/42", "keywords": ["github", "sso", "pull request"]}}

Text: [TITLE BAR: Jira - ACME-1234] Implement SSO for enterprise customers Status: In Progress Assignee: Greg
Answer: {{"document": "ACME-1234", "client": "Acme", "project": "SSO Implementation", "keywords": ["jira", "sso", "enterprise"]}}

Text: [TITLE BAR: Slack - Meridian Health] #proj-migration @sarah the data export is ready for review
Answer: {{"document": "Slack", "client": "Meridian Health", "project": "migration", "keywords": ["slack", "data export", "review"]}}

Text: [TITLE BAR: AWS Console] EC2 > Instances i-0abc123 nexgen-prod-api running t3.large
Answer: {{"document": "AWS EC2", "client": "NexGen", "project": "nexgen-prod-api", "keywords": ["aws", "ec2", "infrastructure"]}}

Text: [TITLE BAR: Google Workspace | Admin - DAG Tech] https://dagtech.huducloud.com/passwords/google-workspace-admin Companies / RGCENG01 / Passwords / Website - Admin administrator@rgce.com
Answer: {{"document": "Hudu - Google Workspace Admin", "client": "RGCENG01", "project": "Password Management", "url": "https://dagtech.huducloud.com/passwords/google-workspace-admin", "breadcrumb": "Companies / RGCENG01 / Passwords / Website - Admin", "keywords": ["hudu", "passwords", "google workspace"]}}

Text: [TITLE BAR: ConnectWise Manage] Service Ticket #847234 ACME Corp - Server offline Priority: Critical Assigned: Greg
Answer: {{"document": "Ticket #847234", "client": "ACME Corp", "project": "Server offline", "keywords": ["connectwise", "ticket", "critical"]}}

Now extract from:
{ocr_text}

JSON:"""


class LLMScreenAnalyzer:
    """Analyzes screen captures using vision LLMs."""

    def __init__(
        self,
        backend: str = "ollama",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
    ):
        """
        Initialize the LLM screen analyzer.

        Args:
            backend: LLM backend - "ollama", "claude", or "openai"
            model: Specific model to use (defaults to fastest for backend)
            api_key: API key for cloud backends
            base_url: Custom API URL (for Ollama, defaults to localhost:11434)
            timeout: Request timeout in seconds
        """
        self.backend = backend
        self.model = model or LLM_BACKENDS.get(backend, {}).get("default", "moondream")
        self.api_key = api_key or os.environ.get(f"{backend.upper()}_API_KEY")
        self.base_url = base_url
        self.timeout = timeout

        # Set default URLs
        if backend == "ollama" and not base_url:
            self.base_url = "http://localhost:11434"
        elif backend == "claude" and not base_url:
            self.base_url = "https://api.anthropic.com"
        elif backend == "openai" and not base_url:
            self.base_url = "https://api.openai.com"

        logger.info(f"LLM OCR initialized: {backend}/{self.model}")

    def _image_to_base64(self, image) -> str:
        """Convert PIL Image to base64 string."""
        buffer = BytesIO()
        # Resize for speed if too large
        max_size = 1024
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size)

        image.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def analyze(self, image, prompt: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Analyze a screen capture using the configured LLM.

        Args:
            image: PIL Image object
            prompt: Custom prompt (uses default if not provided)

        Returns:
            Dict with analysis results or None on failure
        """
        prompt = prompt or SCREEN_ANALYSIS_PROMPT
        start_time = time.time()

        try:
            if self.backend == "ollama":
                result = self._analyze_ollama(image, prompt)
            elif self.backend == "claude":
                result = self._analyze_claude(image, prompt)
            elif self.backend == "openai":
                result = self._analyze_openai(image, prompt)
            else:
                logger.error(f"Unknown backend: {self.backend}")
                return None

            elapsed = time.time() - start_time
            logger.debug(f"LLM analysis completed in {elapsed:.2f}s")

            return result

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return None

    def _analyze_ollama(self, image, prompt: str) -> Optional[Dict[str, Any]]:
        """Analyze using Ollama (local)."""
        import requests

        image_b64 = self._image_to_base64(image)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 256,
            },
        }

        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

        result = response.json()
        text = result.get("response", "")

        return self._parse_json_response(text)

    def _analyze_claude(self, image, prompt: str) -> Optional[Dict[str, Any]]:
        """Analyze using Claude API."""
        import requests

        if not self.api_key:
            logger.error("Claude API key not set")
            return None

        image_b64 = self._image_to_base64(image)

        payload = {
            "model": self.model,
            "max_tokens": 256,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        response = requests.post(
            f"{self.base_url}/v1/messages",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        result = response.json()
        text = result.get("content", [{}])[0].get("text", "")

        return self._parse_json_response(text)

    def _analyze_openai(self, image, prompt: str) -> Optional[Dict[str, Any]]:
        """Analyze using OpenAI API."""
        import requests

        if not self.api_key:
            logger.error("OpenAI API key not set")
            return None

        image_b64 = self._image_to_base64(image)

        payload = {
            "model": self.model,
            "max_tokens": 256,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                                "detail": "low",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        result = response.json()
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        return self._parse_json_response(text)

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response."""
        if not text:
            return None

        # Try to extract JSON from response
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass

            logger.warning(f"Failed to parse LLM response as JSON: {text[:100]}")
            return {"raw_text": text}


def summarize_ocr_with_llm(
    ocr_text: str,
    model: str = "gemma3:4b",
    base_url: str = "http://localhost:11434",
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """
    Use a fast text LLM to summarize/structure OCR output.

    This is faster than vision LLMs since it only processes text.

    Args:
        ocr_text: Raw OCR text from screen capture
        model: Ollama model to use (gemma3:1b is very fast)
        base_url: Ollama API URL
        timeout: Request timeout

    Returns:
        Structured dict with app, task, document, client, keywords
    """
    import requests

    if not ocr_text or len(ocr_text.strip()) < 10:
        return None

    # Truncate OCR text if too long
    ocr_text = ocr_text[:2000]

    prompt = TEXT_SUMMARIZE_PROMPT.format(ocr_text=ocr_text)

    try:
        start = time.time()
        response = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 150,
                },
            },
            timeout=timeout,
        )
        response.raise_for_status()

        elapsed = time.time() - start
        result = response.json()
        text = result.get("response", "")

        logger.debug(f"LLM summarize completed in {elapsed:.2f}s")

        # Parse JSON from response
        if not text:
            return None

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start_idx = text.find("{")
            end_idx = text.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                try:
                    parsed = json.loads(text[start_idx:end_idx])
                except:
                    parsed = {}
            else:
                parsed = {}

        return parsed if parsed else None

    except Exception as e:
        logger.debug(f"LLM summarize failed: {e}")
        return None


# Singleton instance
_analyzer: Optional[LLMScreenAnalyzer] = None


def get_llm_analyzer(
    backend: str = "ollama",
    model: Optional[str] = None,
    **kwargs,
) -> LLMScreenAnalyzer:
    """Get or create the LLM analyzer singleton."""
    global _analyzer
    if _analyzer is None or _analyzer.backend != backend:
        _analyzer = LLMScreenAnalyzer(backend=backend, model=model, **kwargs)
    return _analyzer


def analyze_screen_with_llm(
    image,
    backend: str = "ollama",
    model: Optional[str] = None,
    **kwargs,
) -> Optional[Dict[str, Any]]:
    """
    Convenience function to analyze a screen capture.

    Args:
        image: PIL Image object
        backend: LLM backend to use
        model: Specific model (optional)

    Returns:
        Dict with analysis or None
    """
    analyzer = get_llm_analyzer(backend=backend, model=model, **kwargs)
    return analyzer.analyze(image)


# Test the module
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG)

    # Test with a screen capture
    try:
        import mss
        from PIL import Image

        print("Capturing screen...")
        with mss.mss() as sct:
            screenshot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        print(f"Image size: {img.size}")

        print("\nAnalyzing with Ollama/moondream...")
        start = time.time()
        result = analyze_screen_with_llm(img, backend="ollama", model="moondream")
        elapsed = time.time() - start

        print(f"\nResult ({elapsed:.2f}s):")
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
