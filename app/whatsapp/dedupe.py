from pathlib import Path

from app.db import connect


class SeenMessages:
    """Remembers message ids, because Meta can deliver a webhook more than once."""

    def __init__(self, path: Path) -> None:
        self._db = connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS seen_messages (id TEXT PRIMARY KEY)"
        )
        self._db.commit()

    def claim(self, message_id: str) -> bool:
        """Return True the first time an id is seen, False after that."""
        cursor = self._db.execute(
            "INSERT OR IGNORE INTO seen_messages (id) VALUES (?)", (message_id,)
        )
        self._db.commit()
        return cursor.rowcount == 1

    def close(self) -> None:
        self._db.close()
