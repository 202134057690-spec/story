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
| `tools/story.py stats` | إجماليات سريعة |
| `tools/story.py check-contradictions` | كشف التعارض بين «الحقائق» المسجّلة في `bible/` |
| `tools/story.py self-test` | ٣١ فحصًا ذاتيًا للأداة نفسها — شغّله بعد أي تعديل عليها |

بلا اعتماديات: Python 3.8+ فقط. أو اختصارات عبر `make` (`make lint`, `make new SLUG=x`, `make check`).

## البنية

```
AGENTS.md   نظام العمل (المرجع الأعلى داخل المستودع)
bible/      style.md · world.md · characters.md · plot.md
templates/  short-story.md · chapter.md · fragment.md
works/      عمل واحد لكل ملف — و index.md مولَّد
tools/      story.py
```

## دورة حياة العمل

`idea` → `draft` → `revising` → `done`

كل انتقال مشروط بما يفحصه `lint` لا بما نشعر به: لا `draft` بلا ملخّص من ١٥ كلمة، ولا `done` بلا متن كافٍ وبلا `TODO` وبفحص تناقضات نظيف. التفاصيل في [`AGENTS.md` § 3](AGENTS.md).

## الحالة الحالية

مثال مؤسِّس واحد: [النسخة الخطأ](works/night-copy.md) — مسوّدة تعمل عليها القواعد كلها، والفهرس في [works/index.md](works/index.md).
