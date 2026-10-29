#!/bin/sh
# Install the pre-commit hygiene hook. Run once after cloning.
set -e
cd "$(git rev-parse --show-toplevel)"
cat > .git/hooks/pre-commit <<'HOOK'
#!/bin/sh
exec python3 tools/hygiene_check.py
HOOK
chmod +x .git/hooks/pre-commit
echo "pre-commit hygiene hook installed"
