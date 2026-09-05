# الطبع — `book/`

تحويل عملٍ من `works/` إلى ملفَّين جاهزَين للمَطبعة: متن A5 وغلاف مطوي.
النصّ المصدر هو ملفّ القصة نفسه؛ لا نسخة طباعة منفصلة تُحرَّر سرًّا.

```
book/
├── typeset.py     محرّك التبويب: HarfBuzz ← مشغّلات ← PDF/PNG
├── make_book.py   السائق: يقرأ works/*.md + paratext.md ويكتب الناتج
├── paratext.md    حواشي الطبع (عنوان، افتتاحية، غلاف خلفي، بيانات الطبع)
├── IMAGES.md      أوامر الرسوم المُستعمَلة ومصدرها
└── README.md      هذا الملف
```

## التبعيات (الصندوق لا يملك أيًّا منها ابتداءً)

```bash
python3 -m venv ~/.venv-book && ~/.venv-book/bin/pip install \
    reportlab uharfbuzz fonttools brotli pillow arabic-reshaper python-bidi
```

الخطّ: أميري من حزمة npm عامة، بلا تنزيل مباشر من GitHub:

```bash
mkdir -p ~/build/fonts && cd /tmp
url=$(curl -s https://registry.npmjs.org/@expo-google-fonts%2famiri \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['versions'][d['dist-tags']['latest']]['dist']['tarball'])")
curl -sL "$url" | tar xz -C /tmp && find /tmp/package -name '*.ttf' -exec cp {} ~/build/fonts/ \;
```

ترخيص أميري: SIL Open Font License 1.1 — الإضمين والتوزيع مشروعان.

الرسوم لا تُخزَّن في المستودع (`AGENTS.md § 2`)؛ توضع في `~/build/art/*.png`:
`cover.png`, `plate-1..4.png`, `tailpiece.png`. أوامر توليدها في `IMAGES.md`.

## التشغيل

```bash
~/.venv-book/bin/python book/make_book.py --author "اسم المؤلِّف"
# → ~/build/book/{interior.pdf,cover.pdf,pages/*.png,sheet.png,qa.json}
```

| الراية | المعنى |
|---|---|
| `--art DIR --fonts DIR --out DIR` | إعادة توجيه مجلدات البناء |
| `--story PATH` | طبع عمل آخر من `works/` (يُقرأ `## المتن` وحده) |
| `--dpi-preview N` | دقّة صور المعاينة (لا تمسّ الـPDF) |
| `--no-cover` / `--png-only` | بلا غلاف / معاينة فقط بلا PDF |

## ما يثبته `qa.json` وما لا يثبته

يثبت: عدد الصفحات، حشو الكُرّاسة إلى مضاعف أربعة، عدد الأسطر، الأسطر التي عجز
الضبط عن سدها (`loose_lines`)، أيّ سطر تجاوز العمود (`overfull_pt`)، الدقّة
الفعلية لكل رسم، عرض الكعب المحسوب من عدد الأوراق على ورق ٨٠جم.

لا يثبّت شيئًا جماليًا: لا يحكم على التوزيع البصري ولا على ملاءمة اللوحة لمشهد.
المراجعة البشرية الوحيدة المتاحة هنا هي `pages/*.png` و`sheet.png`، وقد فُحصت.

لا يُطبع حتى تُستوفى شرطان من `AGENTS.md`: العمل بحالة `done` (لا يقبله
`review --strict` وإلا)، و`check-contradictions` نظيف.
