from pathlib import Path

from fastapi.templating import Jinja2Templates


WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")
