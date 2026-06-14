#!/bin/bash
# Hook Stop : Anti-rationalization gate (inspire Trail of Bits)
# Detecte quand Claude pretend avoir termine sans preuves
# Exit 2 = bloque et force a continuer

INPUT=$(cat)
RESPONSE=$(echo "$INPUT" | jq -r '.stop_response // empty' 2>/dev/null)

if [ -z "$RESPONSE" ]; then
  exit 0
fi

# Patterns de rationalization (excuses sans preuve)
RATIONALIZATION_PATTERNS=(
  "je n'ai pas pu tester"
  "je n'ai pas pu verifier"
  "devrait fonctionner"
  "devrait etre correct"
  "should work"
  "should be correct"
  "I believe this"
  "I think this should"
  "il faudrait tester"
  "reste a verifier"
  "a tester manuellement"
  "je suppose que"
  "normalement ca"
  "en theorie"
)

for pattern in "${RATIONALIZATION_PATTERNS[@]}"; do
  if echo "$RESPONSE" | grep -qi "$pattern"; then
    echo "ANTI-RATIONALIZATION: Pattern detecte '$pattern'. Verifier AVANT de declarer termine. Executer le build/test et montrer le resultat." >&2
    exit 2
  fi
done

exit 0
