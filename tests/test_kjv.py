import json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
s=r/"vendor/kjv2006/eng-kjv2006_usfx.xml"
p=json.loads((r/"build/build_report.json").read_text())
assert s.is_file() and s.stat().st_size
assert p["books"]==66 and p["verses"]==31102
assert p["words"]>0 and p["strongs_tags"]>0
assert len(list((r/"build/obsidian-kjv/KJV").rglob("*.md")))==31102
assert not (r/"build/bible_mt_tr.sqlite").exists()
print("PASS")
