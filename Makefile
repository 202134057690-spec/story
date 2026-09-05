# اختصارات مستودع story — كل هدف يعادل أمر story.py المقابل
PY ?= python3
STORY := $(PY) tools/story.py

.PHONY: help lint strict index stats check test new review book

help:
	@echo "أهداف مستودع story:"
	@echo "  make lint            فحص الأعمال بقواعد AGENTS.md"
	@echo "  make strict          الفحص مع اعتبار التنبيهات أخطاء"
	@echo "  make review          فحص قواعد الأسلوب (bible/style.md)"
	@echo "  make index           توليد works/index.md"
	@echo "  make stats           إحصاءات موجزة"
	@echo "  make check           lint + review + index + self-test (استعمله قبل التسليم)"
	@echo "  make book            توليد PDF الغلاف والمتن (يتطلّب ~/.venv-book)")
	@echo "  make test            الاختبار الذاتي للأداة وحده"
	@echo "  make new SLUG=x [FROM=chapter]  إنشاء عمل جديد"

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

check: lint review test
	@$(STORY) index
	@$(STORY) check-contradictions

new:
	@test -n "$(SLUG)" || (echo "استعمل: make new SLUG=my-story [FROM=short-story|chapter|fragment]"; exit 2)
	@$(STORY) new $(SLUG) --from $(if $(FROM),$(FROM),short-story)

# الطبع: يستعمل بيئة التبويب إن وُجدت، وإلا يصرّح بالنقص بدل الصمت
BOOKPY ?= $(HOME)/.venv-book/bin/python
book:
	@test -x "$(BOOKPY)" || { echo "تنبيه: أنشئ بيئة التبويب أولًا (انظر book/README.md)"; exit 3; }
	"$(BOOKPY)" book/make_book.py $(if $(AUTHOR),--author "$(AUTHOR)",)
