"""Storage contracts used to decouple domain logic from persistence backends."""
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class KnowledgeGraphStore(Protocol):
    """Minimal graph persistence contract; implementations own transaction safety."""

    def load(self) -> dict[str, Any]:
        """Return a validated graph snapshot with neurons and synapses."""
        ...

    def save(self, graph: dict[str, Any]) -> None:
        """Persist a complete validated graph snapshot atomically."""
        ...


@runtime_checkable
class KnowledgeGraphService(Protocol):
    """Domain-facing contract consumed by API and worker layers."""

    def snapshot(self) -> dict[str, Any]:
        """Return a detached graph snapshot."""
        ...

    def update(self, graph_delta: dict[str, Any]) -> None:
        """Validate and apply a graph delta."""
        ...
