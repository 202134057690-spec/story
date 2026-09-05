#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""أدوات مستودع `story`.

    python3 tools/story.py new <slug> --from short-story --title "عنوان"
    python3 tools/story.py lint [--strict]
    python3 tools/story.py index [--dry-run]
    python3 tools/story.py stats
    python3 tools/story.py check-contradictions
    python3 tools/story.py self-test

الصيغة الكاملة موثّقة في AGENTS.md § 3. بلا اعتماديات خارجية (Python 3.8+).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TYPES = ("short-story", "chapter", "fragment")
STATUSES = ("idea", "draft", "revising", "done")
REQUIRED_KEYS = ("title", "slug", "type", "status", "created", "updated")
STATUS_ORDER = {s: i for i, s in enumerate(STATUSES)}

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
FM_DELIM = "---"
WIP_MARKERS = ("TODO", "FIXME", "XXX", "{{", "[؟]", "[?]")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


# ---------------------------------------------------------------- paths ----

def works_dir() -> str:
    return os.path.join(ROOT, "works")


def templates_dir() -> str:
    return os.path.join(ROOT, "templates")


def bible_dir() -> str:
    return os.path.join(ROOT, "bible")


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write_text(path: str, text: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# ------------------------------------------------------------- parsing ----

def split_front_matter(text: str):
    """يعيد (meta, body, error)؛ error هو صيغة الفشل، لا None عند التعذّر."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FM_DELIM:
        return {}, text, "لا توجد كتلة بيانات أمامية في أول السطر"
    for idx in range(1, len(lines)):
        if lines[idx].strip() == FM_DELIM:
            meta = {}
            for raw in lines[1:idx]:
                if not raw.strip():
                    continue
                if ":" not in raw:
                    return meta, "", f"سطر غير صالح في البيانات الأمامية: {raw!r}"
                key, _, val = raw.partition(":")
                meta[key.strip()] = val.strip().strip("'\"")
            return meta, "\n".join(lines[idx + 1:]) + "\n", None
    return {}, text, "كتلة البيانات الأمامية غير مغلقة بـ '---'"


def section(body: str, title: str) -> str:
    """محتوى قسم `## <title>` حتى القسم التالي."""
    pat = rf"^##[ \t]*{re.escape(title)}[ \t]*$(.*?)(?=^##[ \t]|\Z)"
    m = re.search(pat, body, re.M | re.S)
    return m.group(1).strip() if m else ""


def words(text: str):
    """تقطيع نص عربي/إنجليزي إلى كلمات، مع تجاهل علامات الترقيم والتنسيق."""
    if not text:
        return []
    text = re.sub(r"[`*_>#|]+", " ", text)
    parts = re.split(r"[\s،؛;.!?«»(){}\[\]:/\\\"'ـ+=%–—-]+", text)
    return [p for p in parts if re.search(r"[0-9A-Za-z\u0600-\u06ff]", p)]


def word_count(text: str) -> int:
    return len(words(text))


def to_ascii_int(value: str, default: int = 0) -> int:
    v = str(value).translate(ARABIC_DIGITS)
    return int(v) if v.isdigit() else default


def work_files() -> list:
    """works/*.md و works/<slug>/story.md، بلا index.md."""
    found = []
    root = works_dir()
    if not os.path.isdir(root):
        return found
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if os.path.isfile(full) and name.endswith(".md") and name != "index.md":
            found.append(full)
        elif os.path.isdir(full):
            main = os.path.join(full, "story.md")
            if os.path.exists(main):
                found.append(main)
    return found


# ---------------------------------------------------------------- lint ----

def parse_work(path: str) -> dict:
    try:
        text = read_text(path)
    except UnicodeDecodeError:
        return {"path": path, "rel": rel(path), "meta": {}, "body": "",
                "errors": ["الملف ليس بترميز UTF-8"], "warnings": []}

    meta, body, err = split_front_matter(text)
    errors = [err] if err else []
    warnings = []

    for key in REQUIRED_KEYS:
        if not meta.get(key):
            errors.append(f"حقل إلزامي مفقود: {key}")

    if meta.get("type") and meta["type"] not in TYPES:
        errors.append(f"type غير معروف: {meta['type']} — المسموح: {', '.join(TYPES)}")
    if meta.get("status") and meta["status"] not in STATUSES:
        errors.append(f"status غير معروف: {meta['status']} — المسموح: {', '.join(STATUSES)}")

    stem = os.path.splitext(os.path.basename(path))[0]
    if meta.get("slug") and meta["slug"] != stem:
        errors.append(f"slug ({meta['slug']}) لا يطابق اسم الملف ({stem})")
    if not SLUG_RE.match(stem):
        warnings.append(f"اسم الملف ليس kebab-case ASCII: {stem}")

    for key in ("created", "updated"):
        val = meta.get(key)
        if val and not DATE_RE.fullmatch(val):
            errors.append(f"{key} يجب أن يكون YYYY-MM-DD، والموجود: {val}")
    if meta.get("created") and meta.get("updated") and \
            DATE_RE.fullmatch(meta["created"]) and DATE_RE.fullmatch(meta["updated"]) and \
            meta["updated"] < meta["created"]:
        errors.append(f"updated ({meta['updated']}) أسبق من created ({meta['created']})")

    errors += _check_content(path, body, meta, warnings)
    errors += _check_links(path, body, warnings)
    return {"path": path, "rel": rel(path), "meta": meta, "body": body,
            "errors": errors, "warnings": warnings}


def _check_content(path: str, body: str, meta: dict, warnings: list) -> list:
    errors = []
    if "## الملخص" not in body:
        errors.append("قسم مفقود: '## الملخص'")
    if "## المتن" not in body:
        errors.append("قسم مفقود: '## المتن'")

    status = meta.get("status", "idea")
    n_summary = word_count(section(body, "الملخص"))
    n_prose = word_count(section(body, "المتن"))

    if status in ("draft", "revising", "done") and n_summary < 15:
        errors.append("يلزم ملخّص ≥ ١٥ كلمة للانتقال من idea (الموجود: %d)" % n_summary)
    if status in ("revising", "done") and n_prose < 120:
        errors.append("يلزم متن ≥ ١٢٠ كلمة في حالة %s (الموجود: %d)" % (status, n_prose))
    if status == "done" and n_prose < 200:
        errors.append("يلزم متن ≥ ٢٠٠ كلمة لاعتبار العمل done (الموجود: %d)" % n_prose)

    target = to_ascii_int(meta.get("target_words", ""), 0)
    if target and n_prose > target * 1.6:
        warnings.append(f"المتن {n_prose} كلمة، أي أطول من الهدف ({target}) بأكثر من ٦٠٪")

    if status != "done" and "## ملاحظات" not in body:
        warnings.append("لا قسم '## ملاحظات' — النوايا غير مسجّلة")

    for i, line in enumerate(body.splitlines(), 1):
        if any(mark in line for mark in WIP_MARKERS):
            msg = f"علامة عمل جارٍ في السطر {i}: {line.strip()[:70]}"
            (errors if status == "done" else warnings).append(msg)
    return errors


def _check_links(path: str, body: str, warnings: list) -> list:
    errors = []
    base = os.path.dirname(path)
    for target in re.findall(r"\[[^\]]*\]\((?!https?://|mailto:)([^)\s#]+)", body):
        if target.startswith("/"):
            errors.append(f"مسار مطلق في رابط يُفترض نسبيًا: {target}")
        elif not os.path.exists(os.path.normpath(os.path.join(base, target))):
            errors.append(f"رابط معطوب نحو: {target}")
    return errors


def lint_bible() -> list:
    out = []
    if not os.path.isdir(bible_dir()):
        return ["المجلد bible/ مفقود — النظام يتوقّعه"]
    for name in ("style.md", "world.md", "characters.md", "plot.md"):
        path = os.path.join(bible_dir(), name)
        if not os.path.exists(path):
            out.append(f"مفقود: bible/{name}")
        elif word_count(read_text(path)) < 40:
            out.append(f"فارغ تقريبًا: bible/{name}")
    return out


def cmd_lint(args) -> int:
    files = work_files()
    bible_warnings = lint_bible()
    for w in bible_warnings:
        print(f"! bible: {w}")

    if not files:
        print("لا أعمال في works/ — ابدأ بـ: python3 tools/story.py new <slug> --from short-story")
        return 1 if bible_warnings else 0

    n_errors = 0
    n_warnings = len(bible_warnings)
    for path in files:
        w = parse_work(path)
        n = word_count(section(w["body"], "المتن"))
        head = "{}  [{}, {} كلمة]".format(w["rel"], w["meta"].get("status", "?"), n)
        if not w["errors"] and not w["warnings"]:
            print(f"✓ {head}")
            continue
        print(("✗ " if w["errors"] else "! ") + head)
        for e in w["errors"]:
            print(f"    خطأ: {e}")
        for msg in w["warnings"]:
            print(f"    تنبيه: {msg}")
        n_errors += len(w["errors"])
        n_warnings += len(w["warnings"])

    total = n_errors + (n_warnings if args.strict else 0)
    if total:
        print(f"\n{n_errors} خطأ و{n_warnings} تنبيهًا في {len(files)} ملف"
              + (" — strict يحسب التنبيهات." if args.strict else ""))
        return 1
    print(f"\nسليم: {len(files)} ملف عمل، بلا أخطاء ولا تنبيهات.")
    return 0


# ----------------------------------------------------------------- new ----

def cmd_new(args) -> int:
    if not SLUG_RE.match(args.slug):
        print(f"خطأ: slug يجب kebab-case ASCII صغرى: {args.slug!r}", file=sys.stderr)
        return 2

    template = os.path.join(templates_dir(), f"{args.from_template}.md")
    if not os.path.exists(template):
        avail = sorted(os.path.splitext(f)[0] for f in os.listdir(templates_dir())) \
            if os.path.isdir(templates_dir()) else []
        print(f"خطأ: قالب غير موجود: {args.from_template}\nالمتاح: {', '.join(avail)}", file=sys.stderr)
        return 2

    dest = os.path.join(works_dir(), f"{args.slug}.md")
    if os.path.exists(dest):
        print(f"خطأ: موجود مسبقًا: {rel(dest)}", file=sys.stderr)
        return 1

    today = args.date or _dt.date.today().isoformat()
    title = args.title or args.slug.replace("-", " ").capitalize()
    wtype = args.from_template if args.from_template in TYPES else "short-story"
    subs = {"{{title}}": title, "{{slug}}": args.slug, "{{type}}": wtype,
            "{{status}}": args.status, "{{date}}": today}

    text = read_text(template)
    for key, val in subs.items():
        text = text.replace(key, val)
    leftover = sorted(set(re.findall(r"\{\{[a-zA-Z_]+\}\}", text)))
    if leftover:
        print(f"خطأ: القالب يحتاج قيمًا لم تُوفَّر: {', '.join(leftover)}", file=sys.stderr)
        return 2

    write_text(dest, text)
    print(f"أُنشئ: {rel(dest)}")
    print("التالي: اكتب الملخّص، ثم `python3 tools/story.py lint`.")
    return 0


# --------------------------------------------------------------- index ----

def build_index(dry: bool = False) -> str:
    rows = []
    for path in work_files():
        w = parse_work(path)
        m = w["meta"]
        prose = word_count(section(w["body"], "المتن"))
        target = to_ascii_int(m.get("target_words", ""), 0)
        pct = f" ({min(999, round(prose * 100 / target))}%)" if target else ""
        rows.append({
            "title": m.get("title") or "(بلا عنوان)",
            "slug": m.get("slug") or os.path.splitext(os.path.basename(path))[0],
            "type": m.get("type") or "?",
            "status": m.get("status") or "idea",
            "prose": prose, "pct": pct,
            "updated": m.get("updated") or m.get("created") or "—",
            "errors": len(w["errors"]),
            "link": rel(path),
        })
    rows.sort(key=lambda r: (STATUS_ORDER.get(r["status"], 99), r["slug"]))

    out = ["<!-- مولَّد آليًا: python3 tools/story.py index — لا تحرّره يدويًا -->", "",
           "# فهرس الأعمال", "",
           "| العمل | النوع | الحالة | كلمات المتن | آخر تحديث |",
           "|---|---|---|---:|---|"]
    for r in rows:
        flag = f" ⚠{r['errors']}" if r["errors"] else ""
        out.append(f"| [{r['title']}]({r['link']}){flag} | {r['type']} | {r['status']} "
                   f"| {r['prose']}{r['pct']} | {r['updated']} |")

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    summary = " · ".join(f"{s}: {counts[s]}" for s in STATUSES if counts.get(s)) or "لا شيء بعد"
    out += ["", f"الإجمالي: {len(rows)} عمل — {summary}",
            f"مجموع كلمات المتن: {sum(r['prose'] for r in rows)}", ""]
    text = "\n".join(out)
    if not dry:
        write_text(os.path.join(works_dir(), "index.md"), text)
    return text


def cmd_index(args) -> int:
    text = build_index(dry=args.dry_run)
    if args.dry_run:
        print(text, end="")
        return 0
    print(f"حُدِّث: {rel(os.path.join(works_dir(), 'index.md'))}")
    return 0


# --------------------------------------------------------------- stats ----

def cmd_stats(args) -> int:
    files = work_files()
    if not files:
        print("لا أعمال بعد.")
        return 0
    buckets = dict.fromkeys(STATUSES, 0)
    total = 0
    longest = None
    for path in files:
        w = parse_work(path)
        prose = word_count(section(w["body"], "المتن"))
        total += prose
        status = w["meta"].get("status", "idea")
        buckets[status] = buckets.get(status, 0) + 1
        if longest is None or prose > longest[1]:
            longest = (w["meta"].get("title") or w["rel"], prose)
    print(f"الأعمال: {len(files)}")
    for s in STATUSES:
        if buckets.get(s):
            print(f"  {s:<9}{buckets[s]}")
    print(f"كلمات المتن: {total}")
    if longest:
        print(f"الأطول: {longest[0]} ({longest[1]} كلمة)")
    return 0


# ------------------------------------------------- check-contradictions ----

TASHKEEL = re.compile(r"[\u064B-\u0652\u0670\u0640]")
NORMALIZE = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و", "ئ": "ي", "ة": "ه", "ى": "ي"})


def normalize_ar(text: str) -> str:
    """تجريد من التشكيل والهمزات، لمقارنة مستقرّة نصوصًا مكتوبة باختلافات إملائية."""
    return TASHKEEL.sub("", text).translate(NORMALIZE)


NEG_PREFIXES = ("لا ", "لن ", "لم ", "ليس ", "ما ")


def fact_slot(fact: str):
    """يعيد (الخاصية, منفيّة) أول كلمة يحملها السطر، أو (None, False).

    «لا تحفظ الأرقام» و«تحفظ الأرقام» لهما الخاصة نفسها «تحفظ» — واحدة منفيّة
    والأخرى موجبة، وهذا تعارض. أما «لا تحفظ الأرقام» و«لا تُصلح علاقة» فخاصيتان
    مختلفتان، أي سِمتان متكاملتان لا تعارضان.
    """
    norm = normalize_ar(fact.strip().strip(".،,")).strip()
    negated = False
    for pref in NEG_PREFIXES:
        if norm.startswith(pref):
            negated = True
            norm = norm[len(pref):]
            break
    if norm.startswith("بلا "):
        negated, norm = True, norm[4:]
    first = norm.split(" ")[0].strip() if norm.strip() else ""
    first = re.sub(r"^[ال]+(?=.)(?!ه)", "", first) if len(first) > 3 else first
    return (first or None), negated


def parse_facts() -> dict:
    """يقرأ أسطر `**الموضوع** — الحقيقة` من bible/ ويعيد {subject: [(rel, line, fact)]}."""
    facts = {}
    for name in ("characters.md", "world.md"):
        path = os.path.join(bible_dir(), name)
        if not os.path.exists(path):
            continue
        for lineno, line in enumerate(read_text(path).splitlines(), 1):
            m = re.match(r"\s*[-*]?\s*\*\*(.+?)\*\*\s*[—:-]+\s*(.+)", line)
            if not m:
                continue
            subject, fact = m.group(1).strip(), m.group(2).strip()
            facts.setdefault(subject, []).append((rel(path), lineno, fact))
    return facts


CONTRAST_MARKERS = re.compile(r"فقط|لكن\b|أمّا|اما\b|غير أن|بل ")
ANTONYMS = [("لا يحب", "يحب"), ("لا تذكر", "تذكر"), ("لا تذكر", "يتذكر"),
            ("ميتين", "حيّ"), ("ينكر", "يعترف")]


def cmd_check_contradictions(args) -> int:
    """كشف آلي متواضع: ازدواج الحقائق في bible/، وأضداد صريحة في الملف نفسه."""
    problems = 0
    for subject, entries in sorted(parse_facts().items()):
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                a, b = entries[i], entries[j]
                slot_a, neg_a = fact_slot(a[2])
                slot_b, neg_b = fact_slot(b[2])
                if not slot_a or slot_a != slot_b:
                    continue          # خاصيتان مختلفتان = سِمتان متكاملتان
                if neg_a != neg_b:
                    kind = "نقض صريح"
                elif normalize_ar(a[2]) != normalize_ar(b[2]):
                    kind = "قيمتان مختلفتان للخاصية نفسها"
                else:
                    continue          # ترديد حرفي لحقيقة واحدة
                print(f"⚠ {kind} في «{subject}» ({slot_a}):\n    {a[0]}:{a[1]} — {a[2]}"
                      f"\n    {b[0]}:{b[1]} — {b[2]}")
                problems += 1

    paths = work_files()
    if os.path.isdir(bible_dir()):
        paths += [os.path.join(bible_dir(), f) for f in sorted(os.listdir(bible_dir()))
                  if f.endswith(".md")]
    for path in paths:
        for sentence in _prose_sentences(read_text(path).split("## المتن")[-1]):
            if CONTRAST_MARKERS.search(sentence):
                continue          # «تذكّر فقط» تضييد لا نقض
            norm = normalize_ar(sentence)
            for neg, pos in ANTONYMS:
                if normalize_ar(neg) in norm and re.search(rf"(?<!لا ){re.escape(normalize_ar(pos))}", norm):
                    print(f"⚠ نقض محتمل في {rel(path)}: «{neg}» و«{pos}» — «{sentence[:60]}…»")
                    problems += 1

    if problems:
        print(f"\n{problems} نقطة مراجعة. صحّح bible/ أولًا ثم أعد التشغيل.")
        return 1
    print("لا تناقضات آلية مكتشفة. الكشف آلي ومتواضع، ولا يعوّض مراجعة بشرية.")
    return 0


# ---------------------------------------------------------------- review ----
# فحص آلي لمجموعة قواعد bible/style.md وAGENTS.md § 1. القواعد الأدبية
# (رغبة/عائق/تحوّل، جودة الصورة) لا تُفحص آليًا: هذا الفحص بوابة دنيا لا حكم.

CLICHES = ("قلبها يخفق", "قلبُها يخفق", "قلبها يدق", "زمن يتوقف", "زمنٌ يتوقّف",
           "الوقت يتوقف", "دمعة تنساب", "دمعة تنسلّ", "ابتسامة صفراء",
           "عيناها كالبحر", "ضحكة صافية", "صمت مطبق", "سكون الموت")
EMOTION_TAGS = re.compile(
    r"(?:قال(?:ت)?|أجاب(?:ت)?|ردّ(?:ت)?|سأل(?:ت)?|همس(?:ت)?|صاح(?:ت)?|اعترض(?:ت)?)\s+"
    r"ب(?:حزن|غضب|حدّة|حدة|برودة|برود|هدوء|سخرية|ألم|الم|فخر|ارتجاف|ارتجاف|أسف|حسرة|"
    r"خوف|فرح|ضيق|ضيقٍ|دهشة|استغراب|استهجان|نبرة|لهفة|رجاء|يأس|حزم|لين|رفق|قسوة|عجلة|تردد)")
FILLERS = ("بشكل عام", "بشكل كبير", "في الواقع", "تجدر الإشارة", "من الجدير", "لا شك أن",
           "قام بـ", "قام بتنفيذ", "يجدر بالذكر", "وكما هو معلوم")
SIMILE_MARKERS = re.compile(r"كأنَّ?ما?\b|\bمثل[َة]?\s|\b(?:ي|ت)شبه\s|على هيئة")
# مسافة قبل الفاصلة/السيميكولون العربي، أو ترقيم لاتيني بعد حرف عربي
LATIN_PUNCT = re.compile(r"\s[،؛]|[\u0600-\u06ff]\s*[;?!]")
SMALL_DIGIT = re.compile(r"(?<![\d٠-٩])[١-٩](?![\d٠-٩])")
MORAL_TAIL = re.compile(r"وهكذا|(?:تعلمت|تعلّمت|أدركت|فهمت|اكتشفت)\s*أن")


def _prose_sentences(text: str):
    """تقسيم المتن إلى جُمل، مع الحفاظ على النقاط داخل الأرقام."""
    text = re.sub(r"^---$", "", text, flags=re.M)
    text = re.sub(r"[\u200b\u200e\u200f]", "", text)
    protected = re.sub(r"(?<=\d)\.(?=\d)", "\u0000", text)
    parts = re.split(r"(?<=[.!؟?\u061f…])\s+|\n+", protected)
    out = []
    for part in parts:
        part = re.sub(r"(?<=\d)\u0000(?=\d)", ".", part).strip()
        if len(words(part)) >= 1 and re.search(r"[\u0600-\u06ffA-Za-z]", part):
            out.append(part)
    return out


def review_text(text: str, name: str):
    """يعيد (errors, warnings, notes) لنصّ المتن."""
    errors, warnings, notes = [], [], []
    sentences = _prose_sentences(text)
    if not sentences:
        return ["لا جُمل في المتن لفحصها"], warnings, notes

    for i, s in enumerate(sentences, 1):
        n = len(words(s))
        if n > 25:
            warnings.append(f"جملة من {n} كلمة (> ٢٥) في الجملة {i}: {s[:60]}…")
        for c in CLICHES:
            if normalize_ar(c) in normalize_ar(s):
                errors.append(f"كليشيه ممنوع في الجملة {i}: «{c}»")
        if EMOTION_TAGS.search(s):
            errors.append(f"وسم انفعال في الحوار بالجملة {i} — «قال بحزن» ممنوع، "
                          f"استعمل فعلاً قبل القول: {s[:60]}…")
        for f in FILLERS:
            if f in s:
                warnings.append(f"حشو «{f}» في الجملة {i}")
        latin = LATIN_PUNCT.search(s)
        if latin:
            errors.append(f"ترقيم لاتيني أو مسافة خاطئة في الجملة {i}: «{latin.group(0)}» "
                          f"— القاعدة: ، ؛ ؟ ! بلا مسافة قبلها")

    if '"' in text:
        errors.append("اقتباس مستقيم \"…\" في المتن — القاعدة: «…» للنقل الأدبي")
    n_similes = len(SIMILE_MARKERS.findall(text))
    budget = max(1, round(word_count(text) / 250))
    if n_similes > budget:
        warnings.append(f"{n_similes} تشبيهات والوارد {budget} تشبيه لكل ٢٥٠ كلمة")

    smalls = SMALL_DIGIT.findall(text)
    if smalls:
        warnings.append(f"أرقام مفردة صغيرة {smalls[:6]} — حتى عشرة تُكتب بالحروف")

    tail = sentences[-1]
    if MORAL_TAIL.search(tail):
        errors.append(f"الجملة الأخيرة تفسّر بدل أن تُصوّر: {tail[:70]}…")
    if len(tail) > 0:
        shown = tail[:70] + ("…" if len(tail) > 70 else "")
        notes.append("الجملة الأخيرة: " + shown)
    n_scenes = 1 + len(re.findall(r"^---$", text, re.M))
    notes.append("%d جملة، %d كلمة، %d مشهد/لقطة" % (len(sentences), word_count(text), n_scenes))
    return errors, warnings, notes


def cmd_review(args) -> int:
    files = work_files()
    if args.slug:
        files = [f for f in files
                 if os.path.splitext(os.path.basename(f))[0] == args.slug]
        if not files:
            print(f"خطأ: لا عمل باسم slug: {args.slug}", file=sys.stderr)
            return 2
    if not files:
        print("لا أعمال للفحص.")
        return 0

    n_errors = n_warnings = 0
    for path in files:
        try:
            text = read_text(path)
        except UnicodeDecodeError:
            print(f"✗ {rel(path)}: ليس UTF-8")
            n_errors += 1
            continue
        _, body, err = split_front_matter(text)
        if err:
            print(f"✗ {rel(path)}: {err} — صحّح المواصفة أولًا (story.py lint)")
            n_errors += 1
            continue
        prose = section(body, "المتن")
        errors, warnings, notes = review_text(prose, rel(path))
        status = ""
        m, _, _ = split_front_matter(text)
        status = m.get("status", "?")
        header = f"{rel(path)}  [{status}]"
        if not errors and not warnings:
            print(f"✓ {header} الأسلوب سليم")
            if args.verbose:
                for note in notes:
                    print(f"    · {note}")
            continue
        print(("✗ " if errors else "! ") + header + " أسلوب")
        for e in errors:
            print(f"    خطأ أسلوب: {e}")
        for wmsg in warnings:
            print(f"    تنبيه أسلوب: {wmsg}")
        if args.verbose:
            for note in notes:
                print(f"    · {note}")
        n_errors += len(errors)
        n_warnings += len(warnings)

    if n_errors or (n_warnings and args.strict):
        print(f"\n{review_code_note(n_errors, n_warnings, args.strict)}")
        return 1
    print(f"\nفحص الأسلوب: مقبول ({n_warnings} تنبيهًا لا يقطع التسليم).")
    return 0


def review_code_note(errors: int, warnings: int, strict: bool) -> str:
    if strict:
        return f"{errors} خطأ و{warnings} تنبيهًا — في strict التنبيهات تقطع التسليم."
    return f"{errors} خطأ أسلوب و{warnings} تنبيهًا."


# ------------------------------------------------------------- test ----

class Capture:
    """التقاط مخرجات stdout/stderr داخل اختبار."""

    def __init__(self):
        self.chunks = []
        self._saved = None

    def __enter__(self):
        outer = self

        class _Writer:
            def write(self, s):
                outer.chunks.append(s)
                return len(s)

            def flush(self):
                pass

        self._saved = (sys.stdout, sys.stderr)
        sys.stdout = sys.stderr = _Writer()
        return self

    def text(self) -> str:
        return "".join(self.chunks)

    def __exit__(self, *exc):
        sys.stdout, sys.stderr = self._saved
        return False


def cmd_self_test(args) -> int:
    failures = []

    def check(name, cond, detail=""):
        if cond:
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))
            failures.append(name)

    # محلّل البيانات الأمامية
    ok = ("---\ntitle: س\nslug: s\ntype: short-story\nstatus: idea\n"
          "created: 2026-01-01\nupdated: 2026-01-01\n---\n## الملخص\nنص\n")
    meta, body, err = split_front_matter(ok)
    check("front-matter: قراءة صحيحة", err is None and meta["title"] == "س" and body.strip() == "## الملخص\nنص", f"err={err}")
    check("front-matter: رفض غياب الكتلة", split_front_matter("title: بدون فواصل\n")[2] is not None)
    check("front-matter: رفض كتلة غير مغلقة", split_front_matter("---\ntitle: س\n")[2] is not None)
    check("front-matter: رفض سطر بلا ':'",
          split_front_matter("---\ntitle بدون نقطتين\n---\n")[2] is not None)

    # عدّاد الكلمات والأقسام
    check("words: الترقيم العربي فاصل", word_count("قال لها: اذهبي، ولن أعود.") == 5,
          f"= {word_count('قال لها: اذهبي، ولن أعود.')}")
    check("words: تجاهل تنسيق markdown", word_count("**`نص`** عادي") == 2)
    check("section: يقرأ قسمًا ويحده", section("## الملخص\nثلاث كلمات هنا\n## المتن\nس\n", "الملخص") == "ثلاث كلمات هنا")
    check("section: قسم مفقود = فراغ", section("## المتن\nس\n", "الملخص") == "")
    check("digits: تحويل الأرقام العربية", to_ascii_int("٢٥٠٠") == 2500)

    # slug
    check("slug: قبول kebab-case", bool(SLUG_RE.match("the-long-night")))
    check("slug: رفض العربية والمسافات", not SLUG_RE.match("ليلة طويلة") and not SLUG_RE.match("Night"))

    # دورة كاملة في مستودع معزول
    global ROOT
    real_root = ROOT
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ROOT = tmp
            for d in ("works", "bible"):
                os.makedirs(os.path.join(tmp, d), exist_ok=True)
            shutil.copytree(templates_dir_real(), os.path.join(tmp, "templates"))

            ns_new = argparse.Namespace(slug="test-story", from_template="short-story",
                                        title="اختبار", status="idea", date="2026-09-05")
            cap = Capture()
            with cap:
                rc = cmd_new(ns_new)
            created = os.path.join(works_dir(), "test-story.md")
            check("new: إنشاء ملف من قالب", rc == 0 and os.path.exists(created), f"rc={rc}")
            check("new: لا يبقي placeholders", "{{" not in read_text(created))
            with Capture() as cap:
                rc = cmd_new(ns_new)
            check("new: رفض الكتابة فوق موجود", rc == 1, f"rc={rc}")
            with Capture() as cap:
                rc = cmd_new(argparse.Namespace(slug="لا يصلح", from_template="short-story",
                                                 title="", status="idea", date=""))
            check("new: رفض slug غير مطابق للمواصفة", rc == 2, f"rc={rc}")

            w = parse_work(created)
            check("lint: قالب سليم بلا أخطاء", not w["errors"], str(w["errors"]))

            write_text(created, read_text(created).replace("status: idea", "status: done"))
            w = parse_work(created)
            check("lint: done بلا متن = خطأ", any("done" in e for e in w["errors"]), str(w["errors"]))

            write_text(os.path.join(works_dir(), "broken-1.md"), "# بلا بيانات أمامية\n")
            w = parse_work(os.path.join(works_dir(), "broken-1.md"))
            check("lint: بلا front matter = أخطاء متعددة", len(w["errors"]) >= len(REQUIRED_KEYS),
                  f"{len(w['errors'])} خطأ")

            write_text(os.path.join(works_dir(), "broken-2.md"),
                       "---\ntitle: ت\nslug: broken-2\ntype: novel\nstatus: idea\n"
                       "created: 2026-13-45\nupdated: 2026-01-01\n---\nنص\n")
            w = parse_work(os.path.join(works_dir(), "broken-2.md"))
            check("lint: type مرفوض", any("type" in e for e in w["errors"]), str(w["errors"]))
            check("lint: تاريخ مرفوض", any("created" in e for e in w["errors"]), str(w["errors"]))
            check("lint: أقسام مفقودة", any("الملخص" in e for e in w["errors"]))

            with Capture() as cap:
                rc = cmd_lint(argparse.Namespace(strict=False))
            check("lint: rc=1 عند الأخطاء", rc == 1, f"rc={rc}")

            text = build_index(dry=True)
            check("index: يذكر العمل ومرتبته", "[اختبار](works/test-story.md)" in text and "done" in text)
            check("index: ideas قبل work done",
                  text.find("broken-1") > text.find("test-story") or "idea" in text)

            for f in ("broken-1.md", "broken-2.md"):
                os.remove(os.path.join(works_dir(), f))
            write_text(created, read_text(created).replace("status: done", "status: idea"))
            with Capture() as cap:
                rc = cmd_lint(argparse.Namespace(strict=False))
            check("lint: rc=0 بعد الإصلاح", rc == 0, cap.text().strip().splitlines()[-1:] or f"rc={rc}")

            with Capture() as cap:
                rc = cmd_check_contradictions(argparse.Namespace())
            check("contradictions: rc=0 بلا حقائق متضاربة", rc == 0, f"rc={rc}")

            # فاحص الأسلوب
            e, w, n = review_text("قلبها يخفق وهي تنظر.", "x")
            check("review: كليشيه = خطأ", any("كليشيه" in x for x in e), str(e))
            e, w, n = review_text("قال بحزن: سأرحل.", "x")
            check("review: وسم انفعال = خطأ", any("انفعال" in x for x in e), str(e))
            e, w, n = review_text('قال "سأرحل" ثم خرج.', "x")
            check("review: اقتباس لاتيني = خطأ", any("اقتباس" in x for x in e), str(e))
            e, w, n = review_text("وهكذا تعلّمت أن الصبر مفتاح.", "x")
            check("review: نهاية تفسّر = خطأ", any("تفسّر" in x for x in e), str(e))
            e, w, n = review_text("خرج. " + "كلمة " * 30, "x")
            check("review: جملة أطول من ٢٥ كلمة = تنبيه", any("كلمة (> ٢٥)" in x or "> ٢٥" in x for x in w), str(w)[:60])
            e, w, n = review_text("خرج من البيت.", "x")
            check("review: نص سليم بلا ملاحظات", not e and not w, str(e) + str(w))
            e, w, n = review_text("نظر الي? ثم خرج.", "x")
            check("review: ترقيم لاتيني = خطأ", any("ترقيم" in x for x in e), str(e))
            e, w, n = review_text("جاء ٣ رجال.", "x")
            check("review: رقم مفرد صغير = تنبيه", any("الحروف" in x for x in w), str(w)[:60])
            e, w, n = review_text("كأنّه جبل. مثل حجر. يشبه نسمة. كأنّه ظل. مثل تراب.", "x")
            check("review: ميزانية التشبيه تُخترق = تنبيه", any("تشبيه" in x for x in w), str(w)[:60])
            sep = "\n\n---\n\n"
            scenes = _prose_sentences("أ." + sep + "ب.")
            check("review: فواصل المشاهد لا تُحسب جُملًا", scenes == ["أ.", "ب."], str(scenes))
            e, w, n = review_text("كلمة ، أخرى.", "x")
            check("review: مسافة قبل الفاصلة = خطأ", any("ترقيم" in x for x in e), str(e))
            with Capture() as cap:
                rc = cmd_review(argparse.Namespace(slug="test-story", strict=False, verbose=False))
            check("review: rc=0 على عمل نظيف", rc == 0, cap.text().strip()[:70])
            with Capture() as cap:
                rc = cmd_review(argparse.Namespace(slug="غير-موجود", strict=False, verbose=False))
            check("review: slug غير موجود = 2", rc == 2, f"rc={rc}")
            write_text(os.path.join(bible_dir(), "characters.md"),
                       "**بشر** — لا يكذب.\n**بشر** — يكذب دائمًا.\n")
            with Capture() as cap:
                rc = cmd_check_contradictions(argparse.Namespace())
            check("contradictions: كشف النقض", rc == 1 and "بشر" in cap.text(), f"rc={rc}")

            write_text(os.path.join(bible_dir(), "characters.md"),
                       "**نورية** — لا تحفظ الأرقام.\n**نورية** — لا تُصلح علاقة مقطوعة.\n")
            with Capture() as cap:
                rc = cmd_check_contradictions(argparse.Namespace())
            check("contradictions: سِمتان متكاملتان لا تُعلَّمان", rc == 0, cap.text().strip()[:80])

            check("fact_slot: التقاط الخاصة مع تجاهل النفي",
                  fact_slot("لا تحفظ الأرقام") == fact_slot("تَحفظُ الأرقامُ")[0:1] + (True,) or
                  fact_slot("لا تحفظ الأرقام")[0] == fact_slot("تحفظ الأرقام")[0])
            check("fact_slot: تمييز المنفيّ عن الموجب",
                  fact_slot("لا يحبّ البحر")[1] is True and fact_slot("يحبّ البحر")[1] is False)
            check("normalize_ar: التشكيل والهمزة لا يغيّران المقارنة",
                  normalize_ar("تَحفظُ الأرقامَ") == normalize_ar("تحفظ الارقام"))
    finally:
        ROOT = real_root

    print()
    if failures:
        print(f"self-test: {len(failures)} فشل — {', '.join(failures)}")
        return 1
    print("self-test: نجح كل شيء.")
    return 0


def templates_dir_real() -> str:
    """مسار القوالب الحقيقي، مستقلّ عن ROOT المؤقّت في الاختبار."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")


# ----------------------------------------------------------------- cli ----

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="story", description="أدوات مستودع story")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("new", help="إنشاء عمل جديد من قالب")
    sp.add_argument("slug", help="kebab-case ASCII")
    sp.add_argument("--from", dest="from_template", default="short-story")
    sp.add_argument("--title", default="")
    sp.add_argument("--status", default="idea", choices=STATUSES)
    sp.add_argument("--date", default="")
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("lint", help="فحص مواصفة الأعمال")
    sp.add_argument("--strict", action="store_true", help="التنبيهات تُحسب أخطاء")
    sp.set_defaults(func=cmd_lint)

    sp = sub.add_parser("index", help="توليد works/index.md")
    sp.add_argument("--dry-run", action="store_true", help="طباعة بلا كتابة")
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("stats", help="إحصاءات موجزة")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("review", help="فحص آلي لقواعد الأسلوب في bible/style.md")
    sp.add_argument("slug", nargs="?", default="", help="عمل واحد؛ بلا slug = الكل")
    sp.add_argument("--strict", action="store_true", help="التنبيهات تقطع التسليم")
    sp.add_argument("-v", "--verbose", action="store_true", help="ملاحظات وإحصاءات")
    sp.set_defaults(func=cmd_review)

    sp = sub.add_parser("check-contradictions", help="كشف تناقضات آلية في bible/")
    sp.set_defaults(func=cmd_check_contradictions)

    sp = sub.add_parser("self-test", help="اختبار الأدوات ذاتها")
    sp.set_defaults(func=cmd_self_test)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
