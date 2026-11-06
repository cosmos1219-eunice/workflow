import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(SCRIPTS))


def load_example():
    brief = json.loads((EXAMPLES / "sample-brief.json").read_text(encoding="utf-8"))
    arts = json.loads((EXAMPLES / "sample-articles.json").read_text(encoding="utf-8"))
    return brief, arts
