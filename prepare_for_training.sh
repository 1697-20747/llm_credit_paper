#!/bin/bash
# =============================================================================
# prepare_for_training.sh
# =============================================================================
# Closes memory-hungry applications and frees up RAM before training.
# Run this immediately before train_mlx.sh.
#
# Usage:
#   chmod +x prepare_for_training.sh
#   ./prepare_for_training.sh
#   ./train_mlx.sh
# =============================================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
closed()  { echo -e "${CYAN}[QUIT]${NC}  $*"; }
skipped() { echo -e "        $*"; }

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " Preparing Mac for Training — Freeing Memory"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── Helper: quit app if running ───────────────────────────────────────────────
quit_app() {
    local app_name="$1"
    local process_name="${2:-$1}"
    if pgrep -x "$process_name" > /dev/null 2>&1 || \
       pgrep -f "$process_name" > /dev/null 2>&1; then
        osascript -e "tell application \"$app_name\" to quit" 2>/dev/null || \
        pkill -x "$process_name" 2>/dev/null || true
        sleep 0.5
        closed "$app_name"
    else
        skipped "$app_name (not running)"
    fi
}

# ── Memory before ─────────────────────────────────────────────────────────────
mem_before() {
    vm_stat | awk '
        /Pages free/     { free=$3 }
        /Pages inactive/ { inactive=$3 }
        END { printf "%.1f", (free+inactive)*16384/1073741824 }
    ' | tr -d '.'
}
BEFORE=$(python3 -c "
import subprocess
r = subprocess.run(['vm_stat'], capture_output=True, text=True)
f=i=0
for line in r.stdout.split('\n'):
    if 'Pages free' in line:
        try: f=int(line.split(':')[1].strip().rstrip('.'))
        except: pass
    if 'Pages inactive' in line:
        try: i=int(line.split(':')[1].strip().rstrip('.'))
        except: pass
print(f'{(f+i)*16384/1073741824:.1f}')
" 2>/dev/null || echo "?")
info "Available memory before: ~${BEFORE}GB"
echo ""

# ── Close browsers ────────────────────────────────────────────────────────────
echo "Browsers:"
quit_app "Google Chrome" "Google Chrome"
quit_app "Firefox" "firefox"
quit_app "Safari" "Safari"
quit_app "Microsoft Edge" "Microsoft Edge"
quit_app "Arc" "Arc"
quit_app "Brave Browser" "Brave Browser"
echo ""

# ── Close communication apps ──────────────────────────────────────────────────
echo "Communication:"
quit_app "Slack" "Slack"
quit_app "Microsoft Teams" "Microsoft Teams"
quit_app "Zoom" "zoom.us"
quit_app "Discord" "Discord"
quit_app "WhatsApp" "WhatsApp"
quit_app "Telegram" "Telegram"
quit_app "Messages" "Messages"
quit_app "Mail" "Mail"
echo ""

# ── Close productivity apps ───────────────────────────────────────────────────
echo "Productivity:"
quit_app "Microsoft Word" "Microsoft Word"
quit_app "Microsoft Excel" "Microsoft Excel"
quit_app "Microsoft PowerPoint" "Microsoft PowerPoint"
quit_app "Microsoft Outlook" "Microsoft Outlook"
quit_app "Numbers" "Numbers"
quit_app "Pages" "Pages"
quit_app "Keynote" "Keynote"
quit_app "Notion" "Notion"
quit_app "Obsidian" "Obsidian"
echo ""

# ── Close development tools (keep Terminal) ───────────────────────────────────
echo "Development tools:"
quit_app "Visual Studio Code" "Electron"
quit_app "Xcode" "Xcode"
quit_app "Docker" "Docker"
quit_app "Postman" "Postman"
quit_app "TablePlus" "TablePlus"
quit_app "Simulator" "Simulator"
echo ""

# ── Close media apps ──────────────────────────────────────────────────────────
echo "Media:"
quit_app "Spotify" "Spotify"
quit_app "Music" "Music"
quit_app "Photos" "Photos"
quit_app "Final Cut Pro" "Final Cut Pro"
quit_app "Adobe Photoshop" "Adobe Photoshop"
quit_app "Adobe Premiere Pro" "Adobe Premiere Pro"
echo ""

# ── Stop background services that use memory ──────────────────────────────────
echo "Background services:"

# Ollama — stop if running (we'll restart after training)
if pgrep -x "ollama" > /dev/null 2>&1; then
    pkill -x "ollama" 2>/dev/null || true
    closed "Ollama (will restart after training)"
else
    skipped "Ollama (not running)"
fi

# Stop any other Python processes (except this script's parent)
CURRENT_PID=$$
OTHER_PYTHON=$(pgrep -f "python" | grep -v "^$CURRENT_PID$" | \
               grep -v "prepare_for_training" | head -5 || true)
if [[ -n "$OTHER_PYTHON" ]]; then
    warn "Other Python processes running:"
    for pid in $OTHER_PYTHON; do
        cmd=$(ps -p $pid -o command= 2>/dev/null | cut -c1-60 || echo "unknown")
        warn "  PID $pid: $cmd"
    done
    read -r -p "  Kill these Python processes? [y/N] " kill_python
    if [[ "$kill_python" =~ ^[Yy]$ ]]; then
        echo "$OTHER_PYTHON" | xargs kill 2>/dev/null || true
        closed "Other Python processes"
    fi
fi

echo ""

# ── Purge memory cache ────────────────────────────────────────────────────────
info "Purging memory cache..."
sudo purge 2>/dev/null && info "Memory cache purged." || \
    warn "Memory purge skipped (requires sudo — run: sudo purge)"

# ── Disable sleep during training ─────────────────────────────────────────────
info "Preventing system sleep during training..."
# pmset -a disablesleep 1 requires sudo — use caffeinate instead
# We'll launch caffeinate in background and save its PID
pkill caffeinate 2>/dev/null || true
caffeinate -i -w $$ &
CAFFEINATE_PID=$!
echo "$CAFFEINATE_PID" > /tmp/camels_caffeinate.pid
info "Sleep prevention active (PID: $CAFFEINATE_PID)"
info "System will not sleep during training."

# ── Memory after ─────────────────────────────────────────────────────────────
sleep 2
AFTER=$(python3 -c "
import subprocess
r = subprocess.run(['vm_stat'], capture_output=True, text=True)
f=i=0
for line in r.stdout.split('\n'):
    if 'Pages free' in line:
        try: f=int(line.split(':')[1].strip().rstrip('.'))
        except: pass
    if 'Pages inactive' in line:
        try: i=int(line.split(':')[1].strip().rstrip('.'))
        except: pass
print(f'{(f+i)*16384/1073741824:.1f}')
" 2>/dev/null || echo "?")

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " Memory Summary"
echo "═══════════════════════════════════════════════════════════"
echo " Before : ~${BEFORE}GB available"
echo " After  : ~${AFTER}GB available"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo " ✅ Ready for training. Run:"
echo "    ./train_mlx.sh"
echo ""
echo " ⚠️  Do not open other applications during training."
echo " ⚠️  Keep this terminal window open (caffeinate is running)."
echo ""
echo " After training completes, re-enable sleep with:"
echo "    pkill caffeinate"
echo "═══════════════════════════════════════════════════════════"
