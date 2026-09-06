# اختصارات مستودع story — كل هدف يعادل أمر story.py المقابل
PY ?= python3
STORY := $(PY) tools/story.py
# الطبع: بيئة التبويب داخل المستودع (.venv، غير ملتقَطة في git — حجمُ بيئةٍ لا حجمُ عمل)
BOOKPY ?= $(CURDIR)/.venv/bin/python
FLAGS ?=
# المؤلِّفُ المكتوبُ في الطبعة المحفوظة في git؛ مرّر AUTHOR=… لتغييره.
#التخليفُ مقصود: `make check-full` يقارن بناءَه بالمحفوظ وسومًا وقياسًا.
AUTHOR ?= نجمة برهان

.PHONY: help lint strict index stats test check check-full new review setup book test-book qa

help:
	@echo "أهداف مستودع story:"
	@echo "  make lint            فحص الأعمال بقواعد AGENTS.md"
	@echo "  make strict          الفحص مع اعتبار التنبيهات أخطاء"
	@echo "  make review          فحص قواعد الأسلوب (bible/style.md) — صارم"
	@echo "  make index           توليد works/index.md"
	@echo "  make stats           إحصاءات موجزة"
	@echo "  make test            الاختبار الذاتي للأداة وحدها"
	@echo "  make check           كل البوابات النصية: lint · review · constraints · sweep · debts · self-test · contradictions"
	@echo "  make qa              تصديق book/edition/qa.json"
	@echo "  make test-book       فحص محرك الطبع (يتطلب: make setup)"
	@echo "  make check-full      check + محرك + طبعة كاملة في مؤقّت ومقارنةُ القياسات"
	@echo "  make setup           إنشاء .venv وتثبيت اعتماديات الطبع"
	@echo "  make book [AUTHOR=…] [FLAGS=--impose]   توليد PDF المتن والغلاف داخل book/edition"
	@echo "  make new SLUG=x [FROM=chapter]           إنشاء عمل جديد"

lint:
	@$(STORY) lint

review:
	@$(STORY) review --strict

strict:
	@$(STORY) lint --strict

index:
	@$(STORY) index

stats:
	@$(STORY) stats

test:
	@$(STORY) self-test

qa:
	@$(PY) tools/check_qa.py

check: lint review
	@$(STORY) constraints
	@$(STORY) sweep
	@$(STORY) debts --gate
	@$(STORY) self-test
	@$(STORY) index
	@$(STORY) check-contradictions

new:
	@test -n "$(SLUG)" || (echo "استعمل: make new SLUG=my-story [FROM=short-story|chapter|fragment]"; exit 2)
	@$(STORY) new $(SLUG) --from $(if $(FROM),$(FROM),short-story)

setup:
	@test -d .venv || $(PY) -m venv .venv
	./.venv/bin/pip install -q --disable-pip-version-check -r book/requirements.txt
	@echo "البيئة جاهزة: .venv — شغّل make book"

test-book:
	@test -x "$(BOOKPY)" || { echo "تنبيه: لا بيئة طبع — شغّل make setup أولًا"; exit 3; }
	"$(BOOKPY)" book/test_typeset.py

# إعادة البناء في مؤقّت ثم مقارنةُ القياسات بالمحفوظ: إن كسرَ محرّكٌ سطرًا
# بلا صرخة، تُخطئ هذه المقارنةُ لا العين.
check-full: check test-book
	@test -x "$(BOOKPY)" || { echo "تنبيه: لا بيئة طبع — شغّل make setup أولًا"; exit 3; }
	@rm -rf /tmp/story-rebuild && mkdir -p /tmp/story-rebuild
	"$(BOOKPY)" book/make_book.py $(if $(AUTHOR),--author "$(AUTHOR)",) --out /tmp/story-rebuild --dpi-preview 90 --impose > /dev/null
	@$(PY) tools/check_qa.py --a /tmp/story-rebuild/qa.json --b book/edition/qa.json

# FLAGS += --impose  → صفحات طابعة مزدوجة · FLAGS += --spine-mm 9 → كعبٌ متّسع
book:
	@test -x "$(BOOKPY)" || { echo "تنبيه: لا بيئة طبع — شغّل make setup أولًا"; exit 3; }
	"$(BOOKPY)" book/make_book.py $(if $(AUTHOR),--author "$(AUTHOR)",) $(FLAGS)
