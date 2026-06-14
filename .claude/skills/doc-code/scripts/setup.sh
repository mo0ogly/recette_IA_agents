#!/bin/bash
# Setup script for doc-code skill dependencies
# Run: bash .claude/skills/doc-code/scripts/setup.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/../.venv"

echo "Setting up doc-code skill dependencies..."

# Create venv if not exists
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "Created virtual environment at $VENV_DIR"
fi

# Activate and install
source "$VENV_DIR/bin/activate"
pip install --quiet lxml python-docx python-pptx 2>/dev/null

echo "Dependencies installed:"
pip list 2>/dev/null | grep -iE "lxml|docx|pptx"
echo ""
echo "Setup complete. Scripts available:"
echo "  python3 $SCRIPT_DIR/doc_classifier.py  -- Metadata manager"
echo "  python3 $SCRIPT_DIR/doc_librarian.py   -- Documentation health"
echo "  python3 $SCRIPT_DIR/generate_mermaid.py -- Mermaid diagram generator"
echo "  python3 $SCRIPT_DIR/generate_word_doc.py -- Word document generator"
