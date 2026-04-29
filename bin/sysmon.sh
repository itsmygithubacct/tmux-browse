#!/bin/bash
# Lightweight system monitor — DSL/tinycore desktop widget style.
# Refreshes every 2 seconds with compact one-screen output.
# No dependencies beyond /proc and standard coreutils.

INTERVAL="${1:-2}"

while true; do
    clear
    printf '\033[1;36m── sysmon ──────────────────────────────\033[0m\n'

    # Uptime + load
    read -r up _ < /proc/uptime
    days=$((${up%.*} / 86400))
    hours=$(( (${up%.*} % 86400) / 3600 ))
    mins=$(( (${up%.*} % 3600) / 60 ))
    load=$(cut -d' ' -f1-3 /proc/loadavg)
    printf '\033[1mUptime:\033[0m %dd %dh %dm  \033[1mLoad:\033[0m %s\n' "$days" "$hours" "$mins" "$load"

    # CPU usage (from /proc/stat, compare two snapshots)
    read -r _ u1 n1 s1 i1 _ < /proc/stat
    sleep 0.2
    read -r _ u2 n2 s2 i2 _ < /proc/stat
    total=$(( (u2+n2+s2+i2) - (u1+n1+s1+i1) ))
    idle=$(( i2 - i1 ))
    if [ "$total" -gt 0 ]; then
        cpu=$(( 100 * (total - idle) / total ))
    else
        cpu=0
    fi
    cores=$(nproc 2>/dev/null || echo "?")
    printf '\033[1mCPU:\033[0m %d%% (%s cores)\n' "$cpu" "$cores"

    # Memory
    while IFS=': ' read -r key val _; do
        case "$key" in
            MemTotal)   mem_total=$val ;;
            MemAvailable) mem_avail=$val ;;
            SwapTotal)  swap_total=$val ;;
            SwapFree)   swap_free=$val ;;
        esac
    done < /proc/meminfo
    mem_used=$(( (mem_total - mem_avail) / 1024 ))
    mem_total_mb=$(( mem_total / 1024 ))
    mem_pct=$(( 100 * (mem_total - mem_avail) / mem_total ))
    printf '\033[1mMem:\033[0m %dM / %dM (%d%%)\n' "$mem_used" "$mem_total_mb" "$mem_pct"
    if [ "$swap_total" -gt 0 ]; then
        swap_used=$(( (swap_total - swap_free) / 1024 ))
        swap_total_mb=$(( swap_total / 1024 ))
        printf '\033[1mSwap:\033[0m %dM / %dM\n' "$swap_used" "$swap_total_mb"
    fi

    # Disk
    printf '\033[1mDisk:\033[0m '
    df -h / 2>/dev/null | awk 'NR==2{printf "%s / %s (%s)\n", $3, $2, $5}'

    # Network (bytes since boot)
    printf '\033[1mNet:\033[0m '
    awk 'NR>2 && $1!~/lo:/{
        gsub(/:/, "", $1)
        printf "%s rx:%s tx:%s  ", $1, $2, $10
    }' /proc/net/dev
    printf '\n'

    # Temperature (if available)
    for tz in /sys/class/thermal/thermal_zone*/temp; do
        if [ -r "$tz" ]; then
            t=$(cat "$tz")
            printf '\033[1mTemp:\033[0m %d.%d°C\n' "$((t/1000))" "$(( (t%1000)/100 ))"
            break
        fi
    done

    # Top processes by CPU
    printf '\033[1;36m── top processes ───────────────────────\033[0m\n'
    ps -eo pid,user,%cpu,%mem,comm --sort=-%cpu 2>/dev/null | head -6

    # Tasks
    running=$(ls -d /proc/[0-9]* 2>/dev/null | wc -l)
    printf '\n\033[1mTasks:\033[0m %d  \033[1mRefresh:\033[0m %ds\n' "$running" "$INTERVAL"

    sleep "$INTERVAL"
done
