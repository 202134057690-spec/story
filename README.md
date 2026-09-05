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
| `tools/story.py self-test` | ٤٤ فحصًا ذاتيًا للأداة نفسها — شغّله بعد أي تعديل عليها |

بلا اعتماديات: Python 3.8+ فقط. أو اختصارات عبر `make` (`make lint`, `make review`, `make new SLUG=x`, `make check`).

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

- [محاولة واحدة](works/one-attempt.md) — قصة قصيرة **مكتملة** بحالة `done`، اجتازت `lint` و`review --strict` و`check-contradictions`.
- [النسخة الخطأ](works/night-copy.md) — مسوّدة `draft` من نفس العالم.

الفهرس المولَّد: [works/index.md](works/index.md).

## الطبعة الجاهزة للطباعة

نصّ القصة الذي يُطبع هو [works/one-attempt.md](works/one-attempt.md) نفسه — لا نسخة
طباعة موازية تُحرَّر سرًّا. وحواشي الطبع (صفحة العنوان، الافتتاحية، الغلاف الخلفي،
بيانات الطبع) في [book/paratext.md](book/paratext.md).

```bash
make book AUTHOR="نجمة برهان"      # أو: ~/.venv-book/bin/python book/make_book.py --author ...
```

**لا ملف PDF ولا صورة داخل git**: المستودع يحفظ النصّ والكود فقط
([`AGENTS.md` § 2](AGENTS.md))، والناتج يُبنى خارجَه في `~/build/book/`:

| الملف | المحتوى |
|---|---|
| `~/build/book/interior.pdf` | المتن — ١٦ صفحة A5، بلا علامات قصّ |
| `~/build/book/cover.pdf` | غلاف مطوّيّ بوجهٍ واحد بنزيف ٣ مم |
| `~/build/book/pages/` · `sheet.png` | معاينة كل صفحة + شيت كامل |
| `~/build/book/qa.json` | ما ثُبِّت آليًا، وما لم يُثبَّت |

التفاصيل والتبعيات في [book/README.md](book/README.md)، وأوامر توليد الرسوم في
[book/IMAGES.md](book/IMAGES.md).
