"""Document application service; tenant scope always comes from Principal."""
from iskra.security.principal import Principal
from iskra.documents.parsers import parse_document


class DocumentService:
    """Coordinate parsing and storage without exposing request-level tenant IDs."""

    def __init__(self, repository):
        self.repository = repository

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
        tenant_id = self._tenant_id(principal)
        parsed = parse_document(filename, data)
        return self.repository.add(tenant_id, parsed)

    def list_documents(self, principal):
        return self.repository.list(self._tenant_id(principal))

    def search_documents(self, principal, query, limit=5):
        return self.repository.search(self._tenant_id(principal), query, limit)

    def delete_document(self, principal, document_id):
        if not isinstance(document_id, str) or not document_id or len(document_id) > 64:
            raise ValueError("Nieprawidłowy identyfikator dokumentu")
        return self.repository.delete(self._tenant_id(principal), document_id)
