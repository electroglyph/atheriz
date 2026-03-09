from typing import Any
from fastapi import FastAPI

class BaseProtocol:
    """
    Interface for protocol lifecycle hooks.
    """

    # pyrefly: ignore
    @classmethod
    def setup(cls, app: FastAPI):
        """
        Required classmethod called during application startup.
        Should register any necessary endpoints, lifespan tasks, or background workers
        with the FastAPI app object.
        """
        raise NotImplementedError
