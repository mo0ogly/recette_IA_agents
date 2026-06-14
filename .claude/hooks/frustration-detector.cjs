// frustration-detector.cjs — UserPromptSubmit hook
// Detects frustration patterns and injects context to go straight to the fix.
// Also detects "continue/finis" to skip summaries.

const chunks = [];
process.stdin.on('data', (c) => chunks.push(c));
process.stdin.on('end', () => {
  const raw = Buffer.concat(chunks).toString('utf8');
  const input = raw ? JSON.parse(raw) : {};
  const msg = (input.prompt || '');

  // Frustration patterns (FR + EN)
  const FRUSTRATION = /putain|merde|bordel|fait chier|ca marche pas|ça marche pas|c'est cass[eé]|encore cass[eé]|wtf|ffs|damn|broken again|still broken|doesn.t work|not working|why the (hell|fuck)/i;

  // "Continue/finish" patterns
  const CONTINUE = /^(continue|continues|finis|termine|finish|go on|keep going|next|suivant)\s*[.!]?$/i;

  if (FRUSTRATION.test(msg)) {
    process.stdout.write(
      'CONTEXTE: Le user est frustre. Va DROIT AU BUT. ' +
      'Pas de recap, pas de "je comprends", pas de blabla. ' +
      'Diagnostique le probleme et propose une correction concrete IMMEDIATEMENT. ' +
      'Si tu as besoin de lire un fichier ou lancer une commande, fais-le sans demander.'
    );
  } else if (CONTINUE.test(msg)) {
    process.stdout.write(
      'CONTEXTE: Le user veut que tu reprennes. ' +
      'Ne resume PAS ce qui a ete fait. Ne recapitule PAS. ' +
      'Reprends exactement la ou tu en etais et avance.'
    );
  }

  process.exit(0);
});
