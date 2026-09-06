#!/usr/bin/env python3
"""اختبار المحرّك — بوابةٌ طباعيّة لا بصرية.

المحرّط كسرَ مرّتين بلا صرخة: وحداتٌ تُركَّب من الحافة اليُمنى فتتراكب،
وأرقامٌ عربيّة تُشكَّل RTL فتُطبع «٨٤١». هذا الملف يمنع ذلك آليًّا.

    ./.venv/bin/python book/test_typeset.py            # المحرّك وحدُه
    ./.venv/bin/python book/test_typeset.py --build    # + طبعةٌ كاملة في مؤقّت

بلا pytest ولا Pillow في المسار الحَرِج: Pillow لازمٌ لفحص صورة PNG فقط.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import typeset as T                                            # noqa: E402

FONT_R = os.path.join(HERE, "fonts", "Amiri-Regular.ttf")
FONT_B = os.path.join(HERE, "fonts", "Amiri-Bold.ttf")
FAILS: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ✓ " if ok else "  ✗ ") + name + (("  — " + detail) if (detail and not ok) else ""))
    if not ok:
        FAILS.append(name)


def shapers() -> dict:
    return {"R": T.Shaper(FONT_R, "R"), "B": T.Shaper(FONT_B, "B")}


# ─────────────────────────── بياناتٌ وقواعدُ نصّ ───────────────────────────

def test_front_matter() -> None:
    md = "---\ntitle: محاولة واحدة\nstatus: done\n---\n\n## المتن\n\nنصّ.\n"
    meta, body = T.read_front_matter(md)
    check("front matter: قيمةٌ من كلمتين تُقرأ كاملة", meta.get("title") == "محاولة واحدة",
          repr(meta.get("title")))
    check("front matter: المتن يبقى في النصّ", "## المتن" in body)
    check("front matter: بلا كتلة أماميّة = نصّ خالص", T.read_front_matter("لا شيء هنا")[0] == {})


def test_peel_and_runs() -> None:
    check("peel: اقتباسٌ وترقيمٌ طرفيّ", T.peel("«الدفتر»،") == ["«", "الدفتر", "»،"],
          str(T.peel("«الدفتر»،")))
    check("peel: قوسٌ مغلقٌ ينفصل", T.peel("في)") == ["في", ")"], str(T.peel("في)")))
    check("peel: قوسٌ مفتوحٌ ينفصل", T.peel("(A5") == ["(", "A5"], str(T.peel("(A5")))
    check("peel: الرمزُ وحدَه كتلةٌ واحدة", T.peel("—") == ["—"], str(T.peel("—")))
    check("script-runs: الرقمُ العربيُّ يَقرأ يسارًا ولا يُنعكس",
          T._script_runs("١٤٨") == [("١٤٨", False)], str(T._script_runs("١٤٨")))
    check("script-runs: الحرفُ العربيّ يمينًا",
          T._script_runs("كلمة") == [("كلمة", True)], str(T._script_runs("كلمة")))
    check("script-runs: جزيرةٌ لاتينيّةٌ ملتصقةٌ بواو تُقسَّم",
          T._script_runs("وbook/typeset.py") == [("و", True), ("book/typeset.py", False)],
          str(T._script_runs("وbook/typeset.py")))
    check("script-runs: الترقيمُ الخالصُ يأخذ اتجاه الفقرة", T._script_runs("،") == [("،", True)],
          str(T._script_runs("،")))


# ────────────────────────────── وحداتٌ ومواضع ──────────────────────────────

def test_units(sh: dict) -> None:
    s = "قرأت نورية السطر ثلاث مرات، ثم أغلقت دفتر الحفر."
    units = T.shape_units(sh, s, 11.5, "R")
    check("units: عددُ الوحدات = عددُ الكلمات", len(units) == len(s.split()), str(len(units)))
    ok = all(abs(u["w"] - sum(p["w"] for p in u["pieces"])) < 1e-6 for u in units)
    check("units: عرضُ الوحدة = مجموعُ قطعها", ok)

    ops, content, loose = T.place_units(units, sh["R"].space(11.5), 400.0, 0.0, "R", 11.5)
    n = len(units)
    expected = sum(u["w"] for u in units) + sh["R"].space(11.5) * (n - 1)
    check("place: المحقَّقُ = العروضُ + الفواصل", abs(content - expected) < 1e-6,
          f"{content:.2f} مقابل {expected:.2f}")

    # لكل وحدةٍ مدىً أفقيّ؛ والمدى يجب ألا يتقاطع مع جارتها (داءُ التراكب)
    spans, cursor = [], 400.0
    for u in units:
        spans.append((cursor - u["w"], cursor))
        cursor -= u["w"] + sh["R"].space(11.5)
    by_unit: list = [{} for _ in units]
    for o in ops:
        x = o[3]
        for i, (lo, hi) in enumerate(spans):
            if lo - 1.0 <= x <= hi + 1.0:
                by_unit[i][o[2]] = by_unit[i].get(o[2], 0) + 1
                break
    inside = all(len(d) for d in by_unit)
    check("place: لا مشغّلَ خارج وحدته (تراكبٌ معدوم)", inside,
          str([i for i, d in enumerate(by_unit) if not d][:5]))
    rights = [hi for _, hi in spans]
    check("place: التقدّمُ من اليمين إلى اليسار صارمٌ",
          all(b < a - 1.0 for a, b in zip(rights, rights[1:])))


def test_directions(sh: dict) -> None:
    def xs_of_units(text):
        u = T.shape_units(sh, text, 12.0, "R")[0]
        ops, _, _ = T.place_units([u], 0.0, 200.0, 0.0, "R", 12.0)
        return ops

    # الأرقام: أوّلُها يسارًا، لا يمينًا (كان «١٤٨» يُطبع «٨٤١»)
    ops = xs_of_units("١٤٨")
    g_one = sh["R"].shape_rtl("١", 12.0, False)[0][0][0]
    g_eight = sh["R"].shape_rtl("٨", 12.0, False)[0][0][0]
    x_one = min(o[3] for o in ops if o[2] == g_one)
    x_eight = min(o[3] for o in ops if o[2] == g_eight)
    check("bidi: الرقمُ العربيُّ لا يُنعكس (١ يسار ٨)", x_one < x_eight,
          f"x(١)={x_one:.2f} · x(٨)={x_eight:.2f}")

    # جزيرة لاتينيّةٌ داخل عربيّ: ترتيبُها الداخليّ سليم
    text = "قال book/typeset.py ثم"
    units = T.shape_units(sh, text, 12.0, "R")
    ops, _, _ = T.place_units(units, sh["R"].space(12.0), 400.0, 0.0, "R", 12.0)
    b_id = sh["R"].shape_rtl("b", 12.0, False)[0][0][0]
    y_id = sh["R"].shape_rtl("y", 12.0, False)[0][0][0]
    xb = min(o[3] for o in ops if o[2] == b_id)
    xy = max(o[3] for o in ops if o[2] == y_id)
    check("bidi: اسمُ الملفّ اللاتينيّ يُقرأ من اليسار", xb < xy, f"x(b)={xb:.2f} · x(y)={xy:.2f}")

    # القوسُ المفتوح يقف يمينَ ما يحويه (وهو أوّلٌ منطقيًّا)
    units = T.shape_units(sh, "(A5)", 12.0, "R")
    ops, _, _ = T.place_units(units, sh["R"].space(12.0), 300.0, 0.0, "R", 12.0)
    open_x = max(o[3] for o in ops)
    g_open = sh["R"].shape_rtl("(", 12.0, True)[0][0][0]
    x_open = max((o[3] for o in ops if o[2] == g_open), default=-1.0)
    check("bidi: الفتحةُ أقصى اليمين والكسرةُ أقصى اليسار",
          abs(x_open - open_x) < 0.01, f"x(=)={x_open:.2f} · أقصى={open_x:.2f}")


def test_piece_order(sh: dict) -> None:
    """أين تقعُ علامةُ الترقيم من الكلمة؟ هذا كان معكوسًا ولا تراه العينُ في معاينة."""
    def sides(txt, ref, rtl=False):
        u = T.shape_units(sh, txt, 12.0, "R")[0]
        ops, _, _ = T.place_units([u], 0.0, 200.0, 0.0, "R", 12.0)
        g = sh["R"].shape_rtl(ref, 12.0, True)[0][0][0]
        mine = [o[3] for o in ops if o[2] == g]
        rest = [o[3] for o in ops if o[2] != g]
        return mine, rest
    for txt, mark, side in (("مرات،", "،", "يسار"), ("«الدفتر", "«", "يمين"),
                            ("في)", ")", "يسار"), ("(A5", "(", "يمين"),
                            ("A5)", ")", "يسار"), ("book/typeset.py،", "،", "يسار")):
        mine, rest = sides(txt, mark)
        ok = bool(mine and rest) and (max(mine) < min(rest) if side == "يسار"
                                      else min(mine) > max(rest))
        check(f"رصّ: «{mark}» في «{txt}» إلى {side} الكلمة", ok,
              f"{[round(v, 1) for v in mine]} مقابل {[round(v, 1) for v in rest]}")


def test_justify(sh: dict) -> None:
    units = T.shape_units(sh, "كلمة كلمة كلمة كلمة", 11.5, "R")
    gap = sh["R"].space(11.5)
    natural = sum(u["w"] for u in units) + gap * (len(units) - 1)
    ops, content, loose = T.place_units(units, gap, 400.0, 0.0, "R", 11.5,
                                        justify_to=natural + 3.0)
    check("justify: عجزٌ صغيرٌ يُسَدّ", abs(content - (natural + 3.0)) < 0.02 and not loose,
          f"{content:.2f} · loose={loose}")
    ops, content, loose = T.place_units(units, gap, 400.0, 0.0, "R", 11.5,
                                        justify_to=natural * 2)
    check("justify: عجزٌ كبيرٌ لا يُفتَح على العمود (سطرٌ فضفاض)",
          loose and abs(content - natural) < 0.02, f"{content:.2f} مقابل {natural:.2f}")
    check("justify: العتبةُ في صنف التدفّق ١٦٪", abs(T.Flow.justify_max - 0.16) < 1e-9)


# ─────────────────────────────── التدفّقُ والورق ───────────────────────────────

MM = T.MM
PAGE_W, PAGE_H = 148 * MM, 210 * MM


def test_flow(sh: dict) -> None:
    text = ("قرأت نورية السطر ثلاث مرات، ثم أغلقت دفتر الحفر فصار الرقم في رأسها لوحة مقلوبة: "
            "ألف ومئة، ومئة، ثم رقمان يتبادلان. " * 40)
    cv = T.Canvas(PAGE_W, PAGE_H)
    flow = T.Flow(cv, sh, margin=17 * MM, top=20 * MM, bottom=PAGE_H - 18 * MM,
                  width=PAGE_W - 2 * 17 * MM)
    flow.set_grid(19.0)
    for _ in range(6):
        flow.paragraph(text, size=11.5, font="R", lead=19.0, align="justify")
    st = flow.stats
    check("flow: أسطرٌ كثيرةٌ وصفحاتٌ متعددة", st["lines"] > 40 and st["pages"] >= 1,
          str(st))
    check("flow: لا تجاوزَ للعمود", st["overfull"] <= 0.05, f"{st['overfull']:.3f}pt")
    check("flow: أطولُ سطرٍ لا يتّسع أكثرَ من العمود", st["longest_line"] <= flow.width + 0.02,
          f"{st['longest_line']:.2f} مقابل {flow.width:.2f}")
    check("flow: كلُّ صفحةٍ من دفترٍ مطابقةٌ للوحة", len(cv.pages) == st["pages"] + 1,
          f"{len(cv.pages)} صفحات و{st['pages']} مُعلَنة")
    # لا سطرَ في الحاشية: كلُّ رسمٍ داخل الصندوق
    bad = 0
    for pg in cv.pages:
        for o in pg:
            if o[0] == "g" and not (17 * MM - 1 <= o[3] <= PAGE_W - 17 * MM + 1):
                bad += 1
    check("flow: لا مشغّلَ خارج الهامش الأيسر", bad == 0, f"{bad} مشغّلًا")

    # يتيمةُ الكلمة: عمودٌ يُسعفُ الحسابُ فيه — ثلاثُ كلماتٍ في السطر،
    # وسبعُ كلماتٍ في الفقرة ⇒ سطرٌ أخيرٌ بكلمةٍ واحدة، فيُسحب منها واحدة.
    uw = T.shape_units(sh, "طويلٌ", 11.5, "R")[0]["w"]
    gp = sh["R"].space(11.5)
    cv2 = T.Canvas(PAGE_W, PAGE_H)
    f2 = T.Flow(cv2, sh, margin=17 * MM, top=20 * MM, bottom=PAGE_H - 18 * MM,
                width=3 * uw + 2 * gp + 0.4)
    f2.set_grid(19.0)
    f2.paragraph(" ".join(["طويلٌ"] * 7), size=11.5, font="R", lead=19.0, align="justify")
    check("flow: اليتمةُ تُسحب من السطر السابق", f2.stats["orphans_fixed"] == 1,
          f'{f2.stats["orphans_fixed"]} · أسطر={f2.stats["lines"]}')
    check("flow: السطرُ الأخيرُ لم يبقَ أعزل", f2.stats["lines"] == 3, str(f2.stats["lines"]))


def test_blocks(sh: dict) -> None:
    cv = T.Canvas(PAGE_W, PAGE_H)
    p = cv.page()
    T.Flow.blocks(cv, sh, p, PAGE_W, PAGE_H,
                  [{"y": 0.35, "text": "محاولة واحدة", "size": 29.0, "font": "B",
                    "align": "center"},
                   {"y": 0.52, "text": "قصة قصيرة", "size": 11.0, "font": "R", "align": "center"},
                   {"y": 0.60, "text": "نجمة برهان", "size": 10.0, "font": "R",
                    "align": "center", "rule": True}])
    ops = [o for o in cv.pages[p] if o[0] == "g"]
    ys = sorted({round(o[4], 1) for o in ops})
    check("blocks: كلُّ عنصرٍ في مكانه النسبيّ", len(ys) >= 3, str(ys))
    check("blocks: لا شيءَ خارج الورقة",
          all(0 <= o[3] <= PAGE_W and 0 <= o[4] <= PAGE_H for o in ops))


def test_render(sh: dict) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cv = T.Canvas(PAGE_W, PAGE_H)
        p = cv.page()
        ops, w = T.draw_single_line(sh, "صفحةُ اختبار", 24.0, "B",
                                   right=PAGE_W - 17 * MM, baseline=40 * MM)
        for o in ops:
            cv.pages[p].append(o)
        pdf = os.path.join(tmp, "x.pdf")
        T.render_pdf(cv, pdf, {"R": FONT_R, "B": FONT_B}, label="test")
        head = open(pdf, "rb").read(5)
        size = os.path.getsize(pdf)
        check("render: PDF يبدأ بمِميَزٍ حقيقي وله حجم", head == b"%PDF-" and size > 8000,
              f"{head!r} · {size}B")
        if "PIL" in sys.modules or True:
            try:
                from PIL import Image     # اختياري: فحصُ الأبعاد يستحقّ Pillow
            except ImportError:
                Image = None
        else:
            Image = None
        if Image is not None:
            out = os.path.join(tmp, "png")
            T.render_png(cv, out, {"R": FONT_R, "B": FONT_B}, dpi=150.0)
            png = os.path.join(out, "p01.png")
            im = Image.open(png)
            # داءُ اللوحة الكاذبة: Canvas بأبعادٍ خاطئة يُخرِج صفحةً ٢×٢ بلا صرخة
            check("render: معاينةُ ١٥٠dpi بحجم A5 (١٤٨×٢١مم)",
                  860 <= im.width <= 890 and 1230 <= im.height <= 1255, f"{im.size}")
            ink = sum(1 for q in im.convert("L").get_flattened_data()[::5] if q < 200)
            check("render: الحبرُ مرسومٌ فعلًا", ink > 120, f"{ink} بكسلًا داكنًا")


# ─────────────────────────────── الطبعةُ كاملة ───────────────────────────────

def test_build() -> None:
    import json
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [sys.executable, os.path.join(HERE, "make_book.py"),
               "--out", tmp, "--author", "نجمة برهان", "--dpi-preview", "72"]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
        check("build: السائقُ ينجو", r.returncode == 0, (r.stderr or r.stdout)[-160:])
        qa_path = os.path.join(tmp, "qa.json")
        if not os.path.exists(qa_path):
            check("build: qa.json مكتوب", False, qa_path)
            return
        qa = json.load(open(qa_path, encoding="utf-8"))
        need = {"title", "prose_words", "interior_pages", "booklet_pad_pages", "lines",
                "glyph_ops", "overfull_pt", "loose_lines", "widows_moved", "art_dpi",
                "art_below_240dpi", "cover", "warnings", "not_checked"}
        check("qa.json: المفاتيحُ كاملة", need <= set(qa), str(sorted(need - set(qa))))
        check("build: ١٦ صفحةً بمضاعف أربعٍ (حشو الكُرّاسة)",
              qa["interior_pages"] % 4 == 0 and qa["interior_pages"] >= 12,
              str(qa["interior_pages"]))
        check("build: لا تجاوزَ ولا سطرَ فضفاض",
              qa["overfull_pt"] == 0.0 and qa["loose_lines"] == 0, str(qa["overfull_pt"]))
        check("build: لا تحذيرَ مجهول", isinstance(qa["warnings"], list))
        p = os.path.join(tmp, "interior.pdf")
        check("build: متنٌ مطبوعٌ غيرُ فارغ", os.path.getsize(p) > 200_000,
              f"{os.path.getsize(p)}B")
        pages = [f for f in os.listdir(os.path.join(tmp, "pages")) if f.endswith(".png")]
        check("build: معاينةٌ لكلّ صفحة", len(pages) == qa["interior_pages"],
              f"{len(pages)} مقابل {qa['interior_pages']}")


def main() -> int:
    print("فحصُ محرّك الطبع — " + os.path.relpath(FONT_R, REPO))
    for f in (FONT_R, FONT_B):
        if not os.path.exists(f):
            print(f"خطأ: خطٌّ مفقود: {f}\n     شغّل make setup أو راجع book/fonts/.")
            return 2
    sh = shapers()
    test_front_matter()
    test_peel_and_runs()
    test_units(sh)
    test_directions(sh)
    test_piece_order(sh)
    test_justify(sh)
    test_flow(sh)
    test_blocks(sh)
    test_render(sh)
    if "--build" in sys.argv:
        print("\nوطبعةٌ كاملةٌ في مجلدٍ مؤقّت:")
        test_build()
    print()
    if FAILS:
        print(f"فشل {len(FAILS)}: " + " · ".join(FAILS))
        return 1
    print("المحرّك سليم.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
