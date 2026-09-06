#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""محرّك تبويب عربي صغير: تشكيل HarfBuzz ← مشغّلات رسم ← محرّكان (PDF / PNG).

لماذا لا تحويل من HTML؟ لا LaTeX ولا LibreOffice ولا خطّ عربي في الصندوق،
والتحويل الأعمى يعطي «ما تراه ليس ما يُطبع». المسار هنا واحد:

    نصّ منطقى → تقطيع وحدات → HarfBuzz (GSUB/GPOS حقيقي) → حروف بمواضعها
             ├→ reportlab: متّجه، خطّ مُضمَّن فرعيًّا (PDF)
             └→ Pillow:   نفس الحروف بنفس المواضع (PNG للمعاينة)

وحتّى يقرأ المحرّكان الحرف نفسه، نبني نسخة من الخطّ أُعيد ربط cmap فيها:
كل gid على حرف في المنطقة الخاصة (U+E000…). لا اختلاف بين المعاينة والطبع.

ثنائية الاتجاه (bidi): لا نُسلّم السطر كلّه إلى HarfBuzz، لأن الاتجاه rtl
يقلب ترتيب الجزر اللاتينية داخله. بدل ذلك نُقطّع السطر إلى **وحدات**
(كلمة + ترقيمها ملحقًا منفصلًا)، نشكّل كل وحدة باتجاهها، ثم نرصّها
يُمنةً نحو اليسار. هذه هي القاعدة المعتادة للنصّ ثنائي المستوى بقدر ما تحتاجه
صفحة كتاب: عربيّ + أرقام/أعلام لاتينية قصيرة.

