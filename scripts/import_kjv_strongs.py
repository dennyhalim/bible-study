#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, shutil, urllib.error, urllib.request, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/"build"; RAW=BUILD/"raw"/"ebible"; VAULT=BUILD/"obsidian-kjv"
VENDORED=ROOT/"vendor/kjv2006/eng-kjv2006_usfx.xml"
SOURCE_URL="https://ebible.org/Scriptures/eng-kjv2006_usfx.zip"
SOURCE_PAGE="https://ebible.org/find/show.php?id=eng-kjv2006"
SOURCE_XML="eng-kjv2006_usfx.xml"

BOOKS=[
("GEN","Genesis"),("EXO","Exodus"),("LEV","Leviticus"),("NUM","Numbers"),("DEU","Deuteronomy"),
("JOS","Joshua"),("JDG","Judges"),("RUT","Ruth"),("1SA","1 Samuel"),("2SA","2 Samuel"),
("1KI","1 Kings"),("2KI","2 Kings"),("1CH","1 Chronicles"),("2CH","2 Chronicles"),
("EZR","Ezra"),("NEH","Nehemiah"),("EST","Esther"),("JOB","Job"),("PSA","Psalms"),
("PRO","Proverbs"),("ECC","Ecclesiastes"),("SNG","Song of Solomon"),("ISA","Isaiah"),
("JER","Jeremiah"),("LAM","Lamentations"),("EZK","Ezekiel"),("DAN","Daniel"),
("HOS","Hosea"),("JOL","Joel"),("AMO","Amos"),("OBA","Obadiah"),("JON","Jonah"),
("MIC","Micah"),("NAM","Nahum"),("HAB","Habakkuk"),("ZEP","Zephaniah"),("HAG","Haggai"),
("ZEC","Zechariah"),("MAL","Malachi"),("MAT","Matthew"),("MRK","Mark"),("LUK","Luke"),
("JHN","John"),("ACT","Acts"),("ROM","Romans"),("1CO","1 Corinthians"),("2CO","2 Corinthians"),
("GAL","Galatians"),("EPH","Ephesians"),("PHP","Philippians"),("COL","Colossians"),
("1TH","1 Thessalonians"),("2TH","2 Thessalonians"),("1TI","1 Timothy"),("2TI","2 Timothy"),
("TIT","Titus"),("PHM","Philemon"),("HEB","Hebrews"),("JAS","James"),("1PE","1 Peter"),
("2PE","2 Peter"),("1JN","1 John"),("2JN","2 John"),("3JN","3 John"),("JUD","Jude"),("REV","Revelation")]
BOOK=dict(BOOKS); ORDER={b:i for i,(b,_) in enumerate(BOOKS)}
SKIP={"f","ef","x","ex","fig","periph","sidebar","rem","rq","xt","xot","xnt","xdc","xk","xq","xo","xta","jmp","milestone"}

def tag(n): return n.rsplit("}",1)[-1].lower()
def norm(s): return " ".join(s.split())
def sha256(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda:f.read(1048576),b""): h.update(c)
    return h.hexdigest()

