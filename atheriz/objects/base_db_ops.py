import dill

class DbOps:
    def get_save_ops(self) -> tuple[str, tuple]:
        """
        Returns a tuple of (sql, params) for saving this object.
        """
        sql = "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)"
        with self.lock:
            had_flag = getattr(self, "is_modified", False)
            object.__setattr__(self, "is_modified", False)
            try:
                blob = dill.dumps(self)
            finally:
                object.__setattr__(self, "is_modified", had_flag)
        return sql, (self.id, blob)

    def get_save_ops_clearing(self) -> tuple[str, tuple]:
        """
        Like get_save_ops, but consumes is_modified atomically with
        serialization: the flag is left cleared once the blob reflects the
        object state, so any mutation after this critical section re-raises
        the flag and survives the next checkpoint instead of being lost.

        On serialization failure the flag is restored and the exception
        propagates; save_objects() additionally re-marks attempted objects on
        rollback.
        """
        sql = "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)"
        with self.lock:
            had_flag = getattr(self, "is_modified", False)
            object.__setattr__(self, "is_modified", False)
            try:
                blob = dill.dumps(self)
            except Exception:
                object.__setattr__(self, "is_modified", had_flag)
                raise
            return sql, (self.id, blob)

    def get_del_ops(self) -> tuple[str, tuple]:
        """
        Returns a tuple of (sql, params) for deleting this object.
        """
        return "DELETE FROM objects WHERE id = ?", (self.id,)