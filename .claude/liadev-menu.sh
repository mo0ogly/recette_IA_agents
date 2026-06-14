#!/bin/bash
# LIA-SEC Claude Code Launcher v3
# Step 1: Permission mode (only for options that launch Claude)
# Step 2: Session type with all useful options

LIADEV_HOME="/opt/lia-sec/dev"
LIADEV_USER="liadev"

C_RESET="\033[0m"; C_CYAN="\033[36m"; C_GREEN="\033[32m"; C_YELLOW="\033[33m"
C_RED="\033[31m"; C_WHITE="\033[1;37m"; C_DIM="\033[2m"; C_BOLD="\033[1m"

show_menu() {
    clear
    echo -e "${C_CYAN}================================================================${C_RESET}"
    echo -e "${C_WHITE}  LIA-SEC Platform - Claude Code${C_RESET}"
    echo -e "${C_DIM}  $(hostname) | $(date '+%Y-%m-%d %H:%M') | /opt/lia-sec/dev${C_RESET}"
    echo -e "${C_CYAN}================================================================${C_RESET}"
    echo ""
    echo -e "  ${C_WHITE}Claude Sessions${C_RESET}"
    echo -e "  ${C_GREEN}1${C_RESET})  New session"
    echo -e "  ${C_GREEN}2${C_RESET})  Browse previous sessions ${C_DIM}(interactive picker)${C_RESET}"
    echo -e "  ${C_GREEN}3${C_RESET})  Continue last session ${C_DIM}(--continue)${C_RESET}"
    echo -e "  ${C_GREEN}4${C_RESET})  Continue + send message"
    echo -e "  ${C_GREEN}5${C_RESET})  From prompt file ${C_DIM}(_alire/05_NOTES/prompts/)${C_RESET}"
    echo ""
    echo -e "  ${C_WHITE}Advanced${C_RESET}"
    echo -e "  ${C_GREEN}6${C_RESET})  New session + model ${C_DIM}(opus/sonnet/haiku)${C_RESET}"
    echo -e "  ${C_GREEN}7${C_RESET})  New session + agent ${C_DIM}(custom agent)${C_RESET}"
    echo -e "  ${C_GREEN}8${C_RESET})  New session + name ${C_DIM}(named session)${C_RESET}"
    echo -e "  ${C_GREEN}9${C_RESET})  New session + effort ${C_DIM}(low/medium/high/max)${C_RESET}"
    echo ""
    echo -e "  ${C_YELLOW}Tools${C_RESET}"
    echo -e "  ${C_YELLOW}s${C_RESET})  Services status"
    echo -e "  ${C_YELLOW}g${C_RESET})  Git log"
    echo -e "  ${C_YELLOW}b${C_RESET})  Build frontend + deploy"
    echo -e "  ${C_YELLOW}d${C_RESET})  PostgreSQL shell"
    echo -e "  ${C_YELLOW}l${C_RESET})  Backend logs ${C_DIM}(journalctl)${C_RESET}"
    echo -e "  ${C_RED}c${C_RESET})  Clean orphan sessions ${C_DIM}(claude orphelins + bash poll-loops + greps runaway + zombies)${C_RESET}"
    echo -e "  ${C_YELLOW}a${C_RESET})  Audit CPU / Load / RAM ${C_DIM}(top consommateurs + zombies)${C_RESET}"
    echo -e "  ${C_RED}k${C_RESET})  Kill stuck pg_dump ${C_DIM}(>1h = backup termine non sorti)${C_RESET}"
    echo ""
    echo -e "  ${C_DIM}0) Shell    q) Exit${C_RESET}"
    echo ""
    echo -e "${C_CYAN}================================================================${C_RESET}"
    read -p "  Choice [1]: " choice
    echo ""
}

# Ask permission mode (only for Claude launches)
ask_mode() {
    echo -e "  ${C_GREEN}a${C_RESET}) ${C_BOLD}Autonomous${C_RESET} ${C_DIM}(--dangerously-skip-permissions)${C_RESET}"
    echo -e "  ${C_YELLOW}i${C_RESET}) ${C_BOLD}Interactive${C_RESET} ${C_DIM}(approve each call)${C_RESET}"
    read -p "  Mode [a]: " pmode
    pmode=${pmode:-a}
    if [ "$pmode" = "a" ]; then
        CC_FLAGS="--dangerously-skip-permissions"
    else
        CC_FLAGS=""
    fi
}

run_claude() {
    local extra_flags="$1"
    # script -qec allocates a real PTY (isatty=true) required for Claude TUI
    # Without it, su/sudo don't pass TTY and Claude shows no input prompt
    exec script -qec "su - $LIADEV_USER -c 'cd $LIADEV_HOME && claude $CC_FLAGS $extra_flags'" /dev/null
}

show_menu
choice=${choice:-1}

