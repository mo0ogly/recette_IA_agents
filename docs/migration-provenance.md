# Provenance de migration -- ce qui a ete repris des repos sources (verifiable)

> Preuve que la couche de capture adapte du VRAI code issu des repos upstream (lu via
> `gh api`), pas du code invente. Chaque ligne cite un symbole/chemin upstream verifiable
> et le code local qui l'adapte. Distinction honnete : le PATTERN et le JEU DE CHAMPS
> sont reutilises ; la COUCHE et le STORE sont reimplantes dans les coutures propres a ce
> projet (le code upstream ne s'integre pas tel quel car il vise une couche/un runtime
> different).
> Licences : agentwatch Apache-2.0, agenttrace MIT (voir NOTICE).

## cyberark/agentwatch (Apache-2.0) -- le MECANISME de hook

Source lue : `src/agentwatch/hooks/base.py`, `src/agentwatch/llm/models.py`,
`src/agentwatch/hooks/http/*`.

| Upstream (symbole reel) | Adaptation locale | Reutilise vs adapte |
|------------------------|------------------|----------------|
| `BaseHook.apply_hook()` / `should_intercept(*args)` (`hooks/base.py`) | `CapturingLlm` enveloppe un `LlmBackend` ; l'enveloppe EST le hook applique, `should_intercept` est implicite (chaque `decide()`) | PATTERN reutilise |
| `HookCallbackProto.on_hook_callback(hook, obj)` (`hooks/base.py`) | `CapturingLlm(sink=...)` -- le callback sink recevant chaque `LlmCallTrace` | PATTERN reutilise |
| modeles wire LLM `ToolUse` / `Message` / `Tool` (`llm/models.py`) | `LlmCallTrace.intent = {tool}:{resource}` capture depuis l'appel d'outil de la decision | FORME DE DONNEES reutilisee |
| `hooks/http/httpcore_hook.py` (interception a la couche **httpcore/HTTP**) | NON utilise au niveau httpcore : on hooke la couture `LlmBackend.decide()` (on en est proprietaire). Dans notre stack, l'interception du transport HTTP EST la surface wire (eBPF `discoveryprobe` / `ProxyTrace`) | COUCHE ADAPTEE (deliberement) |

Enonce honnete : agentwatch intercepte le transport HTTP (httpcore) et parse les
formats wire des providers. Nous ne repliquons pas le hooking httpcore in-process ;
nous enveloppons l'interface `LlmBackend` de plus haut niveau. Le MECANISME (objet hook
+ callback sink + capture de l'intention de l'appel d'outil) est fidelement reutilise ;
la COUCHE differe par conception (sync-first vers notre idiome `CachingLlm` existant).

## tensorstax/agenttrace (MIT) -- le SCHEMA de trace

Source lue : `src/agenttrace/agenttrace.py`.

| Upstream (symbole reel) | Adaptation locale | Reutilise vs adapte |
|------------------------|------------------|----------------|
| `TraceManager._log_trace_end(func_name, session_id, duration_ms, success)` | `LlmCallTrace{intent (~func_name), agent_id/run_id (~session_id), latency_ms (~duration_ms), error (~not success)}` | JEU DE CHAMPS reutilise |
| colonnes de la table `traces` `id, trace_type, timestamp, ...` (`CREATE TABLE traces`) | `LlmCallTrace{seq/event_id, kind (~trace_type)}` + champs ops | JEU DE CHAMPS reutilise |
| `TraceManager` SQLite `traces.db` + `save_traces` | NON utilise : reimplante dans `CaptureStore` (ring borne) + le log d'audit (verite I1) -- pas de SQLite parallele | STORE REIMPLANTE |
| decorateur `@tracer.trace()` | NON utilise : l'enveloppe est le wrapper `LlmBackend`, pas un decorateur par fonction | MECANISME ADAPTE |

Enonce honnete : agenttrace persiste dans son propre SQLite et decore des fonctions.
Nous reutilisons son JEU DE CHAMPS enrichi par appel (intent + duration/latency +
success/error + session/run) mais stockons dans les coutures capture/audit existantes
de ce projet, pas une base de donnees parallele.

## Verifiez-le vous-meme

```
gh api repos/cyberark/agentwatch/contents/src/agentwatch/hooks/base.py --jq '.content' | base64 -d
gh api repos/tensorstax/agenttrace/contents/src/agenttrace/agenttrace.py --jq '.content' | base64 -d
```
Comparez avec `recette/capture/capturing_llm.py` et `recette/capture/llm_trace.py`.

## Parties Rust (skill different)

La surface wire eBPF native (`discoveryprobe/`) est en Rust, construite sous le skill
`rust-best-practices` (borrowing idiomatique, clippy `-D warnings`, fmt). Le schema de
trace + le sink (`discoveryprobe-capture`, GR1-GR3) migrent le JEU DE CHAMPS d'agenttrace
et le MECANISME de callback d'agentwatch (voir les tables ci-dessus) vers Rust.
Voir `docs/plans/2026-06-16-discoveryprobe-ebpf-reference-probe-design.md`.

### GR4 -- observation d'egress agentwatch, relocalisee dans le noyau

agentwatch observe le trafic LLM d'un agent IN-PROCESS a la couche de transport
`httpcore`/HTTP (`BaseHook` au-dessus du client HTTP). Le programme connect eBPF
(`discoveryprobe-ebpf::discoveryprobe_connect`) observe le MEME egress -- l'appel TCP
sortant de l'agent vers le provider -- mais au NOYAU
(`syscalls:sys_enter_connect`), donc il n'a besoin d'AUCUNE cooperation de l'agent et
attrape un fantome aveugle au hook.

| Upstream (mecanisme reel) | Adaptation locale | Reutilise vs adapte |
|---------------------------|------------------|----------------|
| agentwatch `BaseHook` au-dessus du transport HTTP `httpcore` (observation d'egress in-process) | `discoveryprobe_connect` lit le `sockaddr_in` du `connect(2)` au noyau -> `ConnectEvent{daddr:dport}` | POINT D'OBSERVATION relocalise (httpcore in-process -> syscall noyau) |
| agentwatch voit host+port depuis la requete HTTP | le noyau voit la destination `a.b.c.d:port` depuis le socket | MEME signal, couche differente |

Il s'agit d'une ADAPTATION de l'ENDROIT ou agentwatch observe (couche relocalisee pour
une capture sans cooperation), pas d'un portage ligne a ligne de son Python. L'ABI du
tracepoint syscall utilisee (`uservaddr` a l'offset 24 ; `sockaddr_in` `sin_family`@0 /
`sin_port`@2 BE / `sin_addr`@4 BE ; `AF_INET=2`) est le format syscall-enter stable de
Linux, recoupe avec le fichier `format` du tracepoint noyau (root-gated) et des
references publiques ; jamais invente (R13).

Compile-verifie : la crate eBPF construit un vrai objet `Linux BPF` portant les deux
programmes tracepoint + les deux maps (readelf). L'attach/capture en live necessite
CAP_BPF (le broker) et n'est PAS prouve hors d'une execution privilegiee (frontiere R14).
