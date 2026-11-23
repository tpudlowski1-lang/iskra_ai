"""Filesystem path validation for private SQLite stores."""
import os
import stat


def ensure_private_parent(database_path):
    """Create a private final parent while rejecting symlinks in every path component.

    The component walk uses lstat before creating each missing directory. This
    prevents ordinary symlink traversal during path preparation; it does not
    eliminate races against an untrusted process that can mutate ancestors.
    """
    parent = os.path.dirname(os.path.abspath(database_path))
    current = os.path.abspath(os.sep)
    for component in parent.split(os.sep):
        if not component:
            continue
        current = os.path.join(current, component)
        try:
            os.mkdir(current, 0o700)
        except FileExistsError:
            pass
        metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise OSError("Ścieżka bazy danych zawiera symlink lub element niebędący katalogiem")

    metadata = os.stat(parent, follow_symlinks=False)
    if metadata.st_mode & stat.S_ISVTX and metadata.st_mode & 0o002:
        raise OSError("Baza danych nie może znajdować się bezpośrednio w katalogu współdzielonym")
    os.chmod(parent, 0o700)
    return parent
