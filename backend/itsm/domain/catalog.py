"""
IT services and incident categories.

ServiceCatalog owns the service DEPENDENCY GRAPH ("Payment depends on Database"). It
rejects cycles and powers root-cause correlation (walk UPSTREAM) and the what-if
blast-radius simulation (walk DOWNSTREAM).

CategoryRegistry stores categories as data, so admins add new ones at runtime: no code
change, no enum edit (Open/Closed Principle). It also suggests a category from text.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from . import text
from .exceptions import (CategoryNotFoundError, DependencyCycleError, ServiceNotFoundError,
                         ValidationError)


class ITService:
    def __init__(self, service_id: str, name: str, business_criticality: int,
                 default_category: str, *keywords: str):
        if not service_id or not name:
            raise ValidationError("Service id and name are required.")
        if not 1 <= business_criticality <= 5:
            raise ValidationError("business_criticality must be 1..5.")
        self._service_id = service_id
        self._name = name
        self._business_criticality = business_criticality
        self._default_category = default_category.upper()
        self._keywords = {k.lower() for k in keywords}
        self._depends_on: dict[str, None] = {}        # ordered set
        self.owner = "Unassigned"

    service_id = property(lambda s: s._service_id)
    name = property(lambda s: s._name)
    business_criticality = property(lambda s: s._business_criticality)
    default_category = property(lambda s: s._default_category)
    keywords = property(lambda s: frozenset(s._keywords))
    depends_on = property(lambda s: tuple(s._depends_on))

    def _add_dependency_unchecked(self, upstream_id: str) -> None:
        """Only the catalog calls this, after checking for cycles."""
        self._depends_on[upstream_id] = None

    def to_dict(self) -> dict:
        return {"serviceId": self._service_id, "name": self._name,
                "businessCriticality": self._business_criticality,
                "defaultCategory": self._default_category, "dependsOn": list(self._depends_on),
                "owner": self.owner}

    def __repr__(self) -> str:
        return f"{self._name} ({self._service_id})"


class ServiceCatalog:
    def __init__(self):
        self._services: dict[str, ITService] = {}

    def add(self, service: ITService) -> None:
        self._services[service.service_id] = service

    def get(self, service_id: str) -> ITService:
        try:
            return self._services[service_id]
        except KeyError:
            raise ServiceNotFoundError(f"Service '{service_id}' not found.") from None

    def exists(self, service_id: str) -> bool:
        return service_id in self._services

    def all(self) -> list[ITService]:
        return list(self._services.values())

    def add_dependency(self, service_id: str, upstream_id: str) -> None:
        """Declare that `service_id` depends on `upstream_id`. Rejects cycles."""
        service = self.get(service_id)
        self.get(upstream_id)
        if service_id == upstream_id:
            raise DependencyCycleError("A service cannot depend on itself.")
        if service_id in self.upstream_of(upstream_id):
            raise DependencyCycleError(
                f"{upstream_id} already depends on {service_id}; this would create a cycle.")
        service._add_dependency_unchecked(upstream_id)

    def upstream_of(self, service_id: str) -> set[str]:
        """Everything this service needs, directly or indirectly (depth-first search)."""
        seen: set[str] = set()
        stack = list(self.get(service_id).depends_on)
        while stack:
            sid = stack.pop()
            if sid not in seen and sid in self._services:
                seen.add(sid)
                stack.extend(self._services[sid].depends_on)
        return seen

    def downstream_of(self, service_id: str) -> list[str]:
        """Everything that breaks if this service fails (breadth-first search, nearest first)."""
        self.get(service_id)
        order, seen, queue = [], {service_id}, deque([service_id])
        while queue:
            current = queue.popleft()
            for s in self._services.values():
                if current in s.depends_on and s.service_id not in seen:
                    seen.add(s.service_id)
                    order.append(s.service_id)
                    queue.append(s.service_id)
        return order

    def guess_service(self, free_text: str) -> ITService | None:
        """The service whose name/keywords best match the text, or None."""
        words = text.raw_words(free_text)
        best, best_hits = None, 0
        for s in self._services.values():
            hits = len((text.raw_words(s.name) | s.keywords) & words)
            if hits > best_hits:
                best, best_hits = s, hits
        return best


class Category:
    def __init__(self, name: str, description: str = "", keywords=()):
        self._name = name.upper()
        self._description = description or ""
        self._keywords = frozenset(k.lower() for k in keywords)

    name = property(lambda s: s._name)
    description = property(lambda s: s._description)
    keywords = property(lambda s: s._keywords)


@dataclass(frozen=True)
class CategorySuggestion:
    category: str
    confidence: float


class CategoryRegistry:
    def __init__(self):
        self._categories: dict[str, Category] = {}

    def register(self, category: Category) -> None:
        self._categories[category.name] = category

    def get(self, name: str) -> Category:
        try:
            return self._categories[name.upper()]
        except KeyError:
            raise CategoryNotFoundError(f"Category '{name}' does not exist.") from None

    def exists(self, name: str) -> bool:
        return name.upper() in self._categories

    def names(self) -> list[str]:
        return sorted(self._categories)

    def suggest(self, free_text: str) -> CategorySuggestion | None:
        """Intelligent Feature F: best keyword match + confidence (its share of all hits)."""
        words = text.raw_words(free_text)
        hits = {c.name: len(c.keywords & words) for c in self._categories.values()}
        hits = {k: v for k, v in hits.items() if v}
        if not hits:
            return None
        best = max(hits, key=hits.get)
        return CategorySuggestion(best, hits[best] / sum(hits.values()))

    @classmethod
    def with_defaults(cls) -> "CategoryRegistry":
        r = cls()
        defaults = {
            "HARDWARE": ("Physical devices", {"laptop", "printer", "monitor", "keyboard", "mouse", "device", "screen", "jammed"}),
            "SOFTWARE": ("Installed software", {"install", "crash", "crashes", "update", "license", "excel", "software"}),
            "NETWORK": ("Connectivity", {"wifi", "network", "internet", "vpn", "latency", "connection", "disconnects"}),
            "DATABASE": ("Databases", {"database", "db", "query", "sql", "table", "deadlock"}),
            "CLOUD": ("Cloud platforms", {"cloud", "aws", "azure", "bucket", "instance", "kubernetes"}),
            "SECURITY": ("Security events", {"phishing", "virus", "malware", "breach", "suspicious", "hacked"}),
            "AUTHENTICATION": ("Login and identity", {"login", "password", "sso", "otp", "locked", "authenticate", "signin"}),
            "APPLICATION": ("Business applications", {"payment", "transaction", "transactions", "portal", "app", "application", "checkout"}),
            "STORAGE": ("Disks and files", {"disk", "drive", "quota", "backup", "file", "files"}),
        }
        for name, (desc, kws) in defaults.items():
            r.register(Category(name, desc, kws))
        return r
