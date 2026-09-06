"""فحوصُ الالتزام بالمستودع — ثلاث بوابات تُضاف إلى واجهة `story.py`:

* `sweep`        تلوّث الحروف: CJK/عبرية/تailandية في نصّ عربي، لاتينيٌّ في المتن،
                 تحكّماتِ اتجاهٍ خفيّة، أقواسٌ غير مطابقة.
* `debts`        دفتر الدُّيون السردية: من `bible/plot.md` ومن `## ملاحظات` كل عمل.
* `constraints`  عقد العالم: ما لا يوجد، القيودُ المُعجميّة، والفصول.

الفحص هنا لا يخترع قواعد: يقرأ `bible/world.md` و`bible/plot.md` كما هي، ويصرخ
إن أُضيف قيدٌ بلا معجم. المصدرُ هو bible/، وهذا الملف ترجمتهُ الآليّة فقط.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# ────────────────────────────── sweep: التلوّث ──────────────────────────────

FOREIGN_SCRIPTS = (
    ("CJK", re.compile("[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")),
    ("عبرية", re.compile("[\u0590-\u05ff]")),
    ("تايلندية", re.compile("[\u0e00-\u0e7f]")),
    ("هانغول", re.compile("[\uac00-\ud7af]")),
    ("ديوناغارية", re.compile("[\u0900-\u097f]")),
    ("حروفُ تحكّمٍ مرئيّة", re.compile("[\u202a-\u202e\u2066-\u2069]")),
)
BIDI_CTRL = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9_.+/:-]{1,}")
ARABIC = re.compile(r"[\u0600-\u06ff]")
# مختلط: «سat» أو «book» داخل كلمة عربية — لا يُقرأ ولا يُطبع
MIXED_TOKEN = re.compile(r"[\u0621-\u064A][A-Za-z]|[A-Za-z][\u0621-\u064A]")
BACKTICK = re.compile(r"`[^`]*`")

ALLOWED_PROSE_LATIN = {
    # أسماء الملفات والأوامر تُكتب كما هي؛ لا تُعَدّ تلوّثًا
    "AGENTS.md", "README.md", "IMAGES.md", "TODO", "kebab-case", "UTF-8", "A4", "A5",
}


def repo_files(exts=(".md", ".py")):
    """كل ملفٍّ ملتقَط في git — فلا قائمةَ استثناءٍ تُنسى. بلا git: مسحٌ للشجرة."""
    try:
        raw = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True,
                             timeout=20).stdout
        paths = [p for p in raw.decode("utf-8", "replace").split("\0") if p]
        if paths:
            return [p for p in paths if p.endswith(exts)
                    and not p.startswith((".venv", "book/edition/art"))]
    except Exception:                                    # noqa: BLE001 — بلا git
        pass
    out = []
    for dirpath, dirnames, names in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".venv", "__pycache__")]
        for n in names:
            if n.endswith(exts):
                out.append(os.path.relpath(os.path.join(dirpath, n), REPO))
    return sorted(out)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def sweep_text(rel_path: str, text: str) -> tuple[list, list]:
    """أخطاءُ وتنبيهات لملفٍّ واحد. المتن أشدّ قواعدَ من سواه."""
    errs: list = []
    warns: list = []
    is_work = rel_path.startswith("works/") and rel_path.endswith(".md")
    is_prose = is_work or rel_path.startswith(("bible/", "templates/"))
    body = text
    prose_zone = ""
    if is_work:
        m = re.search(r"^## المتن\s*$(.*?)^## ", text, re.S | re.M)
        prose_zone = m.group(1) if m else text[text.find("## المتن"):]
        body = text.replace(prose_zone, "\n" * prose_zone.count("\n"))  # لا تكرار

    for label, rx in FOREIGN_SCRIPTS:
        for mo in rx.finditer(text):
            ln = _line_of(text, mo.start())
            ctx = text[max(0, mo.start() - 14):mo.start() + 14].replace("\n", "⏎")
            errs.append(f"{rel_path}:{ln}: حرفٌ من {label} في نصٍّ عربي: …{ctx}…")
    if len(warns) < 8:
        for mo in BIDI_CTRL.finditer(text):
            ln = _line_of(text, mo.start())
            warns.append(f"{rel_path}:{ln}: تحكّمُ اتجاهٍ خفيّ (U+{ord(mo.group(0)):04X}) "
                         "يُفسد المطابقة والنسخ؛ شطبه: sweep --strip-controls")
    if rel_path.endswith(".md"):
        plain = BACKTICK.sub(lambda m: " " * len(m.group(0)), text)
        for mo in MIXED_TOKEN.finditer(plain):
            tok = re.match(r"\S+", plain[mo.start():])
            tok = tok.group(0) if tok else ""
            tok = tok.strip('«»“”()[]،؛.:;-' + chr(39) + chr(34))
            if "/" in tok or "." in tok or "-" in tok:
                continue          # اسمُ ملفٍّ أو مسارٌ ملتصقٌ بجرٍّ: مقصود
            ln = _line_of(text, mo.start())
            errs.append(f"{rel_path}:{ln}: كلمةٌ تمزج العربيّة باللاتينيّة: «{tok[:24]}» "
                        "— أطِّقها بوسوم `…` أو اكتبها عربيّة")

    if prose_zone:
        stripped = BACKTICK.sub(lambda m: " " * len(m.group(0)), prose_zone)
        for mo in LATIN_RUN.finditer(stripped):
            ln = _line_of(text, text.find(prose_zone) + mo.start() if prose_zone in text
                          else mo.start())
            errs.append(f"{rel_path}:{ln}: لاتينيّةٌ في المتن («{mo.group(0)}») — المتن "
                        "عربيٌّ خالص، والأسماء التقنية لا تدخل الحكاية")
    elif is_prose:
        body = re.sub(r"\A---\n.*?\n---\n", lambda m: "\n" * m.group(0).count("\n"),
                      body, flags=re.S)
        stripped = BACKTICK.sub(lambda m: " " * len(m.group(0)), body)
        for mo in LATIN_RUN.finditer(stripped):
            if mo.group(0) in ALLOWED_PROSE_LATIN or "." in mo.group(0) or "/" in mo.group(0):
                continue
            ln = _line_of(body, mo.start())
            warns.append(f"{rel_path}:{ln}: لاتينيّةٌ في نثرٍ عربي بلا وسوم: «{mo.group(0)}»")

    if is_prose:
        if text.count("«") != text.count("»"):
            warns.append(f"{rel_path}: عددُ « ({text.count('«')}) لا يساوي » "
                         f"({text.count('»')}) — اقتباسٌ غير مطابقة")
    return errs, warns


def strip_controls(text: str) -> tuple[str, int]:
    """شطبُ تحكّمات الاتجاه وBOM. العددُ من BIDI_CTRL وحدَه (تُضمّ BOM فيه)."""
    return BIDI_CTRL.sub("", text), len(BIDI_CTRL.findall(text))


def cmd_sweep(args) -> int:
    files = repo_files()
    all_errs: list = []
    all_warns: list = []
    touched = 0
    for relp in files:
        path = os.path.join(REPO, relp)
        try:
            text = open(path, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError) as exc:
            all_errs.append(f"{relp}: تعذّرت القراءة ({exc.__class__.__name__})")
            continue
        if getattr(args, "strip_controls", False):
            new, n = strip_controls(text)
            if n and new != text:
                open(path, "w", encoding="utf-8").write(new)
                touched += 1
                all_warns.append(f"{relp}: مُحي {n} تحكّمًا خفيًّا")
                text = new
        e, w = sweep_text(relp, text)
        all_errs += e
        all_warns += w
    if getattr(args, "json", False):
        print(json.dumps({"files": len(files), "errors": all_errs,
                          "warnings": all_warns, "stripped_files": touched},
                         ensure_ascii=False, indent=2))
    else:
        for e in all_errs:
            print(f"✗ {e}")
        for w in all_warns:
            print(f"! {w}")
        head = f"سُحِب {len(files)} ملفًّا: "
        if all_errs:
            print(head + f"{len(all_errs)} خطأً، {len(all_warns)} تنبيهًا")
        else:
            print(head + f"لا تلوّث ({len(all_warns)} تنبيهًا)")
        if touched:
            print(f"نُظّفت {touched} ملفًّا من التحكّمات الخفيّة.")
    return 1 if all_errs else 0


# ────────────────────────────── debts: الدُّيون ──────────────────────────────

DEBT_MARK = re.compile(r"دَين|دين|ما لم يُحسم|لم يُحسم|مفتوح")
DEBT_ANSWER = re.compile(r"يُجاب|جوابه|→|في عمل|العقد|لاحقًا|لاحقة")
DEBT_CLOSED = re.compile(r"مغلق|أُغلِق|مُغلَق|سُقِط|دُفِع")
DEBT_TRAIT = re.compile(r"لا يُجاب|عمدًا|عمداً|سِمة|صفة")


def _debt_state(line: str) -> str:
    # الترتيبُ مقصود: «يبقى مغلقًا هنا عمدًا» سِمةٌ مُعلَنة لا دَينٌ قُطِع
    if DEBT_TRAIT.search(line):
        return "سِمة"
    if DEBT_CLOSED.search(line):
        return "مغلق"
    if DEBT_ANSWER.search(line):
        return "مُحال"
    return "مفتوح"


def _pulled_by(line: str) -> str:
    m = re.search(r"(?:يُجاب|جوابه)\s*(?:في)?\s*([^؛.\n]+)", line)
    if m:
        return m.group(1).strip()[:40]
    m = re.search(r"→\s*([^؛.\n]+)", line)
    return m.group(1).strip()[:40] if m else "—"


def debt_entries() -> list[dict]:
    """من «## الدَّين المفتوح» في plot.md، ومن «## ملاحظات» كلِّ عمل."""
    out: list = []
    plot = os.path.join(REPO, "bible", "plot.md")
    if os.path.exists(plot):
        txt = open(plot, encoding="utf-8").read()
        m = re.search(r"^##[^\n]*د[^\n]*ين[^\n]*\n(.*?)(?=^## |\Z)", txt, re.S | re.M)
        if m:
            for line in m.group(1).splitlines():
                s = line.strip()
                if s.startswith(("-", "*", "|")) and len(s) > 6:
                    s = s.lstrip("-*| ").strip()
                    out.append({"مصدر": "bible/plot.md", "دَين": s[:120],
                                "الحالة": _debt_state(s), "يُجاب": _pulled_by(s)})
    wdir = os.path.join(REPO, "works")
    if os.path.isdir(wdir):
        for fn in sorted(os.listdir(wdir)):
            if not fn.endswith(".md") or fn == "index.md":
                continue
            txt = open(os.path.join(wdir, fn), encoding="utf-8").read()
            m = re.search(r"^## ملاحظات[ \t]*\n(.*?)(?=^## |\Z)", txt, re.S | re.M)
            if not m:
                continue
            status = ""
            sm = re.search(r"^status:\s*(\S+)", txt, re.M)
            if sm:
                status = sm.group(1)
            for line in m.group(1).splitlines():
                s = line.strip().lstrip("-* ").strip()
                if len(s) < 8 or not DEBT_MARK.search(s):
                    continue
                out.append({"مصدر": f"works/{fn}", "دَين": s[:120],
                            "الحالة": _debt_state(s), "يُجاب": _pulled_by(s),
                            "status": status})
    return out


