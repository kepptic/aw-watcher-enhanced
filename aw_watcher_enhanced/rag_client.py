"""
RAG Database Client for aw-watcher-enhanced.

Integrates with Qdrant vector database running in Docker to provide:
- Client detection from domains, emails, and keywords
- Project code recognition
- Semantic search using vector embeddings
- Autotask/TSheets/Hudu ID mapping

The Qdrant database is expected to be running at:
    http://localhost:6333
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class QdrantClient:
    """
    Simple Qdrant REST API client.

    Uses the REST API directly to avoid additional dependencies.
    """

    def __init__(self, host: str = "localhost", port: int = 6333, https: bool = False):
        """
        Initialize Qdrant client.

        Args:
            host: Qdrant server host
            port: Qdrant server port
            https: Use HTTPS instead of HTTP
        """
        protocol = "https" if https else "http"
        self.base_url = f"{protocol}://{host}:{port}"
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def health_check(self) -> bool:
        """Check if Qdrant is reachable."""
        try:
            response = self._session.get(f"{self.base_url}/collections", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def list_collections(self) -> List[str]:
        """List all collections."""
        try:
            response = self._session.get(f"{self.base_url}/collections", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [c["name"] for c in data.get("result", {}).get("collections", [])]
        except Exception as e:
            logger.error(f"Error listing collections: {e}")
        return []

    def scroll(
        self,
        collection: str,
        limit: int = 100,
        offset: Optional[int] = None,
        with_payload: bool = True,
        with_vector: bool = False,
    ) -> Tuple[List[Dict], Optional[int]]:
        """
        Scroll through all points in a collection.

        Returns:
            Tuple of (points, next_offset)
        """
        try:
            payload = {"limit": limit, "with_payload": with_payload, "with_vector": with_vector}
            if offset:
                payload["offset"] = offset

            response = self._session.post(
                f"{self.base_url}/collections/{collection}/points/scroll", json=payload, timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", {})
                points = result.get("points", [])
                next_offset = result.get("next_page_offset")
                return points, next_offset
        except Exception as e:
            logger.error(f"Error scrolling collection {collection}: {e}")
        return [], None

    def search(
        self,
        collection: str,
        vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Vector similarity search.

        Args:
            collection: Collection name
            vector: Query vector
            limit: Max results
            score_threshold: Minimum similarity score
            filter_conditions: Qdrant filter conditions

        Returns:
            List of search results with score
        """
        try:
            payload = {"vector": vector, "limit": limit, "with_payload": True}
            if score_threshold:
                payload["score_threshold"] = score_threshold
            if filter_conditions:
                payload["filter"] = filter_conditions

            response = self._session.post(
                f"{self.base_url}/collections/{collection}/points/search", json=payload, timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("result", [])
        except Exception as e:
            logger.error(f"Error searching collection {collection}: {e}")
        return []

    def get_all_points(self, collection: str) -> List[Dict]:
        """Get all points from a collection by scrolling."""
        all_points = []
        offset = None

        while True:
            points, next_offset = self.scroll(collection, limit=100, offset=offset)
            all_points.extend(points)

            if not next_offset or not points:
                break
            offset = next_offset

        return all_points


class RAGClient:
    """
    Client for accessing the Qdrant RAG database for client/project detection.

    Connects to Qdrant running in Docker and caches data in memory.
    """

    def __init__(
        self, qdrant_host: str = "localhost", qdrant_port: int = 6333, cache_ttl_minutes: int = 30
    ):
        """
        Initialize the RAG client.

        Args:
            qdrant_host: Qdrant server host
            qdrant_port: Qdrant server port
            cache_ttl_minutes: How long to cache data before reloading.
        """
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)

        # Cache storage
        self._client_index: Optional[Dict[str, Dict]] = None
        self._domain_map: Optional[Dict[str, str]] = None
        self._last_load: Optional[datetime] = None
        self._connected: bool = False

        # Check connection
        if self.qdrant.health_check():
            self._connected = True
            logger.info(f"Connected to Qdrant at {qdrant_host}:{qdrant_port}")
        else:
            logger.warning(f"Could not connect to Qdrant at {qdrant_host}:{qdrant_port}")

    def _should_reload(self) -> bool:
        """Check if cache should be reloaded."""
        if self._client_index is None or self._last_load is None:
            return True
        return datetime.now() - self._last_load > self.cache_ttl

    def _load_data(self) -> bool:
        """Load client data from Qdrant into memory cache."""
        if not self._connected:
            return False

        try:
            # Load all clients from the 'clients' collection
            points = self.qdrant.get_all_points("clients")

            self._client_index = {}
            self._domain_map = {}

            for point in points:
                payload = point.get("payload", {})
                client_code = payload.get("code")

                if not client_code:
                    continue

                # Build client entry
                domain = payload.get("domain", "")

                # Clean domain (remove www. prefix)
                if domain:
                    clean_domain = domain.lower().strip()
                    if clean_domain.startswith("www."):
                        clean_domain = clean_domain[4:]

                    # Add to domain map
                    self._domain_map[clean_domain] = client_code

                    # Also add the full domain with www if present
                    if domain.lower().startswith("www."):
                        self._domain_map[domain.lower()] = client_code

                # Store client info
                self._client_index[client_code] = {
                    "code": client_code,
                    "name": payload.get("name", client_code),
                    "domain": domain,
                    "domains": [domain] if domain else [],
                    "autotask_id": payload.get("autotask_id"),
                    "hudu_id": payload.get("hudu_id"),
                    "rmm_site_uid": payload.get("rmm_site_uid"),
                    "source": payload.get("source", "qdrant"),
                    "embedding_text": payload.get("embedding_text", ""),
                }

            self._last_load = datetime.now()
            logger.info(f"Loaded {len(self._client_index)} clients from Qdrant")
            logger.info(f"Built {len(self._domain_map)} domain mappings")
            return True

        except Exception as e:
            logger.error(f"Error loading data from Qdrant: {e}")
            return False

    def _ensure_loaded(self):
        """Ensure data is loaded and fresh."""
        if self._should_reload():
            self._load_data()

    @property
    def is_connected(self) -> bool:
        """Check if connected to Qdrant."""
        return self._connected

    @property
    def client_index(self) -> Dict[str, Any]:
        """Get the client index, loading if necessary."""
        self._ensure_loaded()
        return self._client_index or {}

    @property
    def domain_map(self) -> Dict[str, str]:
        """Get the domain mapping, loading if necessary."""
        self._ensure_loaded()
        return self._domain_map or {}

    def detect_client_from_domain(self, domain: str) -> Optional[str]:
        """
        Detect client code from a domain name.

        Args:
            domain: Domain name (e.g., "dagtech.com")

        Returns:
            Client code (e.g., "DAGTECH01") or None
        """
        if not domain:
            return None

        domain = domain.lower().strip()

        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]

        # Direct lookup
        client_code = self.domain_map.get(domain)
        if client_code:
            logger.debug(f"Domain '{domain}' matched to client '{client_code}'")
            return client_code

        # Try without subdomains
        parts = domain.split(".")
        if len(parts) > 2:
            base_domain = ".".join(parts[-2:])
            client_code = self.domain_map.get(base_domain)
            if client_code:
                logger.debug(f"Base domain '{base_domain}' matched to client '{client_code}'")
                return client_code

        return None

    def detect_client_from_email(self, email: str) -> Optional[str]:
        """
        Detect client code from an email address.

        Args:
            email: Email address (e.g., "user@dagtech.com")

        Returns:
            Client code or None
        """
        if not email or "@" not in email:
            return None

        domain = email.split("@")[1].lower()
        return self.detect_client_from_domain(domain)

    def detect_client_from_text(self, text: str) -> Optional[Tuple[str, str, float]]:
        """
        Detect client from free-form text using search index.

        Args:
            text: Text to search (window title, OCR content, etc.)

        Returns:
            Tuple of (client_code, matched_term, confidence) or None
        """
        if not text:
            return None

        text_lower = text.lower()
        best_match = None
        best_score = 0.0

        for client_code, client_data in self.client_index.items():
            if not isinstance(client_data, dict):
                continue

            # Check client code itself (high confidence)
            if client_code.lower() in text_lower:
                score = len(client_code) / max(len(text_lower), 1) * 100
                if score > best_score:
                    best_match = (client_code, client_code, min(1.0, score / 10))
                    best_score = score

            # Check domain
            domain = client_data.get("domain", "")
            if domain:
                clean_domain = domain.lower().replace("www.", "")
                if clean_domain in text_lower:
                    score = len(clean_domain) / max(len(text_lower), 1) * 100
                    if score > best_score:
                        best_match = (client_code, domain, min(1.0, score / 5))
                        best_score = score

            # Check embedding text for additional keywords
            embedding_text = client_data.get("embedding_text", "").lower()
            if embedding_text:
                # Extract meaningful parts from embedding text
                parts = [p.strip() for p in embedding_text.split("|")]
                for part in parts:
                    if part and len(part) > 3 and part in text_lower:
                        score = len(part) / max(len(text_lower), 1) * 100
                        if score > best_score:
                            best_match = (client_code, part, min(0.8, score / 10))
                            best_score = score

        return best_match

    def detect_project_code(self, text: str) -> Optional[str]:
        """
        Detect project code from text (e.g., P202502-539).

        Args:
            text: Text to search

        Returns:
            Project code or None
        """
        if not text:
            return None

        # Project code pattern: P followed by YYYYMM-NNN
        pattern = r"\b(P\d{6}-\d{3})\b"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        return None

    def get_client_info(self, client_code: str) -> Optional[Dict[str, Any]]:
        """
        Get full client information by code.

        Args:
            client_code: Client code (e.g., "DAGTECH01")

        Returns:
            Client data dictionary or None
        """
        return self.client_index.get(client_code.upper())

    def get_client_display_name(self, client_code: str) -> str:
        """
        Get a human-readable display name for a client.

        Args:
            client_code: Client code

        Returns:
            Display name (company name or code)
        """
        info = self.get_client_info(client_code)
        if info:
            return info.get("name") or client_code
        return client_code

    def search_clients(self, query: str, limit: int = 10) -> List[Tuple[str, str, float]]:
        """
        Search for clients matching a query.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of (client_code, display_name, score) tuples
        """
        if not query:
            return []

        query_lower = query.lower()
        results = []

        for client_code, client_data in self.client_index.items():
            if not isinstance(client_data, dict):
                continue

            # Check code, name, domain, embedding_text
            searchable = " ".join(
                [
                    client_code,
                    client_data.get("name", ""),
                    client_data.get("domain", ""),
                    client_data.get("embedding_text", ""),
                ]
            ).lower()

            if query_lower in searchable:
                # Higher score for exact code match
                if query_lower == client_code.lower():
                    score = 1.0
                elif query_lower in client_code.lower():
                    score = 0.9
                else:
                    score = 0.5

                display_name = self.get_client_display_name(client_code)
                results.append((client_code, display_name, score))

        # Sort by score descending
        results.sort(key=lambda x: -x[2])
        return results[:limit]

    def get_all_domains(self) -> Dict[str, str]:
        """Get all domain-to-client mappings."""
        return self.domain_map.copy()

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the RAG database."""
        self._ensure_loaded()
        return {
            "connected": self._connected,
            "qdrant_url": self.qdrant.base_url,
            "total_clients": len(self._client_index or {}),
            "total_domains": len(self._domain_map or {}),
            "last_load": self._last_load.isoformat() if self._last_load else None,
            "cache_ttl_minutes": self.cache_ttl.total_seconds() / 60,
            "collections": self.qdrant.list_collections() if self._connected else [],
        }

    def refresh(self) -> bool:
        """Force refresh the cache from Qdrant."""
        self._last_load = None
        return self._load_data()


# Singleton instance
_rag_client: Optional[RAGClient] = None


def get_rag_client(qdrant_host: str = "localhost", qdrant_port: int = 6333) -> RAGClient:
    """
    Get the singleton RAG client instance.

    Args:
        qdrant_host: Qdrant server host (only used on first call)
        qdrant_port: Qdrant server port (only used on first call)
    """
    global _rag_client
    if _rag_client is None:
        _rag_client = RAGClient(qdrant_host=qdrant_host, qdrant_port=qdrant_port)
    return _rag_client


def detect_client(
    domain: Optional[str] = None,
    email: Optional[str] = None,
    text: Optional[str] = None,
    url: Optional[str] = None,
) -> Optional[str]:
    """
    Convenience function to detect client from various inputs.

    Args:
        domain: Domain name to check
        email: Email address to check
        text: Free-form text to search
        url: URL to extract domain from

    Returns:
        Client code or None
    """
    client = get_rag_client()

    # Try URL first (extract domain)
    if url:
        try:
            parsed = urlparse(url)
            if parsed.netloc:
                result = client.detect_client_from_domain(parsed.netloc)
                if result:
                    return result
        except Exception:
            pass

    # Try domain
    if domain:
        result = client.detect_client_from_domain(domain)
        if result:
            return result

    # Try email
    if email:
        result = client.detect_client_from_email(email)
        if result:
            return result

    # Try text search
    if text:
        result = client.detect_client_from_text(text)
        if result:
            return result[0]  # Return just the client code

    return None


# Test the module
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    rag = get_rag_client()
    print(f"\nRAG Stats: {rag.get_stats()}")

    if not rag.is_connected:
        print("\nERROR: Could not connect to Qdrant. Is Docker running?")
        print("Start Qdrant with: docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant")
        exit(1)

    # Test domain detection
    print("\n--- Domain Detection ---")
    test_domains = [
        "schoelkopffineartappraisals.com",
        "cnc365.net",
        "craccountingdc.com",
        "unknown.com",
    ]
    for domain in test_domains:
        client = rag.detect_client_from_domain(domain)
        print(f"Domain '{domain}' -> {client}")

    # Test text search
    print("\n--- Text Search ---")
    test_texts = [
        "Working on SKFAPR01 appraisal project",
        "Meeting with CONVRG01 about their network",
        "Email about craccountingdc.com",
    ]
    for text in test_texts:
        result = rag.detect_client_from_text(text)
        print(f"Text '{text[:50]}...' -> {result}")

    # Test project code detection
    print("\n--- Project Code Detection ---")
    test_projects = [
        "Project P202502-539 meeting",
        "Working on P202409-421",
        "No project here",
    ]
    for text in test_projects:
        project = rag.detect_project_code(text)
        print(f"Project in '{text}' -> {project}")

    # Test client search
    print("\n--- Client Search ---")
    search_results = rag.search_clients("SKF", limit=5)
    print(f"Search 'SKF': {search_results}")