def download(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(url,headers={"User-Agent":"BibleStudy-KJV-Strong-Importer/4.0"})
    with urllib.request.urlopen(req,timeout=180) as r:
        data=r.read()
    if not data: raise RuntimeError("empty download")
    path.write_bytes(data)

def strongs(node):
    out=[]
    for k,v in node.attrib.items():
        if k.lower() in {"s","strong","lemma","l"} or "strong" in k.lower():
            for x in re.findall(r"\b[GH]\d{1,5}\b",v.upper()):
                if x not in out: out.append(x)
    return out

def parse(path):
    root=ET.parse(path).getroot(); verses={}
    for bn in root.iter():
        if tag(bn.tag)!="book": continue
        book=(bn.attrib.get("id") or "").upper().split()[0]
        if book not in BOOK: continue
        chapter=None; active=None
        def add(k,s):
            if k and s:
                s=norm(s)
                if s: verses[k]["parts"].append(s)
        def walk(n,k):
            nonlocal chapter,active
            t=tag(n.tag)
            if t=="c":
                m=re.search(r"\d+",n.attrib.get("id") or n.attrib.get("number") or "")
                if m: chapter=int(m.group())
                return k
            if t=="v":
                raw=n.attrib.get("id") or n.attrib.get("bcv") or n.attrib.get("number") or ""
                # Handles both chapter.verse and simple verse milestone forms.
                m=re.search(r"(?:^|[.\s])(\d+)\.(\d+)(?:\D|$)",raw)
                if m: chapter,verse=int(m.group(1)),int(m.group(2))
                else:
                    m=re.search(r"\d+",raw)
                    if not m or chapter is None: return k
                    verse=int(m.group())
                active=(book,chapter,verse)
                verses.setdefault(active,{"parts":[],"words":[]})
                return active
            if t in SKIP: return k
            if t=="w":
                if k:
                    text=norm("".join(n.itertext()))
                    if text:
                        verses[k]["words"].append({
                            "text":text,"strongs":strongs(n),
                            "lemma":n.attrib.get("l") or n.attrib.get("lemma") or "",
                            "morphology":n.attrib.get("m") or n.attrib.get("x-morph") or ""})
                        verses[k]["parts"].append(text)
                    add(k,n.tail)
                return k
            add(k,n.text)
            for ch in n:
                k=walk(ch,k); add(k,ch.tail)
            return k
        for ch in bn: active=walk(ch,active)
    for v in verses.values():
        s=norm(" ".join(v.pop("parts")))
        s=re.sub(r"\s+([,.;:!?])",r"\1",s)
        s=re.sub(r"\s+([’'”)\]])",r"\1",s)
        v["text"]=s
    if len(verses)!=31102: raise RuntimeError(f"expected 31102 verses, got {len(verses)}")
    words=sum(len(v["words"]) for v in verses.values())
    tags=sum(len(w["strongs"]) for v in verses.values() for w in v["words"])
    if not words: raise RuntimeError("no word records found")
    if not tags: raise RuntimeError("no Strong's tags found")
    return verses

def validate(p):
    v=parse(p)
    return {"books":66,"verses":len(v),"word_records":sum(len(x["words"]) for x in v.values()),
            "strongs_tags":sum(len(w["strongs"]) for x in v.values() for w in x["words"])}

def source(refresh):
    VENDORED.parent.mkdir(parents=True,exist_ok=True)
    if not refresh and VENDORED.is_file() and VENDORED.stat().st_size:
        validate(VENDORED); print("Using committed source"); return VENDORED,"committed"
    archive=RAW/"eng-kjv2006_usfx.zip"
    try:
        print("Downloading eBible.org KJV2006 USFX...")
        download(SOURCE_URL,archive)
        ext=RAW/"source"; shutil.rmtree(ext,ignore_errors=True); ext.mkdir(parents=True)
        with zipfile.ZipFile(archive) as z:
            hits=[n for n in z.namelist() if Path(n).name==SOURCE_XML]
            if len(hits)!=1: raise RuntimeError(f"expected {SOURCE_XML}, found {hits}")
            z.extract(hits[0],ext)
            candidate=ext/hits[0]
        validate(candidate)
        shutil.copy2(candidate,VENDORED)
        return VENDORED,"downloaded-and-committed"
    except Exception as e:
        if VENDORED.is_file() and VENDORED.stat().st_size:
            validate(VENDORED); print(f"Refresh failed; using committed source: {e}")
            return VENDORED,"committed-fallback"
        raise

def build(v):
    if VAULT.exists(): shutil.rmtree(VAULT)
    (VAULT/"_meta").mkdir(parents=True)
    (VAULT/"_meta/README.md").write_text(
        f"# KJV + Strong's\n\nSource: [eBible.org KJV2006]({SOURCE_PAGE})\n\n"
        f"Canonical source: `{SOURCE_XML}`.\n",encoding="utf-8")
    words=stags=0
    for (code,ch,vs),d in sorted(v.items(),key=lambda x:(ORDER[x[0][0]],x[0][1],x[0][2])):
        book=BOOK[code]; rendered=[]; rows=["| # | KJV word | Strong's | Lemma | Morphology |","|---:|---|---|---|---|"]
        for i,w in enumerate(d["words"],1):
            ids=w["strongs"]; rendered.append(f"**{w['text']}** "+" ".join(f"[[Strong's {x}]]" for x in ids))
            rows.append(f"| {i} | {w['text']} | {', '.join(ids)} | {w['lemma']} | {w['morphology']} |")
            words+=1; stags+=len(ids)
        text=f"""---
type: verse
translation: KJV
source: eBible.org
edition: eng-kjv2006
book: {book}
chapter: {ch}
verse: {vs}
---

# {book} {ch}:{vs}

## KJV

{d['text']}

## KJV + Strong's

{' '.join(rendered)}

## Word table

{chr(10).join(rows)}
"""
        p=VAULT/"KJV"/book/str(ch)/f"{vs:03d}.md"; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding="utf-8")
    return {"books":66,"verses":31102,"words":words,"strongs_tags":stags}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--refresh",action="store_true"); args=ap.parse_args()
    if (BUILD/"bible_mt_tr.sqlite").exists(): raise RuntimeError("KJV importer refuses to touch bible_mt_tr.sqlite")
    BUILD.mkdir(parents=True,exist_ok=True)
    p,mode=source(args.refresh); r=build(parse(p))
    r["source"]={"provider":"eBible.org","id":"eng-kjv2006","xml":SOURCE_XML,"archive":SOURCE_URL,
                 "source_page":SOURCE_PAGE,"sha256":sha256(p),"bytes":p.stat().st_size,
                 "acquisition":mode,"vendored":str(VENDORED.relative_to(ROOT))}
    (BUILD/"build_report.json").write_text(json.dumps(r,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (BUILD/"source_manifest.json").write_text(json.dumps({"source":r["source"],"validation":r},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

if __name__=="__main__": main()
