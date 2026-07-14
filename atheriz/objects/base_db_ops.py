import dill

class DbOps:
    def get_save_ops(self) -> tuple[str, tuple]:
        """
        Returns a tuple of (sql, params) for saving this object.
        """
        sql = "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)"
        with self.lock:
            object.__setattr__(self, "is_modified", False)
            try:
                blob = dill.dumps(self)
            except Exception:
                object.__setattr__(self, "is_modified", True)
                raise
            params = (self.id, blob)
        return sql, params

    def get_del_ops(self) -> tuple[str, tuple]:
        """
        Returns a tuple of (sql, params) for deleting this object.
        """
        return "DELETE FROM objects WHERE id = ?", (self.id,)