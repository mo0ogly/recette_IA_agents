Affiche l'historique des conversations Claude Code de ce projet avec des details distinctifs.

Par defaut affiche les 10 dernieres sessions. Accepte un argument optionnel pour le nombre de sessions ou un terme de recherche.

Argument: $ARGUMENTS (optionnel: nombre de sessions ex "20", ou terme de recherche ex "liaprobe")

Execute le script Python suivant pour analyser les fichiers JSONL de conversation:

```python
import json, os, glob, sys
from datetime import datetime, timedelta
from collections import Counter

project_dir = '/home/liadev/.claude/projects/-opt-lia-sec-dev'
files = sorted(glob.glob(f'{project_dir}/*.jsonl'), key=os.path.getmtime, reverse=True)

# Parse arguments
args = "$ARGUMENTS".strip()
limit = 10
search_term = None
if args:
    try:
        limit = int(args)
    except ValueError:
        search_term = args.lower()
        limit = 65  # search all

current_session = os.environ.get('CLAUDE_SESSION_ID', '')

def extract_session(filepath, brief=False):
    sid = os.path.basename(filepath).replace('.jsonl', '')
    size_kb = os.path.getsize(filepath) / 1024
    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
    ctime = None
    branch = None
    model = None
    version = None
    cwd = None

    user_msgs = []
    assistant_count = 0
    tool_names = Counter()
    skills_used = []
    is_continuation = False
    continuation_summary = None

    with open(filepath) as fh:
        for line in fh:
            try:
                d = json.loads(line)
                t = d.get('type', '')

                # System metadata
                if t == 'system' and not branch:
                    branch = d.get('gitBranch', '?')
                    version = d.get('version', '?')
                    cwd = d.get('cwd', '')
                    ts = d.get('timestamp')
                    if ts:
                        try:
                            ctime = datetime.fromisoformat(ts.replace('Z', '+00:00')).replace(tzinfo=None)
                        except:
                            pass

                # User messages
                elif t == 'user':
                    msg = d.get('message', {})
                    content = msg.get('content', '')
                    text = ''
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get('type') == 'text':
                                text = c['text']
                                break
                    elif isinstance(content, str):
                        text = content

                    if text and len(text.strip()) > 3:
                        # Check for continuation
                        if 'continued from a previous conversation' in text.lower():
                            is_continuation = True
                            # Extract summary snippet
                            idx = text.find('Summary:')
                            if idx > 0:
                                continuation_summary = text[idx+8:idx+200].strip()
                        else:
                            user_msgs.append(text.strip())

                # Assistant messages (tool usage)
                elif t == 'assistant':
                    assistant_count += 1
                    msg = d.get('message', {})
                    if not model and msg.get('model'):
                        model = msg['model']
                    content = msg.get('content', [])
                    if isinstance(content, list) and not brief:
                        for c in content:
                            if isinstance(c, dict) and c.get('type') == 'tool_use':
                                name = c.get('name', '')
                                if name and name not in ('Read', 'Write', 'Edit', 'Glob', 'Grep', 'Bash'):
                                    tool_names[name] += 1
                                # Detect skill usage
                                if name == 'Skill':
                                    inp = c.get('input', {})
                                    skill = inp.get('skillName', inp.get('skill_name', ''))
                                    if skill:
                                        skills_used.append(skill)

            except:
                pass

    return {
        'id': sid,
        'size_kb': size_kb,
        'created': ctime or mtime,
        'modified': mtime,
        'branch': branch,
        'model': model,
        'version': version,
        'user_count': len(user_msgs),
        'assistant_count': assistant_count,
        'user_msgs': user_msgs,
        'tools': tool_names,
        'skills': list(set(skills_used)),
        'is_continuation': is_continuation,
        'continuation_summary': continuation_summary,
        'is_current': sid == current_session,
    }

def format_duration(created, modified):
    delta = modified - created
    mins = int(delta.total_seconds() / 60)
    if mins < 60:
        return f'{mins}min'
    hours = mins // 60
    remaining = mins % 60
    if hours < 24:
        return f'{hours}h{remaining:02d}'
    days = hours // 24
    return f'{days}j {hours%24}h'

def format_size(kb):
    if kb < 1024:
        return f'{kb:.0f}KB'
    return f'{kb/1024:.1f}MB'

print('=' * 78)
print(f'  HISTORIQUE DES SESSIONS CLAUDE CODE  ({len(files)} sessions)')
print('=' * 78)

shown = 0
for filepath in files:
    if shown >= limit:
        break

    session = extract_session(filepath, brief=(search_term is not None))

    # Search filter
    if search_term:
        haystack = ' '.join(session['user_msgs'][:10]).lower()
        if search_term not in haystack and search_term not in session.get('branch', '').lower():
            continue

    shown += 1

    # Header line
    marker = ' [CURRENT]' if session['is_current'] else ''
    cont = ' [CONTINUATION]' if session['is_continuation'] else ''
    duration = format_duration(session['created'], session['modified'])

    print()
    print(f'  #{shown} {session["created"].strftime("%Y-%m-%d %H:%M")} -> {session["modified"].strftime("%H:%M")} ({duration}){marker}{cont}')
    print(f'  ID: {session["id"]}')
    print(f'  Branch: {session["branch"]} | Model: {session["model"] or "?"} | Size: {format_size(session["size_kb"])} | Msgs: {session["user_count"]}u/{session["assistant_count"]}a')

    # First user message (topic)
    if session['user_msgs']:
        first = session['user_msgs'][0].replace('\n', ' ')[:120]
        print(f'  Debut: {first}')

    # Key topics from messages (sample 3 distinct user msgs)
    if len(session['user_msgs']) > 2:
        samples = []
        step = max(1, len(session['user_msgs']) // 4)
        for i in range(1, len(session['user_msgs']), step):
            if i < len(session['user_msgs']) and len(samples) < 3:
                msg = session['user_msgs'][i].replace('\n', ' ')[:80]
                if msg not in samples and len(msg) > 10:
                    samples.append(msg)
        if samples:
            print(f'  Sujets: {" | ".join(samples)}')

    # Last user message
    if len(session['user_msgs']) > 1:
        last = session['user_msgs'][-1].replace('\n', ' ')[:100]
        print(f'  Dernier msg: {last}')

    # Skills & tools
    if session['skills']:
        print(f'  Skills: {", ".join(session["skills"])}')
    if session['tools']:
        top_tools = [f'{n}({c})' for n, c in session['tools'].most_common(5)]
        print(f'  Outils: {", ".join(top_tools)}')

    # Continuation summary
    if session['continuation_summary']:
        print(f'  Resume continuation: {session["continuation_summary"][:150]}')

    print(f'  {"─" * 74}')

if shown == 0 and search_term:
    print(f'\n  Aucune session trouvee pour "{search_term}"')

print()
print(f'  Tip: claude --resume <ID> pour reprendre une session')
print(f'  Tip: /history 20 pour voir plus | /history liaprobe pour chercher')
print()
```

Affiche le resultat du script. Ne rajoute pas de commentaire supplementaire sauf si l'utilisateur pose une question.
