# eBPF dans notre situation -- instrumentation defensive, lisibilite au niveau noyau

> Pourquoi une sonde eBPF dans un banc de recette d'agents IA, ce qu'elle observe
> reellement, et sous quel angle on l'utilise. Doc de fond (conceptuelle). Pour le
> how-to operationnel : [runbooks/ebpf-live-capture.md](runbooks/ebpf-live-capture.md).
> Pour la these "surface de detection" : [runbooks/surface-detection-recette.md](runbooks/surface-detection-recette.md).

## L'angle retenu (la reponse en une phrase)

On utilise eBPF en **instrumentation defensive** : une capture **read-only** des
syscalls et du trafic d'un agent, jamais un enforcement. Mais le choix est
**motive par l'analyse de la menace** : un agent (ou un attaquant qui le pilote)
peut contourner toute observation cooperative *in-process*. La seule surface
qu'il ne peut pas se contenter d'ignorer, c'est le noyau. eBPF est donc notre
filet de derniere instance pour la **lisibilite** -- le principe directeur du
repo : on ne recette que ce qu'on peut observer.

## Ce qu'est eBPF (rappel)

eBPF (extended Berkeley Packet Filter) execute du bytecode **sandboxe dans le
kernel space** sans recompiler le noyau ni charger un module classique. C'est une
VM in-kernel (jeu d'instructions RISC-like 64 bits, JIT) gardee par un
**verifier** qui valide statiquement le programme avant chargement : tous les
chemins analyses, terminaison garantie, pas d'acces memoire hors bornes. C'est ce
qui rend l'execution de code non privilegie dans le noyau acceptable -- en
theorie (cf. la mise en garde plus bas sur la surface du verifier).

Les points d'attache typiques : kprobes/uprobes (instrumentation dynamique),
**tracepoints** (points statiques stables fournis par le noyau), XDP (paquets des
le driver NIC), tc (ingress/egress), LSM/KRSI (enforcement de politiques). La
communication kernel <-> userspace passe par des **maps** (hash, array, ring
buffer, per-CPU...).

Nous n'utilisons qu'un sous-ensemble volontairement etroit : des **tracepoints**
(stables, pas de kprobe fragile) et des **ring buffers** (transport vers le
userspace). Pas de XDP, pas de tc, **pas de LSM** -- on observe, on ne bloque pas.

## Ce que notre sonde attache reellement

Le programme noyau (Rust `no_std` + aya, cible `bpfel-unknown-none`,
`discoveryprobe/discoveryprobe-ebpf/`) s'accroche a **cinq tracepoints** et pousse
chaque evenement dans un ring buffer de 256 KiB :

| Tracepoint | Evenement capture | Ce que ca prouve |
|------------|-------------------|------------------|
| `sched:sched_process_exec` | `ExecEvent` (pid, comm) | l'agent **tourne** -- visible meme dans un conteneur Docker (noyau partage) |
| `syscalls:sys_enter_connect` | `ConnectEvent` (pid, IPv4, port) | l'agent **dial** un endpoint sortant (ex. le provider LLM en HTTPS) sans hook in-process |
| `syscalls:sys_enter_openat` | `FileEvent` (pid, path) | la **surface fichiers** : ce que l'agent ouvre |
| `syscalls:sys_enter_sendto` | `DnsEvent` (pid, qname) | les **requetes DNS** (filtre dur UDP:53 avant parsing) |
| `sched:sched_process_fork` | `ForkEvent` (parent, child) | l'**arbre de processus** -- les agents multi-process ne sont pas un angle mort |

Les structs sont `#[repr(C)]` a taille fixe (`discoveryprobe-common`) pour un
parsing deterministe. Bornes verifier-friendly : `comm` 16 octets
(`TASK_COMM_LEN`), `path` 128, `qname` 256 (puissance de deux pour le masquage).
Le programme **droppe** sur ring plein -- il ne bloque jamais le processus
observe (capture passive).

Cote userspace, le loader (`discoveryprobe/src/probe.rs`) draine les ring buffers
sur une fenetre bornee, puis une fonction **pure** (`mapping.rs`) projette les
evenements en un `CaptureRecording` deterministe : une des quatre **surfaces
d'observation** du modele est `ebpf_wire` (les trois autres -- `hook_subprocess`,
`hook_mcp`, `hook_sdk` -- sont des hooks cooperatifs in-process).

## Le modele de privilege (verifier, CAP_BPF, fail-safe)

Charger/attacher un programme eBPF exige des capacites. Notre decoupage :

- Le **broker** (`discoveryprobe-broker`) est le SEUL composant privilegie. On lui
  accorde `cap_bpf,cap_perfmon,cap_net_admin,cap_dac_read_search` **une fois**
  (`./recette.sh probe-grant-caps`, file-caps via `setcap`), puis il tourne
  **sans sudo** par capture. CAP_BPF est separee de la root depuis le kernel 5.8 :
  on n'a pas besoin du root complet.
- L'**API** et la console sont **non privilegiees** : elles relaient vers le
  broker par une socket Unix locale en `0600`, deny-by-default. Le privilege ne
  remonte jamais dans le plan applicatif.
- L'audit du broker est **append-only** (JSONL + sha256 de la capture) -- piste
  forensique immuable (I1).

