# story

مستودع كتابة قصص، يعمل كنظام: قواعد مكتوبة، بنية ملفات ثابتة، وأدوات تتحقّق من أن النص يفي بما التزم به.

## ابدأ من هنا

1. اقرأ [`AGENTS.md`](AGENTS.md) — هو نظام العمل في هذا المستودع: اللغة، الأسلوب، المواصفة، وتعريف الانتهاء.
2. اقرأ [`bible/`](bible) — الحقائق الثابتة التي لا تُنقض: الأسلوب، العالم، الشخصيات، الحبكة.
3. اعمل في [`works/`](works) — كل ملف = عمل واحد.

```bash
python3 tools/story.py new night-train --from short-story --title "قطار الليل"
$EDITOR works/night-train.md
python3 tools/story.py lint && python3 tools/story.py index
```

## الأوامر

| الأمر | الفعل |
|---|---|
| `tools/story.py new <slug> --from <قالب>` | إنشاء عمل من قالب ببيانات أمامية صحيحة |
| `tools/story.py lint [--strict]` | فحص المواصفة: الحقول، الأقسام، عتبات الحالة، الروابط المعطوبة |
| `tools/story.py index [--dry-run]` | توليد `works/index.md` مرتّبًا بالحالة مع عدّ كلمات |
| `tools/story.py review [--strict]` | فحص آلي لقواعد الأسلوب: جُمل طويلة، كليشيهات، وسوم انفعال، ترقيم لاتيني، ميزانية التشبيه |
| `tools/story.py stats` | إجماليات سريعة |
| `tools/story.py check-contradictions` | كشف التعارض بين «الحقائق» المسجّلة في `bible/` |
| `tools/story.py constraints` | عقدُ العالم: الممنوعاتُ والقيودُ والفصول من `bible/world.md` على المتن |
| `tools/story.py sweep [--strip-controls]` | تلوّثُ الحروف: CJK، لاتينيّةٌ في المتن، تحكّماتُ اتجاهٍ خفيّة |
| `tools/story.py debts [--gate]` | دفترُ الدُّيون السرديّة وحالتُها ومَن يُجيب عنها |
| `tools/check_qa.py [--a A --b B]` | تصديقُ `qa.json` ومقارنةُ قياسَي بناءَين |
| `tools/story.py self-test` | ٦٦ فحصًا ذاتيًا للأداة نفسها — شغّله بعد أي تعديل عليها |

بلا اعتماديات للطباعةِ النصّيّة: Python 3.8+ فقط. الطبعُ يحتاج `make setup`. أو اختصارات عبر `make` (`make lint`, `make review`, `make new SLUG=x`, `make check`).

## البنية

```
AGENTS.md   نظام العمل (المرجع الأعلى داخل المستودع)
bible/      style.md · world.md · characters.md · plot.md
templates/  short-story.md · chapter.md · fragment.md
works/      عمل واحد لكل ملف — و index.md مولَّد
tools/      story.py
book/       الطبع: typeset.py · make_book.py · paratext.md · IMAGES.md
```

## دورة حياة العمل

`idea` → `draft` → `revising` → `done`

كل انتقال مشروط بما يفحصه `lint` لا بما نشعر به: لا `draft` بلا ملخّص من ١٥ كلمة، ولا `done` بلا متن كافٍ وبلا `TODO` وبفحص تناقضات نظيف. التفاصيل في [`AGENTS.md` § 3](AGENTS.md).

## الحالة الحالية

- البواباتُ كلُّها في جدول [AGENTS.md § 7](AGENTS.md)؛ `make check` يشغّل النصّيّةَ منها و`make check-full` يزيد فحصَ المحرّك وطبعةً كاملة.
- [محاولة واحدة](works/one-attempt.md) — قصة قصيرة **مكتملة** بحالة `done`، اجتازت `lint` و`review --strict` و`check-contradictions`.
- [النسخة الخطأ](works/night-copy.md) — مسوّدة `draft` من نفس العالم.

الفهرس المولَّد: [works/index.md](works/index.md).

## الطبعة الجاهزة للطباعة

نصّ القصة الذي يُطبع هو [works/one-attempt.md](works/one-attempt.md) نفسه — لا نسخة
طباعة موازية تُحرَّر سرًّا. وحواشي الطبع (صفحة العنوان، الافتتاحية، الغلاف الخلفي،
بيانات الطبع) في [book/paratext.md](book/paratext.md).

```bash
make setup                        # بيئة الطبع (.venv داخل المستودع، غير ملتقَطة)
make book AUTHOR="نجمة برهان"                                  # → book/edition/{interior,cover}.pdf
make book AUTHOR="نجمة برهان" FLAGS="--impose --spine-mm 9"    # + صفحات طابعة وكعبٌ متّسع
```

كلُّ ذلك محفوظ في المستودع نفسه — لا في مجلد مؤقَّت (`AGENTS.md § 2`):

| الملف | المحتوى |
|---|---|
| [book/edition/interior.pdf](book/edition/interior.pdf) | المتن — ١٦ صفحة A5، بلا علامات قصّ |
| [book/edition/cover.pdf](book/edition/cover.pdf) | غلاف مطوّيّ بوجهٍ واحد بنزيف ٣ مم |
| [book/edition/pages/](book/edition) · `sheet.png` | معاينة كل صفحة + شيت كامل |
| [book/edition/qa.json](book/edition/qa.json) | ما ثُبِّت آليًا، وما لم يُثبَّت |
| [book/art/](book/art) · [book/fonts/](book/fonts) | الرسوم مصدرًا، وأميري (OFL) |

التفاصيل والتبعيات في [book/README.md](book/README.md)، وأوامر توليد الرسوم في
[book/IMAGES.md](book/IMAGES.md).
