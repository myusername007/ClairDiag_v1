#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# ClairDiag — CORE v2 migration script
# Запускай из корня ВТОРОГО проекта: bash migrate_to_v2.sh /path/to/clairdiag_v1
# ─────────────────────────────────────────────────────────────────────────────

set -e

SOURCE="${1:-../clairdiag_v1}"

if [ ! -d "$SOURCE" ]; then
  echo "❌ Источник не найден: $SOURCE"
  echo "   Использование: bash migrate_to_v2.sh /path/to/clairdiag_v1"
  exit 1
fi

echo "📁 Источник: $SOURCE"
echo "📁 Цель:     $(pwd)"
echo ""

# ─── КОММИТ 1: удаление app/logic ────────────────────────────────────────────
echo "▶ Commit 1: remove app/logic"

if [ -d "app/logic" ]; then
  git rm -r app/logic/
else
  echo "  app/logic не найден — пропускаем"
fi

git add -A
git diff --cached --quiet || git commit -m "refactor(core): remove app/logic monolith engine"

# ─── КОММИТ 2: data layer ────────────────────────────────────────────────────
echo "▶ Commit 2: data layer"

mkdir -p app/data
cp "$SOURCE/app/data/__init__.py"  app/data/__init__.py
cp "$SOURCE/app/data/symptoms.py"  app/data/symptoms.py
cp "$SOURCE/app/data/tests.py"     app/data/tests.py
touch app/__init__.py

git add app/__init__.py app/data/
git commit -m "feat(data): add data layer — symptoms dict, test catalog with diagnostic_value"

# ─── КОММИТ 3: schemas ───────────────────────────────────────────────────────
echo "▶ Commit 3: schemas"

mkdir -p app/models
cp "$SOURCE/app/models/__init__.py" app/models/__init__.py
cp "$SOURCE/app/models/schemas.py"  app/models/schemas.py

git add app/models/
git commit -m "feat(schemas): add onset, duration, emergency_flag, tcs_level, sgl_warnings"

# ─── КОММИТ 4: pipeline modules ──────────────────────────────────────────────
echo "▶ Commit 4: pipeline modules"

mkdir -p app/pipeline
cp "$SOURCE/app/pipeline/__init__.py"    app/pipeline/__init__.py
cp "$SOURCE/app/pipeline/orchestrator.py" app/pipeline/orchestrator.py
cp "$SOURCE/app/pipeline/nse.py"         app/pipeline/nse.py
cp "$SOURCE/app/pipeline/scm.py"         app/pipeline/scm.py
cp "$SOURCE/app/pipeline/rfe.py"         app/pipeline/rfe.py
cp "$SOURCE/app/pipeline/bpu.py"         app/pipeline/bpu.py
cp "$SOURCE/app/pipeline/rme.py"         app/pipeline/rme.py
cp "$SOURCE/app/pipeline/tce.py"         app/pipeline/tce.py
cp "$SOURCE/app/pipeline/cre.py"         app/pipeline/cre.py
cp "$SOURCE/app/pipeline/tcs.py"         app/pipeline/tcs.py
cp "$SOURCE/app/pipeline/lme.py"         app/pipeline/lme.py
cp "$SOURCE/app/pipeline/sgl.py"         app/pipeline/sgl.py

git add app/pipeline/
git commit -m "feat(pipeline): CORE v2 — 10-step modular pipeline

Steps (strict order):
  1. NSE — symptom parser + alias resolver
  2. SCM — compress to 5-12 key symptoms
  3. RFE — red flags before scoring
  4. BPU — probabilistic scoring + incoherence_score
  5. RME — risk level
  6. TCE — temporal logic (onset + duration)
  7. CRE — HAS-like medical rules
  8. TCS — thresholds + composite confidence
  9. LME — test selection by value/cost, max 3
 10. SGL — safety layer, incoherence engine"

# ─── КОММИТ 5: API layer ─────────────────────────────────────────────────────
echo "▶ Commit 5: API layer"

mkdir -p app/api
cp "$SOURCE/app/api/__init__.py" app/api/__init__.py
cp "$SOURCE/app/api/routes.py"   app/api/routes.py
cp "$SOURCE/app/main.py"         app/main.py

git add app/api/ app/main.py
git commit -m "feat(api): update routes + main for CORE v2 pipeline"

# ─── КОММИТ 6: composite confidence + incoherence engine ─────────────────────
echo "▶ Commit 6: composite confidence + incoherence engine"

# файлы уже скопированы в commit 4, этот коммит — только для истории
# если в SOURCE уже финальные версии bpu/tcs/sgl — они уже применены выше
git add -A
git diff --cached --quiet || git commit -m "feat(bpu+tcs+sgl): composite confidence + incoherence engine

bpu: return incoherence_score alongside probs
tcs: coverage(40%) + coherence(35%) + quality(25%), cap 0.55 on low data
sgl: drop confidence by incoherence_score thresholds (warn: 0.15, drop: 0.30)"

# ─── КОММИТ 7: frontend ──────────────────────────────────────────────────────
echo "▶ Commit 7: frontend"

mkdir -p frontend
cp "$SOURCE/frontend/index.html" frontend/index.html

git add frontend/
git commit -m "feat(frontend): CORE v2 UI — emergency banner, TCS badge, SGL warnings, onset/duration inputs"

# ─── КОММИТ 8: README ────────────────────────────────────────────────────────
echo "▶ Commit 8: README"

cp "$SOURCE/README.md" README.md

git add README.md
git commit -m "docs(readme): rewrite for CORE v2 — pipeline, composite confidence, incoherence engine"

# ─── PUSH ────────────────────────────────────────────────────────────────────
echo ""
echo "✅ Все коммиты применены. Пушим..."
git push origin master

echo ""
echo "🎉 Готово. Второй проект обновлён до CORE v2."
