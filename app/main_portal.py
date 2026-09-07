"""Production entrypoint that loads the core app and the separated login portals."""

from app import main
from app import portal  # noqa: F401,E402

app = main.app
