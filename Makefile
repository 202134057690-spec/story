# اختصارات مستودع story — كل هدف يعادل أمر story.py المقابل
PY ?= python3
STORY := $(PY) tools/story.py

.PHONY: help lint strict index stats check test new clean-preview

help:
	@echo "أهداف مستودع story:"
	@echo "  make lint            فحص الأعمال بقواعد AGENTS.md"
	@echo "  make strict          الفحص مع اعتبار التنبيهات أخطاء"
	@echo "  make index           توليد works/index.md"
	@echo "  make stats           إحصاءات موجزة"
	@echo "  make check           lint + index + self-test (استعمله قبل التسليم)"
	@echo "  make test            الاختبار الذاتي للأداة وحده"
	@echo "  make new SLUG=x [FROM=chapter]  إنشاء عمل جديد"

lint:
	@$(STORY) lint

strict:
	@$(STORY) lint --strict

index:
	@$(STORY) index

stats:
	@$(STORY) stats

test:
	@$(STORY) self-test

check: lint test
	@$(STORY) index
	@$(STORY) check-contradictions

new:
	@test -n "$(SLUG)" || (echo "استعمل: make new SLUG=my-story [FROM=short-story|chapter|fragment]"; exit 2)
	@$(STORY) new $(SLUG) --from $(if $(FROM),$(FROM),short-story)
