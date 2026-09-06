#!/usr/bin/env python3
"""بوّابةُ `qa.json` — يقرأ ما تدّعيه الطبعةُ المحفوظة ويصدّقُه أو يفشل.

    python3 tools/check_qa.py                      # كتاب/edition/qa.json
    python3 tools/check_qa.py --a X/qa.json        # ملفٌّ آخر وحدَه
    python3 tools/check_qa.py --a A --b B          # مطابقةُ قياسَي بناءَين

الفكرةُ ليست تنميقًا: الطبعةُ محفوظةٌ في git، فإن غيّر محرّكٌ سطرًا أو أسقط
مشغّلًا بصريا، صار الملفُّ المرفوعُ غيرُ ما يولّده الكود. المقارنةُ تكشف ذلك.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(REPO, "book", "edition", "qa.json")

REQUIRED = ("build_args", "title", "story_file", "prose_words", "interior_pages", "booklet_pad_pages",
            "lines", "glyph_ops", "overfull_pt", "loose_lines", "widows_moved",
            "orphans_fixed", "art_dpi", "art_below_240dpi", "cover", "warnings",
            "not_checked", "page_mm", "margins_mm")
NUMERIC_KEYS = ("prose_words", "interior_pages", "booklet_pad_pages", "lines",
                "glyph_ops", "overfull_pt", "loose_lines", "widows_moved", "orphans_fixed")


def load(path: str) -> dict:
    if not os.path.exists(path):
        sys.exit(f"خطأ: لا ملفّ {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def gate(qa: dict, where: str) -> list:
    bad = []
    miss = [k for k in REQUIRED if k not in qa]
    if miss:
        bad.append(f"مفاتيح مفقودة في {where}: {', '.join(miss)}")
    if qa.get("interior_pages", 0) % 4:
        bad.append(f"{where}: الصفحات {qa.get('interior_pages')} ليست مضاعف أربعة "
                   "للكُرّاس البدبّاسة")
    if qa.get("booklet_pad_pages", 0) > 3:
        bad.append(f"{where}: حشوٌ زائد ({qa['booklet_pad_pages']} صفحة فارغة) — "
                   "أضِف عملًا أو قلّل الحواشي")
    if qa.get("overfull_pt", 0) > 0.0:
        bad.append(f"{where}: أسطرٌ تتجاوز العمود ({qa['overfull_pt']}pt)")
    if qa.get("loose_lines", 0) > 0:
        bad.append(f"{where}: أسطرٌ فضفاضة عجزَ الضبطُ عن سَدّها ({qa['loose_lines']})")
    if qa.get("art_below_240dpi"):
        bad.append(f"{where}: رسومٌ تحت ٢٤٠dpi: {qa['art_below_240dpi']}")
    if qa.get("prose_words", 0) < 200:
        bad.append(f"{where}: المتنُ {qa.get('prose_words')} كلمة — أقلُّ من عتبة done")
    if not qa.get("not_checked"):
        bad.append(f"{where}: 'not_checked' فارغة — على الطبعَةِ أن تصرّح بما لم تُتحقّق منه")
    cov = qa.get("cover") or {}
    if cov and cov.get("spine_mm", 0) < 6 and cov.get("spine_has_title"):
        bad.append(f"{where}: كعبٌ {cov['spine_mm']}مم بعنوانٍ عليه — لن يُقرأ")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="فحص qa.json ومقارنة بناءَين")
    ap.add_argument("--a", default="", help="ملفُّ qa (أو المحفوظُ افتراضًا)")
    ap.add_argument("--b", default="", help="ملفُّ qa آخر للمقارنة")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    path_a = args.a or DEFAULT
    qa_a = load(path_a)
    bad = gate(qa_a, os.path.relpath(path_a, REPO) if path_a.startswith(REPO) else path_a)

    if args.b:
        qa_b = load(args.b)
        name_a = os.path.relpath(path_a, REPO) if path_a.startswith(REPO) else path_a
        name_b = os.path.relpath(args.b, REPO) if args.b.startswith(REPO) else args.b
        aa, ab = qa_a.get("build_args") or {}, qa_b.get("build_args") or {}
        if aa and ab and aa != ab:
            diff = ", ".join(f"{k}: {ab.get(k)!r}≠{aa.get(k)!r}" for k in sorted(set(aa) | set(ab))
                             if aa.get(k) != ab.get(k))
            print(f"⚠ البناءان مختلفا الوسوم — لا مقارنةَ قياساتٍ بينهما:\n    {diff}")
            print("  (لا عيب في أحدهما؛ لكنّ مقارنةً بمُدخَلاتٍ مختلفةٍ تُنتج إنذارًا كاذبًا.)")
            return 0
        for k in NUMERIC_KEYS:
            va, vb = qa_a.get(k), qa_b.get(k)
            if va != vb:
                bad.append(f"القياسُ اختلف بين البناءين: {k} = {vb} في {name_b} "
                           f"مقابل {va} في {name_a}")
        if qa_a.get("title") != qa_b.get("title"):
            bad.append(f"العنوان مختلف: {qa_b.get('title')!r} مقابل {qa_a.get('title')!r}")
        if not bad:
            print(f"بناءٌ مطابق: {len(NUMERIC_KEYS)} قياسًا متساوية بين {name_b} و{name_a}"
                  " (الوسومُ ذاتها).")

    if args.json:
        print(json.dumps({"ok": not bad, "file": path_a, "problems": bad},
                         ensure_ascii=False, indent=2))
    elif bad:
        for b in bad:
            print(f"✗ {b}")
        print(f"\nqa: {len(bad)} مشكلة.")
        return 1
    else:
        print(f"✓ qa.json مقبول: {qa_a['interior_pages']} صفحة، {qa_a['lines']} سطرًا، "
              f"{qa_a['glyph_ops']} مشغّلًا، لا تجاوزَ ولا فضفاضة، "
              f"{len(qa_a['not_checked'])} بندًا غيرُ مُتحقَّقٍ منه — مصرَّحٌ به.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