def cmd_debts(args) -> int:
    ents = debt_entries()
    if getattr(args, "json", False):
        print(json.dumps(ents, ensure_ascii=False, indent=2))
        return 0
    if not ents:
        print("لا دُيون مسجَّلة. السِجلّ: «## الدَّين المفتوح» في bible/plot.md و«## ملاحظات» كل عمل.")
        return 0
    print("| المصدر | الدَّين | الحالة | يُجاب |")
    print("|---|---|---|---|")
    for e in ents:
        print(f"| {e['مصدر']} | {e['دَين'][:70]} | {e['الحالة']} | {e['يُجاب']} |")
    open_n = sum(1 for e in ents if e["الحالة"] == "مفتوح")
    done_open = [e for e in ents if e.get("status") == "done" and e["الحالة"] == "مفتوح"]
    print(f"\nالإجمالي {len(ents)} · مفتوح {open_n} · "
          f"مُحال {sum(1 for e in ents if e['الحالة'] == 'مُحال')} · "
          f"سِمة {sum(1 for e in ents if e['الحالة'] == 'سِمة')} · "
          f"مغلق {sum(1 for e in ents if e['الحالة'] == 'مغلق')}")
    if done_open and getattr(args, "gate", False):
        for e in done_open:
            print(f"✗ {e['مصدر']}: دَينٌ مفتوح في عملٍ بحالة done — "
                  "إما أن يُغلَق أو يُحال صراحةً (نصّ فيه «يُجاب في…» أو «عمدًا»)")
        return 1
    if done_open:
        print("! دَينٌ مفتوح في عملٍ بحالة done (لا يقطع التسليم بلا --gate):")
        for e in done_open:
            print(f"    · {e['دَين'][:80]}")
    return 0


