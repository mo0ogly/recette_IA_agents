// secret-scanner.cjs — PreToolUse hook for Bash (git commit interception)
// Scans staged files for API keys, tokens, and private keys before commit.
// Returns exit 2 to block, exit 0 to allow.

const { execSync } = require('child_process');

const chunks = [];
process.stdin.on('data', (c) => chunks.push(c));
process.stdin.on('end', () => {
  const raw = Buffer.concat(chunks).toString('utf8');
  const input = raw ? JSON.parse(raw) : {};
  const cmd = (input.tool_input && input.tool_input.command) || '';

  // Only intercept git commit commands
  if (!/\bgit\s+commit\b/.test(cmd)) {
    process.exit(0);
    return;
  }

  // 18 secret patterns covering major providers
  const PATTERNS = [
    { name: 'Anthropic API Key',       regex: /sk-ant-api[0-9a-zA-Z_-]{20,}/g },
    { name: 'OpenAI API Key',          regex: /sk-[a-zA-Z0-9]{20,}/g },
    { name: 'AWS Access Key',          regex: /AKIA[0-9A-Z]{16}/g },
    { name: 'AWS Secret Key',          regex: /(?:aws_secret|secret_access)[_\s]*[:=]\s*["']?[A-Za-z0-9/+=]{40}/gi },
    { name: 'GitHub Token (classic)',   regex: /ghp_[A-Za-z0-9]{36,}/g },
    { name: 'GitHub Token (fine)',      regex: /github_pat_[A-Za-z0-9_]{22,}/g },
    { name: 'GitLab Token',            regex: /glpat-[A-Za-z0-9_-]{20,}/g },
    { name: 'Slack Bot Token',         regex: /xoxb-[0-9]{10,}-[0-9]{10,}-[A-Za-z0-9]{24,}/g },
    { name: 'Slack Webhook',           regex: /hooks\.slack\.com\/services\/T[A-Z0-9]{8,}\/B[A-Z0-9]{8,}\/[A-Za-z0-9]{24,}/g },
    { name: 'Stripe Secret Key',       regex: /sk_live_[A-Za-z0-9]{24,}/g },
    { name: 'Stripe Restricted Key',   regex: /rk_live_[A-Za-z0-9]{24,}/g },
    { name: 'Google API Key',          regex: /AIza[0-9A-Za-z_-]{35}/g },
    { name: 'Google OAuth Secret',     regex: /GOCSPX-[A-Za-z0-9_-]{28,}/g },
    { name: 'JWT Token',               regex: /eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g },
    { name: 'RSA Private Key',         regex: /-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----/g },
    { name: 'Azure Subscription Key',  regex: /[a-f0-9]{32}/g }, // too broad alone, checked only with context
    { name: 'SendGrid API Key',        regex: /SG\.[A-Za-z0-9_-]{22,}\.[A-Za-z0-9_-]{43,}/g },
    { name: 'Twilio Auth Token',       regex: /(?:twilio|auth_token)[_\s]*[:=]\s*["']?[a-f0-9]{32}/gi },
  ];

  // Skip Azure pattern (too broad) — only check the other 17
  const ACTIVE_PATTERNS = PATTERNS.filter(p => p.name !== 'Azure Subscription Key');

  let diff = '';
  try {
    diff = execSync('git diff --cached --diff-filter=ACMR -U0', {
      encoding: 'utf8',
      timeout: 10000,
      stdio: ['pipe', 'pipe', 'pipe']
    });
  } catch (_) {
    // No staged changes or not in a git repo — allow
    process.exit(0);
    return;
  }

  if (!diff) {
    process.exit(0);
    return;
  }

  // Only scan added lines (lines starting with +, excluding +++ headers)
  const addedLines = diff
    .split('\n')
    .filter(l => l.startsWith('+') && !l.startsWith('+++'));

  const findings = [];

  for (const line of addedLines) {
    for (const pattern of ACTIVE_PATTERNS) {
      pattern.regex.lastIndex = 0;
      if (pattern.regex.test(line)) {
        // Avoid false positives: skip if line is a comment or documentation
        const trimmed = line.slice(1).trim();
        const isComment = /^(\/\/|#|<!--|\*|\/\*|\{\/\*)/.test(trimmed);
        // Still flag it but mark as potential false positive
        findings.push({
          type: pattern.name,
          preview: line.slice(1, 80).trim(),
          isComment
        });
      }
    }
  }

  if (findings.length === 0) {
    process.exit(0);
    return;
  }

  // Build report
  const real = findings.filter(f => !f.isComment);
  const comments = findings.filter(f => f.isComment);

  let msg = 'SECRET SCANNER: Secrets potentiels detectes dans les fichiers stages.\n\n';

  if (real.length > 0) {
    msg += 'BLOQUANT (' + real.length + '):\n';
    for (const f of real) {
      msg += '  [' + f.type + '] ' + f.preview + '\n';
    }
  }

  if (comments.length > 0) {
    msg += '\nDANS COMMENTAIRES (' + comments.length + ') — faux positif probable:\n';
    for (const f of comments) {
      msg += '  [' + f.type + '] ' + f.preview + '\n';
    }
  }

  if (real.length > 0) {
    msg += '\nCommit BLOQUE. Retirez les secrets des fichiers stages avant de committer.';
    process.stderr.write(msg);
    process.exit(2);
  } else {
    // Only comments — warn but allow
    msg += '\nAttention: patterns dans des commentaires. Commit autorise.';
    process.stdout.write(msg);
    process.exit(0);
  }
});
