from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def add_timezone_import(text: str) -> str:
    if "datetime.utcnow" not in text:
        return text
    if "from datetime import datetime, timezone" in text:
        return text
    if "from datetime import datetime," in text:
        return text.replace("from datetime import datetime,", "from datetime import datetime, timezone,", 1)
    if "from datetime import datetime" in text:
        return text.replace("from datetime import datetime", "from datetime import datetime, timezone", 1)
    return text


def clean_datetime(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "datetime.utcnow" not in text:
        return
    text = add_timezone_import(text)
    text = text.replace("datetime.utcnow()", "datetime.now(timezone.utc).replace(tzinfo=None)")
    path.write_text(text, encoding="utf-8")


def clean_fastapi_lifespan(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "@app.on_event(\"startup\")" not in text:
        return
    if "from contextlib import asynccontextmanager" not in text:
        text = text.replace("from datetime import datetime, timezone\n", "from contextlib import asynccontextmanager\nfrom datetime import datetime, timezone\n", 1)
    old_constructor = 'app = FastAPI(title="MetroCRM", version="0.4.0")'
    new_constructor = '''@asynccontextmanager\nasync def lifespan(_: FastAPI):\n    Base.metadata.create_all(bind=engine)\n    start_backup_scheduler()\n    try:\n        yield\n    finally:\n        stop_backup_scheduler()\n\n\napp = FastAPI(title="MetroCRM", version="0.4.0", lifespan=lifespan)'''
    text = text.replace(old_constructor, new_constructor, 1)
    old_events = '''@app.on_event("startup")\ndef startup() -> None:\n    Base.metadata.create_all(bind=engine)\n    start_backup_scheduler()\n\n\n@app.on_event("shutdown")\ndef shutdown() -> None:\n    stop_backup_scheduler()\n\n\n'''
    text = text.replace(old_events, "", 1)
    path.write_text(text, encoding="utf-8")


for path in list((ROOT / "app").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
    clean_datetime(path)

clean_fastapi_lifespan(ROOT / "app" / "main.py")

result = subprocess.run(["git", "status", "--short"], cwd=ROOT, text=True, capture_output=True, check=True)
if result.stdout.strip():
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
    subprocess.run(["git", "add", "app", "tests"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", "chore: remove deprecated datetime and FastAPI lifecycle APIs"], cwd=ROOT, check=True)
    subprocess.run(["git", "push"], cwd=ROOT, check=True)
