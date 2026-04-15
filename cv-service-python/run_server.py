import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".pydeps"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from uvicorn.main import main


if __name__ == "__main__":
    sys.argv = ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]
    main()