**Fail-safe (jamais de fausse capture).** S'il manque une piece (binaire broker,
objet eBPF, manifest, ou la capacite CAP_BPF), `cicd/platform.sh`
(`_probe_live_capable`) bascule automatiquement sur le **broker de replay**
non privilegie (Python, meme format de fil), et l'etat est marque `mode: replay`
de bout en bout. On ne **simule jamais** une capture live qu'on ne peut pas faire
(R13/R14) : un EPERM au chargement est logue, pas maquille.

**Determinisme (I4).** La capture live est non deterministe (le timing des
syscalls varie) ; la **projection** est pure (tri `BTreeMap`, dedup), donc le
`CaptureRecording` est byte-stable et le **meme juge** score live et replay a
l'identique. C'est ce qui rend la sonde rejouable et auditable.

## Le lien menace <-> defense (pourquoi le noyau)

Cote offensif, eBPF est une primitive de **rootkit** de premier ordre : des
familles comme BPFDoor ou Symbiote, des PoC type ebpfkit/TripleCross, l'utilisent
pour du traffic hiding, du hooking de syscalls et de la persistance -- le code
tourne en kernel et **intercepte/modifie** les appels avant qu'ils n'atteignent
le monitoring userspace (MITRE ATT&CK T1014 Rootkit, T1205 Traffic Signaling).

C'est exactement ce risque qui **justifie** notre capture au niveau noyau. Un
agent peut tres bien echapper a toute observation in-process -- ne charger aucun
SDK hooke, parler directement a une base, court-circuiter le proxy. Notre corpus
modelise ce cas : le **"ghost"** (`corpus/surface/ghost-direct-db`) est invisible
sur les trois surfaces de hook mais **visible sur `ebpf_wire`** (son syscall
`connect` est capture). La these de recette en decoule : *si l'outil ne voit pas
l'agent, c'est un echec* -- un sujet vu sur aucune surface
(`corpus/surface/_negative/vanished`) declenche la gate ROUGE. eBPF est la pour
attraper l'agent qui se cache des hooks.

Donc : **defensif par construction** (on observe, on ne bloque pas), **informe
par la menace** (on capture la ou un agent evasif ne peut pas mentir).

## Ce qu'on ne fait PAS (limites assumees)

- **Pas d'enforcement.** Aucun hook LSM/KRSI, aucun drop XDP/tc. La sonde ne
  modifie jamais l'etat d'un processus -- la gouvernance (allow/deny/escalate)
  reste dans le Control Plane applicatif (I2), pas dans le noyau.
- **Pas d'attribution cryptographique au niveau eBPF.** Le fil noyau porte un
  `comm`/PID, pas un `agent_id` signe ; l'identite forte vient des surfaces de
  hook et du proxy. La sonde **corrobore** ("cet agent a bien parle sur le fil"),
  elle n'authentifie pas.
- **La surface d'attaque du verifier existe.** Plusieurs CVE d'elevation de
  privileges ont exploite des failles d'inference de bornes du verifier, d'ou le
  durcissement (`unprivileged_bpf_disabled=1` par defaut sur la plupart des
  distros). On reste donc minimal : tracepoints stables, programme borne,
  privilege confine au seul broker.

## Distinction `ProxyTrace` vs `ebpf_wire`

Deux niveaux de lisibilite, complementaires :

- **`ProxyTrace`** (in-process, `recette/platform/proxy/`) : l'intention
  **mediatisee** -- `agent_id`, `action_type`, `target_system`, `request_payload`
  + `response`. Cooperatif, structure, identifie.
- **`ebpf_wire`** (noyau) : l'observation **non cooperative** -- exec, connect,
  openat, sendto, fork. Pas d'`agent_id`, mais voit ce qu'un agent evasif cache
  au proxy. C'est le niveau "ce qu'il FAIT vraiment" quand il ne veut pas le dire.

## Reperes dans le code

| Sujet | Chemin |
|-------|--------|
| Programmes noyau (tracepoints, maps) | `discoveryprobe/discoveryprobe-ebpf/src/main.rs` |
| Structs de fil kernel<->userspace | `discoveryprobe/discoveryprobe-common/src/lib.rs` |
| Loader + projection pure | `discoveryprobe/src/probe.rs`, `discoveryprobe/src/mapping.rs` |
| Broker privilegie (socket, audit) | `discoveryprobe/discoveryprobe-broker/` |
| Bascule live/replay (fail-safe) | `cicd/platform.sh` (`_probe_live_capable`, `probe_broker_start`) |
| Broker de replay non privilegie | `recette/platform/probe/replay_broker.py` |
| Manifest (allowlist comm_marker) | `recette/platform/probe/manifest_gen.py` |
| API (relai non privilegie) | `recette/api/routers/probe.py` (`/probe/status`, `/probe/capture`, ...) |
| Build / caps | `./recette.sh probe-ebpf-build`, `./recette.sh probe-grant-caps` |

## Voir aussi

- [runbooks/ebpf-live-capture.md](runbooks/ebpf-live-capture.md) -- lancer la capture live (CAP_BPF, end-to-end).
- [runbooks/surface-detection-recette.md](runbooks/surface-detection-recette.md) -- la these des 4 surfaces et la gate du "ghost".
- [ARCHITECTURE.md](ARCHITECTURE.md) -- le chemin gouverne complet (Control/Data/Audit).
- [migration-provenance.md](migration-provenance.md) -- provenance des offsets tracepoint (dump kernel, jamais fabriques).
