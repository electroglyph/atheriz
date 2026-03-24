# Re-export everything from atheriz.database_setup.
# Override or extend functions below to customize behavior.
from atheriz.database_setup import (  # noqa: F401
    Database,
    do_setup,
    get_database,
)

# def do_setup():
#     from atheriz.database_setup import do_setup as _base_do_setup
#     return _base_do_setup()

# def get_database():
#     from atheriz.database_setup import get_database as _base_get_database
#     return _base_get_database()