# ──────────────────── constraints: عقد العالم مقروءًا ────────────────────

# معجمٌ لكل قيدٍ في bible/world.md. المصدرُ هو world.md؛ إن أُضيف قيدٌ هناك
# بلا سطرٍ هنا فالفحص يصرّح بذلك خطأً — فلا ينمو العالمُ سرًّا.
CONSTRAINT_LEXICON = {
    # كلُّ قيدٍ في bible/world.md يحتاج سطرًا هنا، وإلا صرّح الفحصُ خطأً.
    # الأنماطُ عباراتٌ لا حروفٌ مفردة: القيدُ يُخالَف بجملة، لا بحرف.
    "الكهرباء": r"التيار\s+(?:شاملٌ|لا\s+ينقطع)|أضواء\s+الشارع\s+(?:لا\s+تنقطع|مضاءة\s+فجرًا)",
    "الأرشيف": r"استعار(?:ة)?\s+(?:الدفتر|النسخة)|أعار(?:ه)?\s+(?:الدفتر|النسخة)|"
               r"خرج\s+(?:بالدفتر|بالنسخة)|طابعة|ناسوخ|تصوير\s+ضوئي|مسح\s+ضوئي|سكانر|"
               r"صوَّر\s+(?:الصفحة|النسخة)|صوِّرَت\s+(?:الصفحة|النسخة)|كاميرا",
    "النهر": r"النهر\s+(?:يجري|جارف|فاض|امتلأ)\s+(?:في\s+)?(?:الصيف|تمّوز|آب)",
    "القطار": r"قطار\s+(?:الضحى|الصباح|الثاني|التالي|الآتي)|رحلتان\s+في\s+الليلة|"
              r"أوقفوا\s+القطار|يوقف\s+القطار",
}
BAN_SYNONYMS = {
    "هواتف": r"هاتف|هواتف|جوال|موبايل|نقال|رسالة\s+قصيرة|SMS",
    "إنترنت": r"إنترنت|انترنت|شبكة\s+عنكبوت|تحميل|أونلاين",
    "سلاح": r"سلاح|مسدس|بندقي|رصاص|طلقة|عيار\s+ناري",
    "سفر": r"طائرة|مطار|رحلة\s+جوّية|تذكرة\s+طيران",
}
NEGATION = re.compile(r"(?:لا|بلا|بدون|لم\s+يكن|لم\s+تكن|لا\s+يوجد|بدون\s+أثر|"
                      r"لم\s+تُوجد|لا\s+أثرَ?\s+ل)")
