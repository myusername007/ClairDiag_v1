#!/bin/sh
# ClairDiag — установка git hooks
# Запуск: sh install_hooks.sh

set -e

mkdir -p .githooks
cp pre-commit .githooks/pre-commit 2>/dev/null || true

# Установить hook в .git
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

echo "✓ pre-commit hook установлен"
echo "  Теперь каждый 'git commit' автоматически запускает тесты HP + SF"