case "$choice" in
    1)
        ask_mode
        run_claude ""
        ;;
    2)
        ask_mode
        run_claude "--resume"
        ;;
    3)
        ask_mode
        run_claude "--continue"
        ;;
    4)
        ask_mode
        read -p "  Message: " msg
        run_claude "--continue \"$msg\""
        ;;
    5)
        ask_mode
        PROMPTS_DIR="$LIADEV_HOME/_alire/05_NOTES/prompts"
        if [ -d "$PROMPTS_DIR" ]; then
            files=()
            i=1
            for f in "$PROMPTS_DIR"/*.md; do
                [ -f "$f" ] || continue
                echo -e "  ${C_GREEN}${i}${C_RESET}) $(basename "$f")"
                files+=("$f")
                ((i++))
            done
            [ ${#files[@]} -eq 0 ] && echo "  No prompts found." && exit 1
            read -p "  File [1]: " fnum
            fnum=${fnum:-1}
            idx=$((fnum - 1))
            if [ $idx -ge 0 ] && [ $idx -lt ${#files[@]} ]; then
                selected="${files[$idx]}"
                echo -e "\n${C_GREEN}Loading $(basename "$selected")...${C_RESET}\n"
                su - $LIADEV_USER -c "cd $LIADEV_HOME && claude $CC_FLAGS -p \"\$(cat '$selected')\""
            fi
        else
            echo "  $PROMPTS_DIR not found"
        fi
        ;;
    6)
        ask_mode
        echo -e "  ${C_GREEN}1${C_RESET}) opus  ${C_GREEN}2${C_RESET}) sonnet  ${C_GREEN}3${C_RESET}) haiku"
        read -p "  Model [1]: " m
        case "${m:-1}" in
            1) model="opus" ;; 2) model="sonnet" ;; 3) model="haiku" ;; *) model="opus" ;;
        esac
        run_claude "--model $model"
        ;;
    7)
        ask_mode
        # List available agents
        echo -e "  ${C_DIM}Available agents:${C_RESET}"
        for a in $LIADEV_HOME/.claude/agents/*.md; do
            [ -f "$a" ] && echo -e "  - $(basename "$a" .md)"
        done
        read -p "  Agent name: " agent
        [ -n "$agent" ] && run_claude "--agent $agent"
        ;;
    8)
        ask_mode
        read -p "  Session name: " sname
        [ -n "$sname" ] && run_claude "--name \"$sname\""
        ;;
    9)
        ask_mode
        echo -e "  ${C_GREEN}1${C_RESET}) low  ${C_GREEN}2${C_RESET}) medium  ${C_GREEN}3${C_RESET}) high  ${C_GREEN}4${C_RESET}) max"
        read -p "  Effort [3]: " e
        case "${e:-3}" in
            1) effort="low" ;; 2) effort="medium" ;; 3) effort="high" ;; 4) effort="max" ;; *) effort="high" ;;
        esac
        run_claude "--effort $effort"
        ;;
    s|S)
        cd $LIADEV_HOME && ./cleanup_services.sh status
        read -p "  Enter..." _ && exec "$0"
        ;;
    g|G)
        cd $LIADEV_HOME && git log --oneline -15
        echo "" && git status --short | head -10
        read -p "  Enter..." _ && exec "$0"
        ;;
    b|B)
        echo -e "${C_YELLOW}Building...${C_RESET}"
        cd $LIADEV_HOME/sigma-react-frontend && npm run build 2>&1 | tail -5
        rsync -a --delete build/ /opt/lia-sec/source/sigma-react-frontend/build/
        systemctl reload nginx
        echo -e "${C_GREEN}Deployed.${C_RESET}"
        read -p "  Enter..." _ && exec "$0"
        ;;
    d|D)
        sudo -u postgres psql -d lia_scan
        exec "$0"
        ;;
    l|L)
        journalctl -u lia-backend --no-pager -n 30
        read -p "  Enter..." _ && exec "$0"
        ;;
    c|C)
        echo ""
        echo -e "${C_WHITE}Memoire avant nettoyage${C_RESET}"
        free -h | awk 'NR==2 {printf "  Utilisee: %s / %s  Disponible: %s\n", $3, $2, $7}'
        echo ""
        # Find orphan claude processes:
        #  - owned by liadev
        #  - command starts with "claude" (top-level CLI, not child MCPs)
        #  - ancestor chain contains NO live sshd (real orphan = SSH disconnected)
        #  - NOT a descendant of this menu's shell (preserves active session)
        # Previous filter used ps START column switching HH:MM<->Mon, which
        # missed same-day orphans entirely.
        MY_PID=$$
        pids=$(ps -eo pid,user,comm --no-headers | awk -v user="$LIADEV_USER" -v me="$MY_PID" '
            $2==user && $3=="claude" && $1 != me {print $1}
        ' | while read -r pid; do
            chain=$(pstree -sp "$pid" 2>/dev/null)
            # Skip if descendant of running menu
            if echo "$chain" | grep -q "($MY_PID)"; then
                continue
            fi
            # Real orphan: ancestor chain has no live sshd
            if ! echo "$chain" | grep -qE "sshd\([0-9]+\)"; then
                echo "$pid"
            fi
        done)
        if [[ -z "$pids" ]]; then
            echo -e "${C_GREEN}Aucun processus orphelin trouve.${C_RESET}"
        else
            echo "$pids" | xargs kill -9 2>/dev/null || true
            killed=$(echo "$pids" | wc -w)
            echo -e "${C_GREEN}${killed} processus tues.${C_RESET}"
        fi
        # Surgical pass: bash poll-loops (comm=bash, PPID=1) + runaway recursive
        # scans (comm masked as claude.exe by the sandbox) + zombies report.
        # The claude-comm filter above never matches these classes.
        echo ""
        echo -e "${C_WHITE}Orphelins bash poll-loops + scans runaway${C_RESET}"
        if [ -x "$LIADEV_HOME/scripts/clean_claude_orphans.sh" ]; then
            "$LIADEV_HOME/scripts/clean_claude_orphans.sh" --apply 2>/dev/null | \
                grep -E 'killed|Killed|No orphan|zombie|Zombies' | sed 's/^/  /' || \
                echo -e "  ${C_GREEN}Rien a nettoyer${C_RESET}"
        else
            echo -e "  ${C_DIM}(scripts/clean_claude_orphans.sh absent)${C_RESET}"
        fi
        sleep 1
        echo ""
        echo -e "${C_WHITE}Memoire apres nettoyage${C_RESET}"
        free -h | awk 'NR==2 {printf "  Utilisee: %s / %s  Disponible: %s\n", $3, $2, $7}'
        echo ""
        read -p "  Enter..." _ && exec "$0"
        ;;
    a|A)
        echo ""
        echo -e "${C_CYAN}================================================================${C_RESET}"
        echo -e "${C_WHITE}  Audit CPU / Load / RAM${C_RESET}"
        echo -e "${C_CYAN}================================================================${C_RESET}"
        echo ""
        echo -e "${C_WHITE}# Uptime & load${C_RESET}"
        uptime
        ncpu=$(nproc)
        load1=$(awk '{print $1}' /proc/loadavg)
        ratio=$(awk -v l="$load1" -v c="$ncpu" 'BEGIN{printf "%.2f", l/c}')
        if awk -v r="$ratio" 'BEGIN{exit !(r>1.5)}'; then
            verdict="${C_RED}SATURE${C_RESET} (load/cpu = ${ratio}x)"
        elif awk -v r="$ratio" 'BEGIN{exit !(r>0.8)}'; then
            verdict="${C_YELLOW}CHARGE${C_RESET} (load/cpu = ${ratio}x)"
        else
            verdict="${C_GREEN}OK${C_RESET} (load/cpu = ${ratio}x)"
        fi
        echo -e "  CPUs: ${ncpu}  load1: ${load1}  -> ${verdict}"
        echo ""
        echo -e "${C_WHITE}# Memoire${C_RESET}"
        free -h | awk 'NR==1 {print "  "$0} NR==2 || NR==3 {print "  "$0}'
        echo ""
        echo -e "${C_WHITE}# Disque /${C_RESET}"
        df -h / | awk 'NR==1 {print "  "$0} NR==2 {print "  "$0}'
        echo ""
        echo -e "${C_WHITE}# Top 10 CPU${C_RESET}"
        ps -eo pid,user,pcpu,pmem,etime,comm --sort=-pcpu --no-headers | head -10 | \
            awk '{printf "  %-8s %-10s %5s%% %5s%% %12s  %s\n", $1, $2, $3, $4, $5, $6}'
        echo ""
        echo -e "${C_WHITE}# Top 10 RAM${C_RESET}"
        ps -eo pid,user,pcpu,pmem,rss,comm --sort=-rss --no-headers | head -10 | \
            awk '{printf "  %-8s %-10s %5s%% %5s%% %10s KB  %s\n", $1, $2, $3, $4, $5, $6}'
        echo ""
        echo -e "${C_WHITE}# Sessions Claude actives${C_RESET}"
        nclaude=$(ps -eo user,comm --no-headers | awk -v u="$LIADEV_USER" '$1==u && $2=="claude"' | wc -l)
        echo -e "  ${nclaude} session(s) claude actives"
        ps -eo pid,etime,pcpu,pmem,user,comm --no-headers | awk -v u="$LIADEV_USER" '$5==u && $6=="claude" {printf "  pid=%-8s age=%-12s cpu=%5s%% ram=%5s%%\n", $1, $2, $3, $4}'
        echo ""
        echo -e "${C_WHITE}# Backups PostgreSQL en cours (>1h = anomalie)${C_RESET}"
        long_dumps=$(ps -eo pid,etime,comm --no-headers | awk '$3 ~ /^pg_dump$/ {print $1, $2}')
        if [ -z "$long_dumps" ]; then
            echo -e "  ${C_GREEN}Aucun pg_dump actif${C_RESET}"
        else
            echo "$long_dumps" | while read -r pid age; do
                hours=$(echo "$age" | awk -F: '{ if (NF==3) print $1; else print 0 }')
                if [ "${hours:-0}" -ge 1 ] 2>/dev/null; then
                    echo -e "  ${C_RED}pid=$pid age=$age (suspect)${C_RESET}"
                else
                    echo -e "  ${C_GREEN}pid=$pid age=$age${C_RESET}"
                fi
            done
        fi
        echo ""
        echo -e "${C_WHITE}# Zombies${C_RESET}"
        nzombie=$(ps -eo stat --no-headers | awk '/^Z/' | wc -l)
        if [ "$nzombie" -gt 0 ]; then
            echo -e "  ${C_RED}${nzombie} zombie(s)${C_RESET}"
            ps -eo pid,ppid,stat,comm --no-headers | awk '/^[ ]*[0-9]+[ ]+[0-9]+[ ]+Z/' | head -5 | sed 's/^/  /'
        else
            echo -e "  ${C_GREEN}Aucun zombie${C_RESET}"
        fi
        echo ""
        echo -e "${C_CYAN}================================================================${C_RESET}"
        read -p "  Enter..." _ && exec "$0"
        ;;
    k|K)
        echo ""
        echo -e "${C_WHITE}# pg_dump stuck (>1h)${C_RESET}"
        # Anatomy of a stuck pg_dump:
        #  - 2+ concurrent pg_dump compete for ACCESS SHARE locks on big tables
        #    (unified_logs ~244M rows) and may deadlock during snapshot release
        #  - the | gzip variant adds a pipe that can stall on flush if either side
        #    blocks, leaving both processes alive after the .dump file is written
        #  - on-disk file is complete, the process is just stuck in finalisation
        # Selection: pg_dump with elapsed time HH:MM:SS where HH >= 1
        candidates=$(ps -eo pid,etime,user,comm --no-headers | awk '
            $4=="pg_dump" {
                n = split($2, t, ":")
                if (n == 3 && t[1]+0 >= 1) print $1, $2, $3
            }')
        if [ -z "$candidates" ]; then
            echo -e "  ${C_GREEN}Aucun pg_dump bloque${C_RESET}"
            sleep 1
            exec "$0"
        fi
        echo "$candidates" | awk '{printf "  pid=%-8s age=%-12s user=%s\n", $1, $2, $3}'
        echo ""
        # Also show parent shells (sh -c, pg_backup.sh) so we can kill the chain
        ppids=$(echo "$candidates" | awk '{print $1}' | xargs -I{} ps -o ppid= -p {} 2>/dev/null | tr -d ' ' | sort -u)
        echo -e "${C_DIM}  Parents: $(echo $ppids | tr '\n' ' ')${C_RESET}"
        echo ""
        read -p "  Confirm kill (TERM puis KILL si survie 5s) ? [y/N]: " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo -e "${C_YELLOW}Annule${C_RESET}"
            sleep 1
            exec "$0"
        fi
        # pg_dump runs as root -> sudo required
        pids=$(echo "$candidates" | awk '{print $1}')
        echo -e "${C_DIM}sudo kill -TERM ${pids} ${ppids}${C_RESET}"
        sudo -n kill -TERM $pids $ppids 2>/dev/null || \
            sudo kill -TERM $pids $ppids
        sleep 5
        survivors=$(ps -p $pids -o pid= --no-headers 2>/dev/null | tr -d ' ' | grep -v '^$')
        if [ -n "$survivors" ]; then
            echo -e "${C_RED}Survivants: $survivors -> KILL -9${C_RESET}"
            sudo kill -KILL $survivors 2>/dev/null
        fi
        sleep 1
        echo ""
        echo -e "${C_WHITE}Etat final:${C_RESET}"
        ps -eo pid,etime,user,comm --no-headers | awk '$4=="pg_dump"' | sed 's/^/  /'
        [ -z "$(ps -eo comm --no-headers | awk '$1=="pg_dump"')" ] && echo -e "  ${C_GREEN}Tous les pg_dump termines${C_RESET}"
        echo ""
        read -p "  Enter..." _ && exec "$0"
        ;;
    0)
        echo -e "${C_DIM}Shell. 'cc' for menu.${C_RESET}"
        cd $LIADEV_HOME
        ;;
    q|Q)
        exit 0
        ;;
    *)
        echo "Invalid." && sleep 1 && exec "$0"
        ;;
esac