SEASON_LEX = {"خريف": r"خريف|أيلول|تشرين", "صيف": r"صيف|تمّوز|آب|حرّ",
              "شتاء": r"شتاء|كانون|برد|ثلج"}


def _strip_marks(s: str) -> str:
    return re.sub(r"[*_`]", "", s).strip()


def parse_world(path: str | None = None) -> dict:
    txt = open(path or os.path.join(REPO, "bible", "world.md"), encoding="utf-8").read()
    world = {"bans": [], "constraints": [], "seasons": {}}
    m = re.search(r"^## ما لا يوجد[^\n]*\n(.+?)(?=^## |\Z)", txt, re.S | re.M)
    if m:
        chunk = m.group(1)
        for item in re.split(r"[،،]\s*(?=لا\s)|\n+", chunk):
            item = _strip_marks(item).strip()
            if item.startswith("لا ") and len(item) > 4:
                head = re.match(r"لا\s+([\u0600-\u06ff]+)", item)
                if head:
                    key = head.group(1)
                    stem = key[:4] if len(key) > 4 else key
                    pat = BAN_SYNONYMS.get(key) or BAN_SYNONYMS.get(stem) or \
                        re.escape(stem)
                    world["bans"].append({"من": item, "معجم": pat})
    m = re.search(r"^## قواعد[^\n]*\n(.*?)(?=^## |\Z)", txt, re.S | re.M)
    if m:
        for line in m.group(1).splitlines():
            s = _strip_marks(line.strip())
            mm = re.match(r"^-\s*«?([^—\u2014-]{2,28}?)\s*[—\u2014-]\s*(.+)$", s)
            if mm:
                world["constraints"].append({"موضوع": mm.group(1).strip(),
                                             "قيد": mm.group(2).strip()})
    m = re.search(r"^## الطقس[^\n]*\n(.*?)(?=^## |\Z)", txt, re.S | re.M)
    if m:
        for line in m.group(1).splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] in SEASON_LEX:
                world["seasons"][cells[0]] = cells[1]
    return world