مقياس الإحداثيات: نقاط (pt)، y نحو أسفل الصفحة، الأصل الزاوية اليُسرى العليا.
"""

from __future__ import annotations

import os
import re

MM = 72.0 / 25.4
PT_PER_IN = 72.0

ARABIC_LETTER = re.compile(r"[\u0621-\u064A\u0660-\u0669\u0671-\u06D3\u06FA-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]")
WORD_CHAR = re.compile(r"[\u0621-\u064A\u0660-\u0669\u0671-\u06D30-9A-Za-z]")  # الأرقام العربية حروفٌ في سياق الترقيم: لا تُعامَل كرمز خالص
# حرف عربي أو علامة تشكيل — الأرقام ليست كذلك: تسلسلها يقرأ من اليسار
# إلى اليمين ولو وسط الكلام العربي (AN في خوارزمية bidi)، وعكسها يُخرج
# «٨٤١» بدل «١٤».
AR_LETTER = re.compile(r"[\u0621-\u064A\u0671-\u06D3\u06FA-\u06FF"
                       r"\uFB50-\uFDFF\uFE70-\uFEFF\u064B-\u065F\u0670]")


def read_front_matter(md: str):
    """كتلة `---` الافتتاحية ← (dict, متن). نسخة مطابقة لسلوك tools/story.py."""
    lines = md.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                meta = {}
                for raw in lines[1:i]:
                    if ":" in raw:
                        k, _, v = raw.partition(":")
                        meta[k.strip()] = v.strip().strip(chr(39) + chr(34)).strip()
                return meta, "\n".join(lines[i + 1:])
    return {}, md


# ---------------------------------------------------------------- Shaper ----
class Shaper:
    """تشكيل HarfBuzz + خريطة gid ← حرف PUA، وخطّ معاد الربط للمحرّكين."""

    FEATURES = {"kern": True, "liga": True, "rlig": True, "calt": True,
                "ccmp": True, "locl": True, "mark": True, "mkmk": True}

    def __init__(self, ttf_path: str, name: str = "R"):
        import uharfbuzz as hb
        self._hb, self.name, self.path = hb, name, ttf_path
        self.blob = hb.Blob.from_file_path(ttf_path)
        self.face = hb.Face(self.blob)
        self.upem = self.face.upem or 1000
        self.gid_to_char: dict[int, str] = {}
        self._next_pua = 0xE000
        self.ascender, self.descender = 1.0, 0.3
        try:
            from fontTools.ttLib import TTFont
            tt = TTFont(ttf_path)
            hhea = tt["hhea"]
            self.ascender = hhea.ascender / self.upem
            self.descender = abs(hhea.descender) / self.upem
        except Exception:
            pass

    def _font(self):
        f = self._hb.Font(self.face)
        f.scale = (self.upem, self.upem)      # بوحدات التصميم؛ القياس لاحقًا
        return f

    def _char(self, gid: int) -> str:
        ch = self.gid_to_char.get(gid)
        if ch is None:
            if self._next_pua > 0xF000:
                raise RuntimeError("امتلأت المنطقة الخاصة: قسّم الكتاب")
            ch = chr(self._next_pua)
            self._next_pua += 1
            self.gid_to_char[gid] = ch
        return ch

    def shape(self, text: str, size: float):
        """[(char, adv, xoff, yoff)] + العرض، باتجاه يُحدَّده محتوى النص."""
        if not text:
            return [], 0.0
        rtl = bool(ARABIC_LETTER.search(text))
        return self.shape_rtl(text, size, rtl)

    def shape_rtl(self, text: str, size: float, rtl: bool):
        buf = self._hb.Buffer()
        buf.add_str(text)
        buf.direction = "rtl" if rtl else "ltr"
        if rtl:
            buf.script, buf.language = "Arab", "ar"
        else:
            buf.script, buf.language = "Latn", "en"
        self._hb.shape(self._font(), buf, self.FEATURES)
        glyphs, w = [], 0.0
        for gi, gp in zip(buf.glyph_infos, buf.glyph_positions):
            adv = gp.x_advance * size / self.upem
            glyphs.append((self._char(gi.codepoint), adv,
                           gp.x_offset * size / self.upem,
                           gp.y_offset * size / self.upem))
            w += adv
        return glyphs, w

    def width(self, text: str, size: float) -> float:
        return self.shape(text, size)[1]

    def space(self, size: float) -> float:
        return self.width(" ", size)

    def build_remapped_font(self, dst_ttf: str) -> int:
        from fontTools.ttLib import TTFont
        tt = TTFont(self.path)
        order = tt.getGlyphOrder()
        cmap = {0x20: order[0]}
        for gid, ch in self.gid_to_char.items():
            if gid < len(order):
                cmap[ord(ch)] = order[gid]
        sub = tt["cmap"].tables[0]
        sub.platformID, sub.platEncID, sub.encodingID = 3, 1, 0
        sub.cmap, sub.isUnicode = cmap, True
        tt["cmap"].tables = [sub]
        os.makedirs(os.path.dirname(os.path.abspath(dst_ttf)), exist_ok=True)
        tt.save(dst_ttf)
        return len(cmap)


# --------------------------------------------------------------- bidi ----
def peel(word: str):
    """`«الدفتر»،` → [`«`, `الدفتر`, `»،`] — الترقيم يُفصل ليأخذ اتجاه الفقرة."""
    lead = ""
    m = re.match(r"^\W+(?=\w)", word, re.S)
    if m:
        lead = m.group(0)
        word = word[len(lead):]
    trail = ""
    m = re.search(r"\W+$", word)
    if m and word[:m.start()]:
        trail = m.group(0)
        word = word[:m.start()]
    if not word:                        # رمز وحده: يبقى كتلة واحدة
        return [lead + trail or word] if (lead or trail) else []
    return [p for p in (lead, word, trail) if p]


def _script_runs(part: str):
    """تقسيم القطعة إلى مقاطع نصّ واحد: عربيٌّ يُشكَّل من اليمين، وغيرُ عربيٍّ
    (لاتينيّ أو رقم) من اليسار. هكذا يبقى `وbook/typeset.py` مقروءًا: الواو
    في محلّها من الكلام، والاسم اللاتينيّ في ترتيبه، بلا عكسٍ داخلي.
    الترقيمُ الخالص يُتْرك لاتجاه الفقرة لأنه يتدلّى من الكلام العربي."""
    runs, cur, cur_ar = [], "", None
    for ch in part:
        ar = bool(AR_LETTER.match(ch))
        if cur_ar is None or ar == cur_ar:
            cur += ch
            cur_ar = ar
            continue
        runs.append((cur, cur_ar))
        cur, cur_ar = ch, ar
    if cur:
        runs.append((cur, cur_ar))
    if len(runs) == 1 and not WORD_CHAR.search(part):
        runs = [(part, True)]
    return runs


def shape_units(shapers: dict, text: str, size: float, font: str):
    """وحدات السطر: كل وحدة = قطع متلاصقة، والمسافات بين الوحدات لا داخلها.

    رصّ القطع داخل الوحدة يجري دائمًا من اليمين إلى اليسار: هذا المحرّك
    أحاديّ الاتجاه — فقرةُ الكتاب كلِّها عربيّة، فأوّلُ المنطق أقصى اليمين،
    ولو رُصَّت القطعُ يسارًا لانقلبت الفاصلةُ تحت الكلمةِ الخطأ ولصار
    «(س» «س)». أمّا داخل القطعة فالاتجاهُ للُّغة نفسها: اللاتينيُّ والأرقام
    يُقرأان من اليسار، وهذا يُحدَّد عند التشكيل لا عند الرصّ.
    """
    units = []
    for raw in [w for w in re.split(r"\s+", text.strip()) if w]:
        pieces = []
        for part in peel(raw):
            for run, rtl in _script_runs(part):
                glyphs, w = shapers[font].shape_rtl(run, size, rtl)
                pieces.append({"g": glyphs, "w": w})
        if pieces:
            units.append({"pieces": pieces, "w": sum(p["w"] for p in pieces)})
    return units


def place_units(units, gap: float, right: float, baseline: float, font: str, size: float,
                ink: str = "#141414", justify_to: float | None = None,
                justify_max: float = 0.16):
    """رسم الوحدات من اليمين إلى اليسار؛ يعيد (ops, العرض المحقّق)."""
    content = sum(u["w"] for u in units) + gap * max(0, len(units) - 1)
    loose = False
    if justify_to is not None and len(units) > 1 and justify_to > content:
        deficit = (justify_to - content) / justify_to
        if deficit <= justify_max:
            gap += (justify_to - content) / (len(units) - 1)
            content = justify_to
        else:
            loose = True
    ops, cursor = [], right
    for u in units:
        x_left = cursor - u["w"]          # الحافّة اليُسرى للوحدة؛ اليُمنى معروفة
        gx = cursor                       # أوّلُ المنطق أقصى اليمين
        for p in u["pieces"]:
            x = gx - p["w"]
            for ch, adv, xo, yo in p["g"]:
                ops.append(("g", font, ch, x + xo, baseline + yo, size, ink))
                x += adv                  # وداخلَ القطعةِ يسارًا، بلغةِ القطعة
            gx -= p["w"]
        cursor = x_left - gap             # ثم مسافة، فالوحدة التالية إلى يسارها
    return ops, content, loose


def draw_single_line(shapers: dict, text: str, size: float, font: str, *,
                     cx: float | None = None, right: float | None = None,
                     baseline: float = 0.0, ink: str = "#141414",
                     gap_mul: float = 1.0):
    """سطر واحد بلا التفاف. يعيد (ops, content_w)."""
    gap = shapers[font].space(size) * gap_mul
    units = shape_units(shapers, text, size, font)
    if not units:
        return [], 0.0
    _, content, _ = place_units(units, gap, 0, 0, font, size)
    if cx is not None:
        right = cx + content / 2
    ops, content2, _ = place_units(units, gap, right, baseline, font, size, ink=ink)
    return ops, max(content, content2)


# ----------------------------------------------------------------- Ops ----
class Canvas:
    """وعاء مشغّلات مجرّدة؛ المحرّكات تنفّذها حرفيًا."""

    def __init__(self, width: float, height: float):
        self.w, self.h = width, height
        self.pages: list[list] = []
        self.images: set[str] = set()

    def page(self) -> int:
        self.pages.append([])
        return len(self.pages) - 1

    @property
    def cur(self) -> list:
        if not self.pages:
            self.page()
        return self.pages[-1]

    def glyphs(self, ops, page: int | None = None):
        (self.pages[page] if page is not None else self.cur).extend(ops)

    def glyph(self, font: str, ch: str, x: float, y: float, size: float,
              color: str = "#141414"):
        self.cur.append(("g", font, ch, x, y, size, color))

    def image(self, path: str, x: float, y: float, w: float, h: float,
              page: int | None = None):
        self.images.add(path)
        (self.pages[page] if page is not None else self.cur).append(
            ("i", path, x, y, w, h))

    def rule(self, x: float, y: float, w: float, thick: float = 0.45,
             color: str = "#2b2b2b", page: int | None = None):
        (self.pages[page] if page is not None else self.cur).append(
            ("r", x, y, w, thick, color))

    def rect(self, x: float, y: float, w: float, h: float, fill: str,
             page: int | None = None):
        (self.pages[page] if page is not None else self.cur).append(
            ("b", x, y, w, h, fill))

    def total_glyphs(self) -> int:
        return sum(1 for p in self.pages for op in p if op[0] == "g")


# ---------------------------------------------------------------- Flow ----
class Flow:
    """تدفق فقرة-بفقرة في عمود واحد، مع كسر صفحات على شبكة أَسُس."""

    justify_max = 0.16          # لا نمدّ سطرًا ينقصه أكثر من ١٦٪ من العرض

    def __init__(self, cv: Canvas, shapers: dict, *, margin: float, top: float,
                 bottom: float, width: float, start_page: int | None = None):
        self.cv, self.sh = cv, shapers
        self.margin, self.top, self.bottom, self.width = margin, top, bottom, width
        self.page = cv.page() if start_page is None else start_page
        self.y, self.lead = top, None
        self.stats = {"lines": 0, "pages": 0, "overfull": 0.0, "widows_moved": 0,
                      "orphans_fixed": 0, "loose_lines": 0, "longest_line": 0.0}

    # — الصفحات —
    def new_page(self) -> int:
        self.page = self.cv.page()
        self.stats["pages"] += 1
        self.y = self.top
        return self.page

    def set_grid(self, lead: float):
        self.lead = lead
        self.y = self.top

    def _ensure(self, h: float) -> bool:
        if self.y + h > self.bottom:
            self.new_page()
            return True
        return False

    # — الفقرة —
    def paragraph(self, text: str, *, size: float = 11.5, font: str = "R",
                  lead: float | None = None, align: str = "justify",
                  before: float = 0.0, after: float = 0.0, indent: float = 0.0):
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return
        lead = lead or self.lead or size * 1.65
        gap = self.sh[font].space(size)
        units = shape_units(self.sh, text, size, font)
        if not units:
            return
        # تقطيع جشع إلى سطور
        lines, cur, used = [], [], 0.0
        for u in units:
            add = u["w"] + (0.0 if not cur else gap)
            avail = self.width - (indent if not lines else 0.0)
            if cur and used + add > avail:
                lines.append((cur, indent if not lines else 0.0))
                cur, used = [u], u["w"]
            else:
                cur.append(u)
                used += add
        if cur:
            lines.append((cur, indent if len(lines) == 0 else 0.0))
        # يتيمةُ الكلمة: لا يجوز أن تُنهِيَ فقرةً بكلمةٍ وحدها تحت سطرٍ ممتلئ.
        # تُسحب كلمةٌ من السطر السابق ما دام الاتّساعُ باقيًا — وهذه قاعدةُ طباعة،
        # لا ذوق: السطرُ ذي الكلمة الواحدة يبدو خطأً مطبعيًا ولو كان صحيحًا.
        while len(lines) >= 2 and len(lines[-1][0]) == 1:
            p_units = lines[-2][0]
            if len(p_units) < 2:
                break
            moved = p_units[-1]
            prev_w = sum(u["w"] for u in p_units) + gap * (len(p_units) - 1)
            last_w = lines[-1][0][0]["w"]
            if prev_w - moved["w"] - gap > self.width + 0.01 or \
                    last_w + moved["w"] + gap > self.width + 0.01:
                break
            lines[-2] = (p_units[:-1], lines[-2][1])
            lines[-1] = ([moved] + lines[-1][0], lines[-1][1])
            self.stats["orphans_fixed"] += 1

        # أرملة سطرٍ واحد: انقل السطرين معًا
        if len(lines) > 2 and self.y + lead * 2 > self.bottom:
            self.new_page()
            self.stats["widows_moved"] += 1
        self.y += before
        for i, (lu, ind) in enumerate(lines):
            self._ensure(lead)
            last = (i == len(lines) - 1)
            right = self.margin + self.width - ind
            if align == "center":
                _, content, _ = place_units(lu, gap, right, 0, font)
                right = self.margin + (self.width + content) / 2
                jt = None
            elif align == "justify" and not last:
                jt = self.width - ind
            else:
                jt = None
            ops, content, loose = place_units(lu, gap, right, self.y + size * 1.02,
                                              font, size, justify_to=jt,
                                              justify_max=self.justify_max)
            self.cv.pages[self.page].extend(ops)
            self.stats["lines"] += 1
            self.stats["longest_line"] = max(self.stats["longest_line"], content)
            if jt and content - jt > 0.5:
                self.stats["overfull"] = max(self.stats["overfull"], content - jt)
            if loose:
                self.stats["loose_lines"] += 1
            self.y += lead
        self.y += after

    def heading(self, text: str, *, size: float = 16.0, font: str = "B",
                align: str = "center", before: float = 0.0, after: float = 0.0,
                rule: bool = False, color: str = "#141414"):
        self.y += before
        self._ensure(size * 1.6)
        gap = self.sh[font].space(size)
        units = shape_units(self.sh, text, size, font)
        if not units:
            return
        right = self.margin + self.width
        if align == "center":
            _, content, _ = place_units(units, gap, right, 0, font, size)
            right = self.margin + (self.width + content) / 2
        ops, content, _ = place_units(units, gap, right, self.y + size * 1.15,
                                      font, size, ink=color)
        self.cv.pages[self.page].extend(ops)
        self.stats["lines"] += 1
        self.y += size * 1.35
        if rule:
            self.cv.rule(self.margin + self.width * 0.36, self.y - size * 0.15,
                         self.width * 0.28, 0.5, "#6a6156", page=self.page)
            self.y += 5.0
        self.y += after

    def rule(self, **kw):
        self.cv.rule(page=self.page, **kw)

    def image_centered(self, path: str, box_w: float, box_h: float, w: float, h: float,
                       x_off: float = 0.0, y: float | None = None):
        cx = self.margin + box_w / 2 + x_off
        yy = (self.y if y is None else y)
        self.cv.image(path, cx - w / 2, yy, w, h, page=self.page)

    # — صفحات الحواشي: بلوكات بمواضع نسبية —
    @staticmethod
    def blocks(cv: Canvas, shapers: dict, page: int, width: float, height: float,
               items: list):
        """items: [{text,size,font,y(0..1),align,lead,color,rule,gap,margin}]"""
        for b in items:
            sh = shapers[b.get("font", "R")]
            size = b.get("size", 11.5)
            color = b.get("color", "#141414")
            lead = b.get("lead", 1.5)
            gap = sh.space(size) * b.get("gap", 1.0)
            y0 = height * b.get("y", 0.5)
            for k, ln in enumerate([l for l in b["text"].split("\n") if l.strip()]):
                units = shape_units(shapers, ln, size, b.get("font", "R"))
                if not units:
                    continue
                _, content, _ = place_units(units, gap, 0, 0, b.get("font", "R"), size)
                if b.get("align", "center") == "center":
                    right = width / 2 + content / 2
                else:
                    right = width - b.get("margin", 17 * MM)
                ops, _, _ = place_units(units, gap, right, y0 + k * size * lead,
                                        b.get("font", "R"), size, ink=color)
                cv.pages[page].extend(ops)
                if b.get("rule") and k == 0:
                    cv.pages[page].append(("r", width / 2 - size * 3.2,
                                          y0 - size * 1.45, size * 6.4, 0.5, color))
        return page


# ------------------------------------------------------------ المحرّكات ----
def render_pdf(cv: Canvas, out_pdf: str, fonts: dict, label: str = "book"):
    from reportlab.pdfgen import canvas as rl
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont as RLTT
    for key, path in fonts.items():
        pdfmetrics.registerFont(RLTT("BOOK-" + key, path))
    c = rl.Canvas(out_pdf, pagesize=(cv.w, cv.h))
    c.setTitle(label)
    c.setCreator("story/book/typeset.py")
    c.setAuthor("")
    for ops in cv.pages:
        for op in ops:
            kind = op[0]
            if kind == "g":
                _, font, ch, x, y, size = op[:6]
                color = op[6] if len(op) > 6 else "#141414"
                c.setFont("BOOK-" + font, size)
                c.setFillColor(HexColor(color))
                c.drawString(x, cv.h - y, ch)
            elif kind == "i":
                _, path, x, y, w, h = op
                c.drawImage(path, x, cv.h - y - h, width=w, height=h,
                            preserveAspectRatio=False, mask=None)
            elif kind == "r":
                _, x, y, w, thick, color = op
                c.setStrokeColor(HexColor(color))
                c.setLineWidth(thick)
                c.line(x, cv.h - y, x + w, cv.h - y)
            elif kind == "b":
                _, x, y, w, h, fill = op
                c.setFillColor(HexColor(fill))
                c.rect(x, cv.h - y - h, w, h, stroke=0, fill=1)
        c.showPage()
    c.save()
    return out_pdf


def render_png(cv: Canvas, out_dir: str, fonts: dict, dpi: float = 150.0,
               bg: str = "#ffffff"):
    """المعاينة: نفس المشغّلات على بكسل — لا إعادة تشكيل ولا تقدير."""
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(out_dir, exist_ok=True)
    k = dpi / PT_PER_IN
    cache: dict = {}
    made = []
    for i, ops in enumerate(cv.pages):
        im = Image.new("RGB", (round(cv.w * k), round(cv.h * k)), bg)
        d = ImageDraw.Draw(im)
        for op in ops:
            if op[0] == "g":
                _, font, ch, x, y, size = op[:6]
                color = op[6] if len(op) > 6 else "#141414"
                key = (font, round(size * k))
                if key not in cache:
                    cache[key] = ImageFont.truetype(fonts[font], key[1])
                d.text((x * k, y * k), ch, font=cache[key], fill=color, anchor="ls")
            elif op[0] == "i":
                _, path, x, y, w, h = op
                art = Image.open(path).convert("RGB").resize(
                    (max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
                im.paste(art, (round(x * k), round(y * k)))
            elif op[0] == "r":
                _, x, y, w, thick, color = op
                d.line([x * k, y * k, (x + w) * k, y * k], fill=color,
                       width=max(1, round(thick * k)))
            elif op[0] == "b":
                _, x, y, w, h, fill = op
                d.rectangle([x * k, y * k, (x + w) * k, (y + h) * k], fill=fill)
        path = os.path.join(out_dir, f"p{i + 1:02d}.png")
        im.save(path)
        made.append(path)
    return made


def contact_sheet(png_dir: str, out_png: str, cols: int = 5, thumb_w: int = 300):
    from PIL import Image
    files = sorted(f for f in os.listdir(png_dir) if f.endswith(".png"))
    if not files:
        return None
    base = Image.open(os.path.join(png_dir, files[0]))
    ratio = base.height / base.width
    tw, th = thumb_w, max(1, int(thumb_w * ratio))
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 8, rows * th + (rows + 1) * 8),
                      "#7d7d7d")
    for i, f in enumerate(files):
        im = Image.open(os.path.join(png_dir, f)).resize((tw, th), Image.LANCZOS)
        sheet.paste(im, (8 + (i % cols) * (tw + 8), 8 + (i // cols) * (th + 8)))
    sheet.save(out_png)
    return out_png
