"""Document application service; tenant scope always comes from Principal."""
from iskra.security.principal import Principal
from iskra.documents.worker import parse_document_isolated


class DocumentService:
    """Coordinate parsing and storage without exposing request-level tenant IDs."""

    def __init__(self, repository, parser=None):
        self.repository = repository
        self.parser = parser or parse_document_isolated

    @staticmethod
    def _tenant_id(principal):
        if not isinstance(principal, Principal):
            raise PermissionError("Wymagana jest zweryfikowana tożsamość")
        if principal.tenant_id == "system":
            raise PermissionError("System administrator nie jest tenantem klienta")
        if not principal.roles.intersection({"member", "admin"}):
            raise PermissionError("Brak uprawnień do dokumentów")
        return principal.tenant_id

    def add_document(self, principal, filename, data):
        self._tenant_id(principal)
        parsed = self.parser(filename, data)
        return self.repository.add(principal, parsed)

    def list_documents(self, principal):
        self._tenant_id(principal)
        return self.repository.list(principal)

    def search_documents(self, principal, query, limit=5):
        self._tenant_id(principal)
        return self.repository.search(principal, query, limit)

    def delete_document(self, principal, document_id):
        if not isinstance(document_id, str) or not document_id or len(document_id) > 64:
            raise ValueError("Nieprawidłowy identyfikator dokumentu")
        self._tenant_id(principal)
        return self.repository.delete(principal, document_id)
