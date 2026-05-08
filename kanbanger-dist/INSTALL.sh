#!/bin/bash
# Kanbanger Installation Script for Spec_Engine

echo "================================================"
echo "  Kanbanger Spec_Engine Integration Installer"
echo "================================================"
echo ""

# Check if we're in Spec_Engine project
if [ ! -d "SPECs" ]; then
    echo "[ERROR] SPECs directory not found"
    echo ""
    echo "This doesn't appear to be a Spec_Engine project."
    echo ""
    echo "Please run this script from your Spec_Engine project root:"
    echo "  cd /path/to/Spec_Engine"
    echo "  bash /path/to/kanbanger-dist/INSTALL.sh"
    echo ""
    exit 1
fi

echo "[OK] Spec_Engine project detected"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Install kanbanger
echo "Step 1: Installing kanbanger..."
pip install -e "$SCRIPT_DIR"
if [ $? -ne 0 ]; then
    echo "[ERROR] Installation failed"
    exit 1
fi
echo "[OK] Kanbanger installed"
echo ""

# Run integration setup
echo "Step 2: Running integration setup..."
python "$SCRIPT_DIR/spec_engine_integration.py"
if [ $? -ne 0 ]; then
    echo "[ERROR] Integration setup failed"
    exit 1
fi

# Install git hooks
echo ""
echo "Step 3: Installing git hooks..."
if [ -d ".git" ]; then
    bash "$SCRIPT_DIR/git-hooks/install-hooks.sh"
    echo "[OK] Git hooks installed"
else
    echo "[SKIP] Not a git repository - skipping git hooks"
    echo "       (Run 'bash $SCRIPT_DIR/git-hooks/install-hooks.sh' later if needed)"
fi

# Install Cursor AI rules
echo ""
echo "Step 4: Installing Cursor AI rules..."
if [ ! -d ".cursor/rules/project_management" ]; then
    mkdir -p ".cursor/rules/project_management"
fi
cp "$SCRIPT_DIR/.cursor/rules/project_management/kanbanger.mdc" ".cursor/rules/project_management/kanbanger.mdc"
echo "[OK] Cursor AI rules installed"

echo ""
echo "================================================"
echo "  Installation Complete!"
echo "================================================"
echo ""
echo "What was created:"
echo "  - .env.example (configuration template)"
echo "  - .gitignore (updated with kanbanger entries)"
echo "  - spec-to-kanban.py (SPEC → kanban converter)"
echo "  - sync-all-specs.sh (sync all kanbans)"
echo "  - KANBANGER_INTEGRATION.md (usage guide)"
echo "  - .git/hooks/pre-commit (enforce kanban sync)"
echo "  - .git/hooks/post-commit (auto-sync after commits)"
echo "  - .cursor/rules/project_management/kanbanger.mdc (AI enforcement)"
echo ""
echo "Next steps:"
echo "  1. cp .env.example .env"
echo "  2. Edit .env with your GitHub token"
echo "  3. kanban-sync-setup"
echo "  4. python spec-to-kanban.py SPECs/your_project/spec_your_project.md"
echo "  5. kanban-sync SPECs/your_project/_kanban.md"
echo ""
echo "Three layers of enforcement now active:"
echo "  - Git hooks: Enforce kanban sync at commit time"
echo "  - Cursor AI: Forces LLM to reference _kanban.md in plans"
echo "  - Documentation: LLM_GUIDANCE.md teaches proper usage"
echo ""
echo "Read KANBANGER_INTEGRATION.md for detailed instructions."
echo ""
