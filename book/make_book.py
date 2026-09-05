#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""سائق الطبع: «محاولة واحدة» من ملف المستودع إلى كرّاس A5 جاهز للطباعة.

    python3 book/make_book.py --author "اسمك"

يقرأ `works/one-attempt.md` (المتن وحده: ملاحظات الشغل لا تُطبع) و`book/paratext.md`،
ويكتب في مجلد البناء — خارج git عمدًا، فالمستودع نصّي ولا ثنائيات فيه:

    interior.pdf   متن الكتاب، صفحة بصفحة
    cover.pdf      غلاف مطوي: خلف + كعب + أمام، بنزيف ٣ مم
    pages/*.png    معاينة كل صفحة، من نفس مشغّلات الـPDF
    sheet.png      الصفحات كلها في صورة واحدة (وهي ما أُراجِع بصريًا)
    qa.json        قياسات الطبع: صفحات، دقّة الرسوم، عرض الكعب، تحذيرات

السائق لا يعيد كتابة القصة ولا «ينقّحها»: المصدر هو نفسه الذي يفحصه story.py.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import typeset as T                                    # noqa: E402
from typeset import MM, Canvas, Flow, Shaper           # noqa: E402

PAGE_W, PAGE_H = 148 * MM, 210 * MM
MARGIN = 17 * MM
TEXT_W = PAGE_W - 2 * MARGIN
TOP, BOTTOM = 20 * MM, PAGE_H - 18 * MM
HEAD_Y, FOLIO_Y = 10.6 * MM, PAGE_H - 11.0 * MM
BODY, LEAD = 11.5, 19.0
SMALL, TINY = 9.0, 7.8
INK, MUTED = "#141414", "#5d564b"
DPI = 300.0
MAX_UP = 1.15            # لا نختلق تفاصيل: توسيم حتى ١٫١٥× فقط
BLEED = 3 * MM
PLATES = ["plate-1.png", "plate-2.png", "plate-3.png", "plate-4.png"]


# --------------------------------------------------------------- أدوات ----
def find_font(fonts_dir: str, *patterns: str) -> str:
    for pat in patterns:
        hits = sorted(glob.glob(os.path.join(fonts_dir, pat)))
        if hits:
            return hits[0]
    raise SystemExit(f"خطأ: لا خطّ يطابق {patterns} في {fonts_dir} — راجع book/README.md")


def load_paratext(path: str, author: str) -> dict:
    out, key = {}, None
    for line in open(path, encoding="utf-8").read().splitlines():
        h = re.match(r"^##[ \t]+(.+?)[ \t]*$", line)
        if h:
            key = h.group(1).strip()
            out[key] = []
        elif key is not None and line.strip() and not line.startswith("# "):
            out[key].append(line.strip())
    return {k: re.sub(r"\s*\n\s*", "\n", "\n".join(v)).replace("{{author}}", author).strip()
            for k, v in out.items()}


def load_story(path: str):
    text = open(path, encoding="utf-8").read()
    meta, body = T.read_front_matter(text)
    m = re.search(r"^##[ \t]*المتن[ \t]*$(.*?)(?=^##[ \t]|\Z)", body, re.M | re.S)
    prose = m.group(1) if m else ""
    scenes = [re.split(r"\n\s*\n", s.strip())
              for s in re.split(r"\n\s*---\s*\n", prose) if s.strip()]
    n_words = len([w for w in re.split(r"[\s،؛;.!?«»()]+", prose) if re.search(r"[\u0600-\u06ff]", w)])
    return meta, scenes, n_words


def prep_fit(src: str, box_w: float, box_h: float, tmp: str) -> tuple:
    """تحجيم إلى داخل صندوق بلا قصّ: يعيد (المسار، عرض pt، ارتفاع pt، dpi حقيقي)."""
    from PIL import Image
    im = Image.open(src).convert("RGB")
    need_w, need_h = box_w / 72 * DPI, box_h / 72 * DPI
    k = min(need_w / im.width, need_h / im.height, MAX_UP)
    if abs(k - 1.0) > 0.01:
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
    if tmp.lower().endswith((".jpg", ".jpeg")):    # اللوحات الحبرية: JPEG بلا فرع chroma ثقيل
        im.save(tmp, dpi=(int(DPI), int(DPI)), quality=94, subsampling=0, optimize=True)
    else:
        im.save(tmp, dpi=(int(DPI), int(DPI)))
    return tmp, im.width / DPI * 72, im.height / DPI * 72, round(DPI / k)


def sample_paper(src: str) -> str:
    from PIL import Image
    g = Image.open(src).convert("L")
    w, h = g.size
    v = sum(g.getpixel(p) for p in ((3, 3), (w - 4, 3), (3, h - 4), (w - 4, h - 4))) // 4
    return "#%02x%02x%02x" % (min(255, v + 6), min(255, v - 1), max(0, v - 21))


def draw_line(cv, page: int, shapers: dict, text: str, size: float, font: str,
              cx: float | None = None, baseline: float = 0.0,
              right: float | None = None, color: str = INK, gap_mul: float = 1.0):
    """سطر واحد بلا التفاف، عبر مسار bidi المشترك مع المحرّك. يعيد العرض."""
    ops, w = T.draw_single_line(shapers, text, size, font, cx=cx, right=right,
                               baseline=baseline, ink=color, gap_mul=gap_mul)
    cv.pages[page].extend(ops)
    return w


# ------------------------------------------------------------- المتن ----
def build_body(cv: Canvas, shapers: dict, story_path: str, paratext: dict,
               art_dir: str, out_dir: str, warnings: list) -> dict:
    meta, scenes, n_words = load_story(story_path)
    title = meta.get("title") or "محاولة واحدة"
    dpi_seen = {}

    # ١) نصف العنوان
    hp = cv.page()
    T.Flow.blocks(cv, shapers, hp, PAGE_W, PAGE_H, [
        {"text": title, "size": 13.5, "font": "R", "y": 0.40,
         "align": "center"}])
    # ٢) زخرفة مفتتحية
    p = cv.page()
    tp = prep_fit(os.path.join(art_dir, "tailpiece.png"), TEXT_W * 0.58, 36 * MM,
                  os.path.join(out_dir, "art", "tail-open.jpg"))
    dpi_seen["tailpiece.png"] = tp[3]
    cv.pages[p].append(("i", tp[0], (PAGE_W - tp[1]) / 2, PAGE_H * 0.44, tp[1], tp[2]))

    # ٣) صفحة العنوان
    cv.page()
    p = len(cv.pages) - 1
    lines = [l for l in paratext.get("صفحة العنوان", "").split("\n") if l.strip()]
    draw_line(cv, p, shapers, lines[0] if lines else title, 29.0, "B", cx=PAGE_W / 2,
              baseline=PAGE_H * 0.30)
    cv.pages[p].append(("r", PAGE_W / 2 - 17 * MM, PAGE_H * 0.30 - 13 * MM, 34 * MM, 0.5, MUTED))
    y = PAGE_H * 0.30 + 9 * MM
    for extra in lines[1:]:
        if extra.startswith("الطبعة") or extra.startswith("مَطبوع"):
            continue
        draw_line(cv, p, shapers, extra, 12.0, "R", cx=PAGE_W / 2, baseline=y)
        y += 6.0 * MM
    for foot in [l for l in lines if l.startswith("الطبعة") or l.startswith("مَطبوع")]:
        draw_line(cv, p, shapers, foot, 9.4, "R", cx=PAGE_W / 2, baseline=PAGE_H - 30 * MM)
        y = PAGE_H - 30 * MM + 4.6 * MM

    # ٤) الافتتاحية
    cv.page()
    p = len(cv.pages) - 1
    epi = [l for l in paratext.get("الافتتاحية", "").split("\n") if l.strip()]
    if epi:
        draw_line(cv, p, shapers, epi[0], 13.0, "R", right=PAGE_W - MARGIN - 8 * MM,
                  baseline=PAGE_H * 0.34)
        if len(epi) > 1:
            draw_line(cv, p, shapers, epi[1], 9.2, "R", right=PAGE_W - MARGIN - 8 * MM,
                      baseline=PAGE_H * 0.34 + 8 * MM, color=MUTED)

    # ٥) المشاهد: كل مشهد يبدأ على يُمْنى، ولوحته في صفحته المقابلة
    flow = Flow(cv, shapers, margin=MARGIN, top=TOP, bottom=BOTTOM, width=TEXT_W)
    flow.set_grid(LEAD)
    first_text_page = flow.page
    for idx, scene in enumerate(scenes):
        while flow.page % 2 == 1:
            flow.new_page()
        if idx == 0:
            flow.heading(title, size=19.5, font="B", align="center",
                         after=LEAD * 1.15, rule=True)
        else:
            flow.heading(["", "١", "٢", "٣", "٤"][idx + 1] if idx + 1 < 5 else str(idx + 1),
                          size=12.5, font="B", align="center", after=LEAD * 0.75)
        for para in [x.strip() for x in scene if x.strip()]:
            para = re.sub(r"\s+", " ", para)
            is_speech = para.count("«") >= 1 and len(para) < 90
            flow.paragraph(para, size=BODY, font="R", align="justify",
                           indent=0.0 if is_speech else 5.5, after=0.0)
        if idx < len(PLATES):
            src = os.path.join(art_dir, PLATES[idx])
            if os.path.exists(src):
                flow.new_page()
                pp = flow.page
                q = prep_fit(src, TEXT_W, BOTTOM - TOP - 3 * MM,
                             os.path.join(out_dir, "art", PLATES[idx].replace(".png", "-300.jpg")))
                dpi_seen[PLATES[idx]] = q[3]
                cv.pages[pp].append(("i", q[0], (PAGE_W - q[1]) / 2,
                                     TOP + (BOTTOM - TOP - q[2]) / 2, q[1], q[2]))
            else:
                warnings.append(f"لوحة مفقودة: {PLATES[idx]} — طُبع المشهد بلا مقابل مصوَّر.")
    last_text_page = flow.page

    # ٦) الختام على صفحة يُمْنى
    if flow.page % 2 == 1:
        flow.new_page()
    p = flow.page
    draw_line(cv, p, shapers, "تمّت", 12.5, "B", cx=PAGE_W / 2, baseline=PAGE_H * 0.44)
    t2 = prep_fit(os.path.join(art_dir, "tailpiece.png"), TEXT_W * 0.5, 30 * MM,
                  os.path.join(out_dir, "art", "tail-end.jpg"))
    cv.pages[p].append(("i", t2[0], (PAGE_W - t2[1]) / 2, PAGE_H * 0.50, t2[1], t2[2]))

    # ٧) بيانات الطبع في الصفحة الموالية (مقابلة للختام)
    col_page = flow.new_page()
    col = Flow(cv, shapers, margin=MARGIN, top=PAGE_H * 0.28, bottom=BOTTOM,
               width=TEXT_W, start_page=col_page)
    col.set_grid(LEAD * 0.76)
    for i, para in enumerate([re.sub(r"\s*\n\s*", " ", x).strip()
                              for x in paratext.get("بيانات الطبع", "").split("\n\n") if x.strip()]):
        col.paragraph(para, size=8.6 if i else 10.5, font="R" if i else "B",
                      align="right", lead=LEAD * 0.76, after=4.0)
    colophon_page = col.page

    # ٨) حشو الكُرّاسة: الكعب المفكّك يطلب مضاعفًا من أربع صفحات
    pad = 0
    while len(cv.pages) % 4:
        cv.page()
        pad += 1

    # ٩) أرقام الصفحات + جريٌ صامت، من المتن حتى ما قبل بيانات الطبع
    for i in range(first_text_page, min(last_text_page + 1, len(cv.pages))):
        ops = cv.pages[i]
        has_text = any(o[0] == "g" for o in ops)
        if has_text and i != colophon_page:
            draw_line(cv, i, shapers, title, SMALL, "R", cx=PAGE_W / 2,
                      baseline=HEAD_Y, color=MUTED)
        draw_line(cv, i, shapers, str(i + 1), SMALL, "R", cx=PAGE_W / 2, baseline=FOLIO_Y)

    return {"pages": len(cv.pages), "booklet_pad": pad, "words": n_words, "title": title,
            "first_text_page": first_text_page + 1, "dpi": dpi_seen,
            "flow": flow.stats}


# --------------------------------------------------------------- الغلاف ----
def build_cover(cv: Canvas, shapers: dict, paratext: dict, title: str, author: str,
                art_dir: str, out_dir: str, body_pages: int, warnings: list) -> dict:
    leaves = math.ceil(body_pages / 2)
    spine_mm = round(leaves * 0.10, 2)             # ورق ٨٠جم غير مطلي
    spine = spine_mm * MM
    W, H = PAGE_W * 2 + spine + 2 * BLEED, PAGE_H + 2 * BLEED
    cv.w, cv.h = W, H
    p = cv.page()                                   # صفحة واحدة: الخلف+الكعب+الأمام
    paper = sample_paper(os.path.join(art_dir, "cover.png"))
    cv.rect(0, 0, W, H, paper)
    front_x = BLEED + PAGE_W + spine
    cx = front_x + PAGE_W / 2
    art_w, art_h = PAGE_W * 0.80, PAGE_H * 0.60
    q = prep_fit(os.path.join(art_dir, "cover.png"), art_w, art_h,
                 os.path.join(out_dir, "art", "cover-fit.jpg"))
    draw_line(cv, p, shapers, title, 26.0, "B", cx=cx, baseline=BLEED + 19 * MM, color="#191712")
    draw_line(cv, p, shapers, "قصة قصيرة", 10.5, "R", cx=cx, baseline=BLEED + 25.5 * MM, color=MUTED)
    cv.pages[p].append(("i", q[0], cx - q[1] / 2, BLEED + 31 * MM, q[1], q[2]))
    if "اسم المؤل" in author:
        warnings.append("الكاتب ما زال «اسم المؤلِّف»؛ لم يُطبع على الغلاف. "
                        "أعد التشغيل بـ --author \"…\".")
    else:
        draw_line(cv, p, shapers, author, 12.5, "R", cx=cx, baseline=BLEED + PAGE_H - 12 * MM)

    # الخلف: نصّ الغلاف الخلفي + طابع الدار
    right = BLEED + PAGE_W - 16 * MM
    bf = Flow(cv, shapers, margin=BLEED + 16 * MM, top=BLEED + 20 * MM,
              bottom=BLEED + PAGE_H - 34 * MM, width=PAGE_W - 32 * MM, start_page=p)
    bf.set_grid(LEAD * 0.84)
    paras = [re.sub(r"\s*\n\s*", " ", x).strip()
             for x in paratext.get("الغلاف الخلفي", "").split("\n\n") if x.strip()]
    for i, para in enumerate(paras):
        bf.paragraph(para, size=11.0 if i == 0 else 9.4, font="R" if i else "B",
                     align="right", lead=LEAD * 0.84, after=LEAD * 0.55)
    # بلا زخرفة على الوجه الخلفي: وشمةٌ عند الحافة السفلى كانت تصطدم بسطر الدار
    # (التقاءٌ لا يُرى في المعاينة المصغَّرة ويُرى على الورق). الزينة في المتن وحده.
    draw_line(cv, p, shapers, "مستودع story · طبعة تجريبية للتحقّق من النظام",
              TINY, "R", cx=BLEED + PAGE_W / 2,
              baseline=BLEED + PAGE_H - 11 * MM, color=MUTED)

    if spine_mm < 6:
        warnings.append(f"الكعب {spine_mm} مم لـ{leaves} ورقة: لا يتّسع لعنوان؛ "
                        "طُبع خاليًا. للعنوان على الكعب يلزم ٦ مم على الأقل.")
    else:
        spine_text = paratext.get("الكعب", "").replace("\n", " · ")
        draw_line(cv, p, shapers, spine_text, 9.0, "R",
                  cx=BLEED + PAGE_W + spine / 2, baseline=BLEED + PAGE_H / 2)
    if len(cv.pages) != 1:
        warnings.append(f"الغلاف طُبِع على {len(cv.pages)} صفحات بدل واحدة؛ "
                        "قلّل نص الغلاف الخلفي أو صغّر خطّه.")
    return {"spine_mm": spine_mm, "leaves": leaves, "w_mm": round(W / MM, 1),
            "h_mm": round(H / MM, 1), "bleed_mm": round(BLEED / MM, 1),
            "cover_dpi": q[3]}


# ------------------------------------------------------------------ CLI ----
def main(argv=None) -> int:
    root = os.path.dirname(REPO)
    ap = argparse.ArgumentParser(description="تبويب «محاولة واحدة» — A5، أميري، HarfBuzz")
    ap.add_argument("--out", default=os.environ.get("BOOK_OUT", os.path.join(root, "build", "book")))
    ap.add_argument("--art", default=os.environ.get("BOOK_ART", os.path.join(root, "build", "art")))
    ap.add_argument("--fonts", default=os.environ.get("BOOK_FONTS", os.path.join(root, "build", "fonts")))
    ap.add_argument("--story", default=os.path.join(REPO, "works", "one-attempt.md"))
    ap.add_argument("--author", default="اسم المؤلِّف")
    ap.add_argument("--dpi-preview", type=float, default=180.0)
    ap.add_argument("--no-cover", action="store_true")
    ap.add_argument("--png-only", action="store_true")
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    for d, what in ((args.art, "الرسوم"), (args.fonts, "الخطوط")):
        if not os.path.isdir(d):
            raise SystemExit(f"خطأ: مجلد {what} غير موجود: {d}")
    if not os.path.exists(args.story):
        raise SystemExit(f"خطأ: لا ملف قصة: {args.story}")

    shapers = {"R": Shaper(find_font(args.fonts, "*Amiri_400Regular.ttf", "*400Regular*.ttf"), "R"),
               "B": Shaper(find_font(args.fonts, "*Amiri_700Bold.ttf", "*700Bold.ttf", "*700Bold*.ttf"), "B")}
    warnings: list[str] = []
    paratext = load_paratext(os.path.join(HERE, "paratext.md"), args.author)

    body = Canvas(PAGE_W, PAGE_H)
    info = build_body(body, shapers, args.story, paratext, args.art, args.out, warnings)
    cover_cv, cover_info = None, {}
    if not args.no_cover:
        cover_cv = Canvas(PAGE_W * 2, PAGE_H)   # يُعاد ضبطه داخل build_cover
        cover_info = build_cover(cover_cv, shapers, paratext, info["title"],
                                 args.author, args.art, args.out, info["pages"], warnings)

    # الخطّان المعاد ربطهما: بعد اكتمال كل التشكيل (شرطٌ لا اختيار)
    fonts = {}
    for key, sh in shapers.items():
        dst = os.path.join(args.out, f"Amiri-{key}-book.ttf")
        n = sh.build_remapped_font(dst)
        fonts[key] = dst
        if n < 60:
            warnings.append(f"خطّ {key} يضمّ {n} حرفًا فقط — شيء ما لم يُشكَّل.")

    T.render_png(body, os.path.join(args.out, "pages"), fonts, dpi=args.dpi_preview)
    T.contact_sheet(os.path.join(args.out, "pages"), os.path.join(args.out, "sheet.png"),
                    cols=5, thumb_w=300)
    if not args.png_only:
        T.render_pdf(body, os.path.join(args.out, "interior.pdf"), fonts, label=info["title"])
        if cover_cv is not None:
            T.render_pdf(cover_cv, os.path.join(args.out, "cover.pdf"), fonts, label="cover")
            T.render_png(cover_cv, os.path.join(args.out, "cover-pages"), fonts, dpi=args.dpi_preview)

    art_dpi = dict(info["dpi"])
    if cover_info:
        art_dpi["cover.png"] = cover_info["cover_dpi"]
    low = {k: v for k, v in art_dpi.items() if isinstance(v, (int, float)) and v < 240}
    qa = {"title": info["title"], "story_file": os.path.relpath(args.story, REPO),
          "prose_words": info["words"], "interior_pages": info["pages"],
          "glyph_ops": body.total_glyphs(), "lines": info["flow"]["lines"],
          "widows_moved": info["flow"]["widows_moved"],
          "overfull_pt": round(info["flow"]["overfull"], 2),
          "loose_lines": info["flow"].get("loose_lines", 0),
          "booklet_pad_pages": info["booklet_pad"],
          "art_dpi": art_dpi, "art_below_240dpi": low,
          "cover": cover_info, "page_mm": [148, 210],
          "margins_mm": [17, 17, 20, 18], "fonts_embedded_subset": True,
          "warnings": warnings,
          "not_checked": [
              "لا تحقيق تراصّ (imposition) لطابعة بعينها: الملف صفحات مفردة بحجمها الصافي",
              "بلا ملف ICC ولا علامات قصّ — تُضاف عند المصنع",
              "الرسوم توليد اصطناعي؛ حقوق الاستعمال التجاري على من يطبع",
              "المراجعة البصرية: صفحة العنوان وأول المتن وبيانات الطبع على ٣٠٠dpi والغلاف على ٢٢٠dpi؛ "
              "وبقية الصفحات فُحصت آليًا فقط (تجاوز العمود، الفضفاضة، الأرقيم)"]}
    with open(os.path.join(args.out, "qa.json"), "w", encoding="utf-8") as fh:
        json.dump(qa, fh, ensure_ascii=False, indent=2)

    print(f"المتن: {info['words']} كلمة · صفحات الكتاب: {info['pages']} "
          f"(حشو الكُرّاسة {info['booklet_pad']}) · أسطر مرسومة: {info['flow']['lines']} · "
          f"مشغّلات: {body.total_glyphs()}")
    if cover_info:
        print(f"الغلاف المطوي: {cover_info['w_mm']}×{cover_info['h_mm']} مم (بنزيف "
              f"{cover_info['bleed_mm']}) · الكعب {cover_info['spine_mm']} مم لـ{cover_info['leaves']} ورقة")
    print(f"دقّة الرسوم dpi: {json.dumps(info['dpi'], ensure_ascii=False)}")
    if cover_info:
        print(f"دقّة غلاف: {cover_info.get('cover_dpi')} dpi · أسطر فضفاضة: "
              f"{info['flow'].get('loose_lines', 0)} · سطر مُتجاوز: "
              f"{info['flow'].get('overfull', 0):.2f}pt")
    print(f"الناتج: {args.out}")
    for w in warnings:
        print("تنبيه:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