def check_prose(prose: str, world: dict) -> tuple[list, list]:
    errs: list = []
    warns: list = []
    if not prose.strip():
        return errs, warns

    def hits(pat: str):
        for mo in re.finditer(pat, prose):
            ctx = prose[max(0, mo.start() - 22):mo.end() + 22].replace("\n", " ")
            if NEGATION.search(prose[max(0, mo.start() - 16):mo.end() + 8]):
                continue          # النصُّ يُعلن الغياب، لا يُخالف
            yield mo.group(0), ctx

    for ban in world["bans"]:
        for tok, ctx in hits(ban["معجم"]):
            errs.append(f"يخالف «{ban['من']}»: …{ctx}…")

    known = set(CONSTRAINT_LEXICON)
    subjects = {c["موضوع"].replace("ال", "", 1) for c in world["constraints"]}
    for c in world["constraints"]:
        key = c["موضوع"]
        entry = CONSTRAINT_LEXICON.get(key)
        if entry is None:            # «الأرشيف البلدي» يُقبل تحت مفتاح «الأرشيف»
            for k in CONSTRAINT_LEXICON:
                if k in key or (len(k) > 3 and k[2:] in key):
                    entry = CONSTRAINT_LEXICON[k]
                    break
        if entry is None:
            errs.append(f"قيدٌ في bible/world.md بلا معجم فحص: {key} — "
                        f"أضِف سطرًا إلى CONSTRAINT_LEXICON (الموجود: {', '.join(sorted(known))})")
            continue
        pat = entry
        for tok, ctx in hits(pat):
            warns.append(f"يُحتمل مخالفَةُ «{key}: {c['قيد'][:40]}» — "
                         f"راجعَ يدويًّا: …{ctx}…")

    seasons = [s for s in SEASON_LEX if re.search(SEASON_LEX[s], prose)]
    if "صيف" in seasons and re.search(r"غرق|يغرق", prose) and \
            not NEGATION.search(prose[max(0, prose.find("غرق") - 20):prose.find("غرق") + 10]):
        errs.append("مشهدُ غرقٍ في الصيف والنهرُ جافّ — القيدُ في bible/world.md")
    if "خريف" in seasons and re.search(r"مطر", prose) and "شتاء" not in seasons:
        warns.append("مطرٌ في الخريف: نادرٌ ومُعلَن — أعلنْه في أول المشهد أو انقله إلى الشتاء")
    return errs, warns


def cmd_constraints(args) -> int:
    world = parse_world()
    if getattr(args, "json", False):
        print(json.dumps(world, ensure_ascii=False, indent=2))
        return 0
    print(f"قراءة bible/world.md: {len(world['bans'])} منعًا · "
          f"{len(world['constraints'])} قيدًا · {len(world['seasons'])} فصلًا مُعجمًا")
    wdir = os.path.join(REPO, "works")
    files = sorted(f for f in os.listdir(wdir) if f.endswith(".md") and f != "index.md")
    if getattr(args, "slug", ""):
        files = [f for f in files if f[:-3] == args.slug]
        if not files:
            print(f"خطأ: لا عمل باسم slug: {args.slug}", file=sys.stderr)
            return 2
    n_err = n_warn = 0
    for fn in files:
        txt = open(os.path.join(wdir, fn), encoding="utf-8").read()
        m = re.search(r"^## المتن[ \t]*\n(.*?)(?=^## |\Z)", txt, re.S | re.M)
        prose = m.group(1) if m else ""
        errs, warns = check_prose(prose, world)
        n_err += len(errs)
        n_warn += len(warns)
        if not errs and not warns:
            print(f"✓ works/{fn} — لا مخالفة")
            continue
        print(f"{'✗' if errs else '!'} works/{fn}")
        for e in errs:
            print(f"    خطأ: {e}")
        for w in warns:
            print(f"    تنبيه: {w}")
    if n_err:
        print(f"\nالعقد: {n_err} مخالفة · {n_warn} تنبيهًا — القيودُ مُلزمة، فلا done مع مخالفة.")
        return 1
    print(f"\nالعقد: لا مخالفة ({n_warn} تنبيهًا لا يقطع).")
    return 0


