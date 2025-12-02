"""
Activity categorization for aw-watcher-enhanced.

Automatically categorizes activities based on:
- App name
- Window title / URL
- OCR keywords
- Custom rules loaded from YAML files
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache for loaded rules
_rules_cache: Optional[List[Dict[str, Any]]] = None
_clients_cache: Optional[Dict[str, Any]] = None


# Default categorization rules
# Format: list of {match: {...}, category: "..."}
DEFAULT_RULES: List[Dict[str, Any]] = [
    # Development
    {
        "match": {"app": r"code|pycharm|intellij|webstorm|vim|nvim|sublime"},
        "category": "Work/Development/Coding",
    },
    {
        "match": {"url": r"github\.com/.+/pull/"},
        "category": "Work/Development/Code Review",
    },
    {
        "match": {"url": r"github\.com|gitlab\.com|bitbucket\.org"},
        "category": "Work/Development",
    },
    {
        "match": {"url": r"stackoverflow\.com|docs\."},
        "category": "Work/Development/Research",
    },
    # Communication
    {
        "match": {"app": r"slack|teams|discord|zoom"},
        "category": "Work/Communication/Chat",
    },
    {
        "match": {"url": r"mail\.google\.com|outlook\.(com|office)"},
        "category": "Work/Communication/Email",
    },
    {
        "match": {"app": r"outlook|thunderbird|mail"},
        "category": "Work/Communication/Email",
    },
    {
        "match": {"url": r"meet\.google\.com|zoom\.us"},
        "category": "Work/Communication/Meetings",
    },
    # Documentation
    {
        "match": {"app": r"word|winword|pages|docs"},
        "category": "Work/Documentation/Writing",
    },
    {
        "match": {"url": r"docs\.google\.com/document"},
        "category": "Work/Documentation/Writing",
    },
    {"match": {"url": r"notion\.so|confluence"}, "category": "Work/Documentation"},
    {
        "match": {"app": r"acrobat|preview", "title": r"\.pdf"},
        "category": "Work/Documentation/Reading",
    },
    # Spreadsheets & Data
    {"match": {"app": r"excel|numbers"}, "category": "Work/Data/Spreadsheets"},
    {
        "match": {"url": r"docs\.google\.com/spreadsheets"},
        "category": "Work/Data/Spreadsheets",
    },
    # Design
    {
        "match": {"app": r"figma|sketch|photoshop|illustrator|xd"},
        "category": "Work/Design",
    },
    {"match": {"url": r"figma\.com"}, "category": "Work/Design"},
    # Project Management
    {
        "match": {"url": r"jira|asana\.com|trello\.com|monday\.com|linear\.app"},
        "category": "Work/Project Management",
    },
    # Research/Learning
    {"match": {"url": r"wikipedia\.org|medium\.com"}, "category": "Research/Reading"},
    {
        "match": {"url": r"youtube\.com.*watch.*(?:tutorial|learn|course)"},
        "category": "Research/Learning",
    },
    {
        "match": {"url": r"udemy\.com|coursera\.org|linkedin\.com/learning"},
        "category": "Research/Learning",
    },
    # Personal - Social Media
    {
        "match": {
            "url": r"facebook\.com|twitter\.com|x\.com|instagram\.com|linkedin\.com(?!/learning)"
        },
        "category": "Personal/Social Media",
    },
    {"match": {"url": r"reddit\.com"}, "category": "Personal/Social Media"},
    # Personal - Entertainment
    {
        "match": {"url": r"youtube\.com|netflix\.com|twitch\.tv|spotify\.com"},
        "category": "Personal/Entertainment",
    },
    {"match": {"app": r"spotify|vlc|netflix"}, "category": "Personal/Entertainment"},
    # Personal - Shopping
    {
        "match": {"url": r"amazon\.com|ebay\.com|etsy\.com"},
        "category": "Personal/Shopping",
    },
    # System
    {"match": {"app": r"explorer|finder"}, "category": "System/File Management"},
    {
        "match": {"app": r"terminal|cmd|powershell|iterm|konsole"},
        "category": "Work/Development/Terminal",
    },
    {
        "match": {"app": r"settings|preferences|control panel"},
        "category": "System/Settings",
    },
]


def load_rules_from_yaml(rules_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Load categorization rules from YAML file.

    Args:
        rules_path: Path to rules YAML file. If None, uses default location.

    Returns:
        List of rule dictionaries
    """
    global _rules_cache

    if _rules_cache is not None:
        return _rules_cache

    if rules_path is None:
        # Try default locations
        possible_paths = [
            Path(__file__).parent / "rules" / "categories.yaml",
            Path.home() / ".config" / "activitywatch" / "aw-watcher-enhanced" / "categories.yaml",
        ]
        for p in possible_paths:
            if p.exists():
                rules_path = p
                break

    if rules_path is None or not rules_path.exists():
        logger.debug("No custom rules file found, using defaults")
        return []

    try:
        import yaml

        with open(rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        rules = data.get("rules", [])
        logger.info(f"Loaded {len(rules)} rules from {rules_path}")
        _rules_cache = rules
        return rules
    except ImportError:
        logger.warning("PyYAML not installed, cannot load custom rules")
        return []
    except Exception as e:
        logger.error(f"Error loading rules from {rules_path}: {e}")
        return []


def load_clients_from_yaml(clients_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load client keywords from YAML file.

    Args:
        clients_path: Path to clients YAML file. If None, uses default location.

    Returns:
        Dictionary of client configurations
    """
    global _clients_cache

    if _clients_cache is not None:
        return _clients_cache

    if clients_path is None:
        # Try default locations
        possible_paths = [
            Path(__file__).parent / "rules" / "clients.yaml",
            Path.home() / ".config" / "activitywatch" / "aw-watcher-enhanced" / "clients.yaml",
        ]
        for p in possible_paths:
            if p.exists():
                clients_path = p
                break

    if clients_path is None or not clients_path.exists():
        logger.debug("No clients file found")
        return {}

    try:
        import yaml

        with open(clients_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        clients = data.get("clients", {})
        logger.info(f"Loaded {len(clients)} clients from {clients_path}")
        _clients_cache = clients
        return clients
    except ImportError:
        logger.warning("PyYAML not installed, cannot load client keywords")
        return {}
    except Exception as e:
        logger.error(f"Error loading clients from {clients_path}: {e}")
        return {}


def categorize_event(data: Dict[str, Any], config: Dict[str, Any]) -> Optional[str]:
    """
    Categorize an event based on rules and keywords.

    Args:
        data: Event data dict
        config: Categorization configuration

    Returns:
        Category string (e.g., "Work/Development/Coding") or None
    """
    if not config.get("enabled", True):
        return None

    # Load rules from YAML if available, then fall back to defaults
    yaml_rules = load_rules_from_yaml(config.get("rules_file"))
    rules = yaml_rules if yaml_rules else DEFAULT_RULES.copy()

    # Add any inline custom rules from config
    custom_rules = config.get("rules", [])
    rules.extend(custom_rules)

    # Try rule-based categorization first
    category = _match_rules(data, rules)
    if category:
        return category

    # Try RAG database for client detection first (most accurate)
    if config.get("use_rag", True):
        qdrant_config = config.get("qdrant", {})
        client_code, project_code = _detect_client_from_rag(data, qdrant_config)
        if client_code:
            if project_code:
                return f"Work/Client/{client_code}/{project_code}"
            return f"Work/Client/{client_code}"

    # Fall back to keyword-based client detection
    # First load from YAML, then merge with config
    yaml_clients = load_clients_from_yaml(config.get("clients_file"))
    client_keywords = config.get("client_keywords", {})

    # Merge YAML clients with config clients
    all_clients = {}
    for client_name, client_config in yaml_clients.items():
        keywords = client_config.get("keywords", [])
        # Also add domains and emails as keywords
        keywords.extend(client_config.get("domains", []))
        keywords.extend(client_config.get("emails", []))
        all_clients[client_name] = keywords

    # Config client_keywords override/extend
    for client_name, keywords in client_keywords.items():
        if client_name in all_clients:
            all_clients[client_name].extend(keywords)
        else:
            all_clients[client_name] = keywords

    client, project = _detect_client_and_project(data, yaml_clients, client_keywords)
    if client:
        if project:
            return f"Work/Client/{client}/{project}"
        return f"Work/Client/{client}"

    # Default: uncategorized
    return None


def _match_rules(data: Dict[str, Any], rules: List[Dict[str, Any]]) -> Optional[str]:
    """Match event against categorization rules."""
    app = data.get("app", "").lower()
    title = data.get("title", "").lower()
    url = data.get("url", "").lower()

    for rule in rules:
        match_conditions = rule.get("match", {})
        all_match = True

        for field, pattern in match_conditions.items():
            value = ""
            if field == "app":
                value = app
            elif field == "title":
                value = title
            elif field == "url":
                value = url
            elif field == "domain":
                value = data.get("domain", "").lower()

            try:
                if not re.search(pattern, value, re.IGNORECASE):
                    all_match = False
                    break
            except re.error:
                all_match = False
                break

        if all_match:
            return rule.get("category")

    return None


def _detect_client(data: Dict[str, Any], client_keywords: Dict[str, List[str]]) -> Optional[str]:
    """Detect client/project from keywords."""
    if not client_keywords:
        return None

    # Collect all searchable text
    searchable = " ".join(
        [
            data.get("title", ""),
            data.get("url", ""),
            " ".join(data.get("ocr_keywords", [])),
            data.get("document", {}).get("project", ""),
            data.get("document", {}).get("filename", ""),
        ]
    ).lower()

    # Check each client's keywords
    for client, keywords in client_keywords.items():
        for keyword in keywords:
            if keyword.lower() in searchable:
                logger.debug(f"Detected client '{client}' via keyword '{keyword}'")
                return client

    return None


def _detect_client_and_project(
    data: Dict[str, Any], yaml_clients: Dict[str, Any], config_keywords: Dict[str, List[str]]
) -> tuple:
    """
    Detect client and optionally project from keywords.

    Args:
        data: Event data dict
        yaml_clients: Client configs loaded from YAML (with projects)
        config_keywords: Simple client keywords from config

    Returns:
        Tuple of (client_name, project_name) or (None, None)
    """
    # Collect all searchable text
    searchable = " ".join(
        [
            data.get("title", ""),
            data.get("url", ""),
            " ".join(data.get("ocr_keywords", [])),
            data.get("document", {}).get("project", ""),
            data.get("document", {}).get("filename", ""),
            data.get("domain", ""),
        ]
    ).lower()

    # First, try to match projects within clients (more specific)
    for client_name, client_config in yaml_clients.items():
        if not isinstance(client_config, dict):
            continue

        projects = client_config.get("projects", {})
        for project_name, project_keywords in projects.items():
            if not isinstance(project_keywords, list):
                continue
            for keyword in project_keywords:
                if keyword.lower() in searchable:
                    logger.debug(
                        f"Detected client '{client_name}' project '{project_name}' via keyword '{keyword}'"
                    )
                    return client_name, project_name

    # Then try client-level keywords
    for client_name, client_config in yaml_clients.items():
        if isinstance(client_config, dict):
            keywords = client_config.get("keywords", [])
            # Also check domains
            for domain in client_config.get("domains", []):
                if domain.lower() in searchable:
                    logger.debug(f"Detected client '{client_name}' via domain '{domain}'")
                    return client_name, None
            # Check github repos
            for repo in client_config.get("github_repos", []):
                if repo.lower() in searchable:
                    logger.debug(f"Detected client '{client_name}' via repo '{repo}'")
                    return client_name, None
            # Check jira projects
            for jira_proj in client_config.get("jira_projects", []):
                if jira_proj.lower() in searchable:
                    logger.debug(f"Detected client '{client_name}' via JIRA '{jira_proj}'")
                    return client_name, None
            # Check emails
            for email in client_config.get("emails", []):
                if email.lower() in searchable:
                    logger.debug(f"Detected client '{client_name}' via email '{email}'")
                    return client_name, None
        else:
            keywords = client_config if isinstance(client_config, list) else []

        for keyword in keywords:
            if keyword.lower() in searchable:
                logger.debug(f"Detected client '{client_name}' via keyword '{keyword}'")
                return client_name, None

    # Finally try simple config keywords
    for client_name, keywords in config_keywords.items():
        if not isinstance(keywords, list):
            continue
        for keyword in keywords:
            if keyword.lower() in searchable:
                logger.debug(f"Detected client '{client_name}' via config keyword '{keyword}'")
                return client_name, None

    return None, None


def clear_caches():
    """Clear the rules and clients caches. Useful for testing or config reload."""
    global _rules_cache, _clients_cache
    _rules_cache = None
    _clients_cache = None


def _detect_client_from_rag(data: Dict[str, Any], qdrant_config: Optional[Dict] = None) -> tuple:
    """
    Detect client using the RAG database (Qdrant).

    Args:
        data: Event data dict
        qdrant_config: Optional Qdrant configuration dict with host, port, etc.

    Returns:
        Tuple of (client_code, project_code) or (None, None)
    """
    try:
        from .rag_client import get_rag_client
    except ImportError:
        logger.debug("RAG client not available")
        return None, None

    # Get config values or use defaults
    if qdrant_config:
        host = qdrant_config.get("host", "localhost")
        port = qdrant_config.get("port", 6333)
        rag = get_rag_client(qdrant_host=host, qdrant_port=port)
    else:
        rag = get_rag_client()

    # Try domain detection first (most reliable)
    url = data.get("url", "")
    domain = data.get("domain", "")

    if url:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.netloc:
                domain = parsed.netloc
        except Exception:
            pass

    if domain:
        client_code = rag.detect_client_from_domain(domain)
        if client_code:
            # Check for project code in title/text
            title = data.get("title", "")
            project_code = rag.detect_project_code(title)
            return client_code, project_code

    # Try text-based detection from title and OCR keywords
    searchable_parts = [
        data.get("title", ""),
        " ".join(data.get("ocr_keywords", [])),
        data.get("document", {}).get("project", ""),
        data.get("document", {}).get("filename", ""),
    ]
    searchable = " ".join(filter(None, searchable_parts))

    if searchable:
        result = rag.detect_client_from_text(searchable)
        if result:
            client_code = result[0]
            project_code = rag.detect_project_code(searchable)
            return client_code, project_code

    return None, None


def get_category_hierarchy(category: str) -> List[str]:
    """
    Get category hierarchy from category string.

    Example: "Work/Development/Coding" -> ["Work", "Work/Development", "Work/Development/Coding"]
    """
    if not category:
        return []

    parts = category.split("/")
    hierarchy = []
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        hierarchy.append(current)

    return hierarchy


def suggest_category(data: Dict[str, Any]) -> List[str]:
    """
    Suggest possible categories for an event.

    Returns a list of suggested categories ordered by likelihood.
    """
    suggestions = []

    # Try all rules and collect matches
    for rule in DEFAULT_RULES:
        match_conditions = rule.get("match", {})
        score = 0

        for field, pattern in match_conditions.items():
            value = data.get(field, "")
            if isinstance(value, str):
                try:
                    if re.search(pattern, value, re.IGNORECASE):
                        score += 1
                except re.error:
                    pass

        if score > 0:
            suggestions.append((score, rule.get("category")))

    # Sort by score descending
    suggestions.sort(key=lambda x: -x[0])

    # Return unique categories
    seen = set()
    result = []
    for _, cat in suggestions:
        if cat and cat not in seen:
            result.append(cat)
            seen.add(cat)

    return result[:5]


# Test module
if __name__ == "__main__":
    test_cases = [
        {"app": "Code.exe", "title": "main.py - my-project"},
        {"app": "chrome.exe", "url": "https://github.com/user/repo/pull/123"},
        {"app": "chrome.exe", "url": "https://mail.google.com/inbox"},
        {"app": "Slack.exe", "title": "general - Company Workspace"},
        {"app": "chrome.exe", "url": "https://www.youtube.com/watch?v=xyz"},
    ]

    config = {"enabled": True}

    for data in test_cases:
        category = categorize_event(data, config)
        print(f"App: {data.get('app', '')}")
        print(f"Title/URL: {data.get('title', data.get('url', ''))}")
        print(f"Category: {category}")
        print()
