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

## أين يكون الناتج

الناتج **داخل المستودع** في `book/edition/`، والرسوم في `book/art/`، والخطّ في
`book/fonts/` — فالمستودع هو مساحة العمل، وما يُكتب خارجه يضيع بتهيئة الصندوق
(قد جرى ذلك فعلًا: بُنيت الطبعة أول أمرها في `~/build/` فمضى مع المحو).

```
book/
├── art/       cover.png · plate-1..4.png · tailpiece.png     ← مصدر الرسوم، ملتقَط
├── fonts/     Amiri-Regular.ttf · Amiri-Bold.ttf (OFL)       ← لا تنزيل وقت البناء
└── edition/   interior.pdf · cover.pdf · qa.json · sheet.png
               pages/pNN.png · cover-pages/pNN.png            ← معاينة ١٥٠dpi
               art/ · Amiri-*-book.ttf                         ← مُشتقَّات، غير ملتقَطة
```

تُغطّي `.gitignore` القاعدةَين معًا: تلغي استثناء الوسائط داخل هذه الأدلة الثلاث،
وتُبقي المُشتَقَّين خارجًا لأنّ `make book` يعيدهما في ثانية.

## التبعيات

الخطّ والرسوم محفوظان في المستودع، فلا تنزيل وقت البناء. يبقى ما يُثبَّت بـpip،
وهو غير ملتقَط عمدا (`AGENTS.md § 2`) لأنّه حجمُ بيئةٍ لا حجمُ عمل:

```bash
make setup
# = python3 -m venv .venv && ./.venv/bin/pip install -r book/requirements.txt
```

ترخيص أميري: SIL Open Font License 1.1 — الإضمين والتوزيع مشروعان، ولذلك يُحفَظ
الخطّ نفسُه في `book/fonts/` بدل الاعتماد على مصدرٍ خارجي وقت الطبع.
## التشغيل

```bash
make book AUTHOR="اسم المؤلِّف"
# أو: ./.venv/bin/python book/make_book.py --author "اسم المؤلِّف"
# → book/edition/{interior.pdf,cover.pdf,pages/*.png,cover-pages/*.png,sheet.png,qa.json}
```

| الراية | المعنى |
|---|---|
| `--art DIR --fonts DIR --out DIR` | إعادة توجيه المجلدات (الافتراضي: `book/art`، `book/fonts`، `book/edition`) |
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
