import os
from pathlib import Path

from ...config import secret_file
from ..runtime import run
from .handler import handle

if os.environ.get("MASSIVE_API_KEY_FILE"):
    path = Path(os.environ["MASSIVE_API_KEY_FILE"])
    if path.is_file() and path.read_text().strip():
        os.environ["MASSIVE_API_KEY"] = secret_file(path)
run("scanner", handle)