# ─────────────────────────── اختبارٌ ذاتيّ مُصغَّر ───────────────────────────

def self_test(check) -> None:
    """فحوصٌ تُنفَّذ داخل أدوات/story.py self-test (تأخذ دالّة check)."""
    w = parse_world()
    fixture = "مرحبا \u7535\u7f51 عالمًا"      # لا CJK في هذا المصدر إلّا هربًا
    check("sweep: CJK في سطرٍ عربيٍّ خطأٌ لا تنبيه",
          any("CJK" in e for e in sweep_text("works/x.md", fixture)[0]))
    check("sweep: لاتينيّةٌ في المتن خطأ",
          any("لاتينيّةٌ في المتن" in e
              for e in sweep_text("works/x.md", "## المتن\n\nقال نورية OK ثم مضت\n")[0]))
    check("sweep: لاتينيّةٌ مُطهّقةٌ بين وسومٍ ليست خطأ",
          not any("المتن" in e for e in sweep_text("works/x.md", "## المتن\n\nلا `dpi` هنا\n")[0]))
    e, wn = sweep_text("AGENTS.md", "كلمة\u200fمكتوبةٌ بلا\n")
    check("sweep: تحكّمُ اتجاهٍ خفيّ يُنبَّه له", any("تحكّمُ اتجاه" in x for x in wn))
    check("sweep: اقتباسٌ غير مطابق يُنبَّه له",
          any("»" in x for x in sweep_text("bible/style.md", "قال «نعم ثم مضى")[1]))
    clean, _ = sweep_text("works/ok.md", "## المتن\n\nلا يوجد هاتفٌ يعمل في المدينة.\n")
    check("sweep: لا صرخةَ في نصٍّ نظيف", not clean)
    t, n = strip_controls("مرحبا\u200f عالمًا\ufeff")
    check("sweep: الشطب يعيد نصًّا بلا تحكّمات", n == 2 and "\u200f" not in t and "\ufeff" not in t)

    check("constraints: معجمُ القيدِ معروفٌ لكلّ قيدٍ في bible/",
          not any("بلا معجم" in e for e in check_prose("نسخةٌ في الدفتر.", w)[0]),
          str(check_prose("", w)[0][:1]))
    e, wn = check_prose("خرج بالنسخة من الأرشيف.", w)
    check("constraints: استعارةُ الأرشيف تُلتقَط", any("الأرشيف" in x for x in wn))
    e, wn = check_prose("لا أثرَ لهاتفٍ في جيبه.", w)
    check("constraints: النفيُ ليس مخالفة", not e)
    e, wn = check_prose("كان الهاتف في جيبه يرنّ.", w)
    check("constraints: الهاتفُ المخالف خطأ", any("يخالف" in x for x in e))
    e, wn = check_prose("غرق الطفل في النهر صيفًا، والمطر في الخريف.", w)
    check("constraints: غرقٌ صيفيّ خطأٌ ومطرُ خريفٍ تنبيه",
          any("غرق" in x for x in e) and any("خريف" in x for x in wn))

    check("debts: مفتوحٌ بلا إحالة", _debt_state("من مسح الشريط؟") == "مفتوح")
    check("debts: «يُجاب في» إحالة", _debt_state("هل تُثبت؟ جوابه في العقد الأخير") == "مُحال")
    check("debts: «عمدًا» سِمةٌ لا دَين", _debt_state("يبقى مغلقًا هنا عمدًا") == "سِمة")
    check("debts: مُغلَق", _debt_state("الدَّين مغلق في الركن ٤") == "مغلق")
    ents = debt_entries()
    check("debts: السِجلّ يقرأ plot.md وworks/", len(ents) >= 3
          and any(e["مصدر"].endswith("plot.md") for e in ents)
          and any(e["مصدر"].startswith("works/") for e in ents))
    check("debts/constraints: لا قيدٌ في bible/ بلا معجم",
          not any("بلا معجم" in e for e in
                  check_prose("ذكرتُ القطار والنهر والكهرباء والأرشيف.", parse_world())[0]))
    check("sweep: مصدرُ الفحص لا يُلعَن عليه بنفسه",
          not any("CJK" in e for e in sweep_text("tools/contract.py",
                "نصٌّ عربيٌّ سليم")[0]))
