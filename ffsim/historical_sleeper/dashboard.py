import subprocess
from pathlib import Path


CRAWL_COMMANDS = {"collect", "discover", "hydrate", "players"}


def crawler_runtime(ps_output=None):
    if ps_output is None:
        try:
            ps_output = subprocess.run(
                ["ps", "-axo", "pid=,rss=,command="],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout
        except (OSError, subprocess.SubprocessError) as error:
            return {
                "process_count": 0,
                "rss_bytes": 0,
                "pids": [],
                "error": str(error),
            }
    processes = []
    for line in ps_output.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid, rss_kib, command = parts
        tokens = command.split()
        if "ffsim.historical_sleeper" not in command:
            continue
        if not CRAWL_COMMANDS.intersection(tokens):
            continue
        try:
            processes.append((int(pid), int(rss_kib) * 1024))
        except ValueError:
            continue
    return {
        "process_count": len(processes),
        "rss_bytes": sum(rss for _, rss in processes),
        "pids": [pid for pid, _ in processes],
    }


def sqlite_storage(database_path):
    database_path = Path(database_path)
    sizes = {
        "main_bytes": _size(database_path),
        "wal_bytes": _size(Path(str(database_path) + "-wal")),
        "shm_bytes": _size(Path(str(database_path) + "-shm")),
    }
    sizes["total_bytes"] = sum(sizes.values())
    return sizes


def render_dashboard(snapshot, interval, *, width=100, color=False, verbose=False):
    status = snapshot["status"]
    quality = snapshot["quality"]
    runtime = snapshot["runtime"]
    storage = snapshot["storage"]
    width = min(120, max(78, int(width)))
    hydration_queue = status["hydration_queue"]
    awaiting = max(
        0,
        status["candidate_leagues"]
        - sum(
            hydration_queue.get(state, 0)
            for state in ("pending", "in_progress", "done", "failed")
        ),
    )
    hydration_work = (
        awaiting
        + hydration_queue.get("pending", 0)
        + hydration_queue.get("in_progress", 0)
    )
    target = max(1, quality["training_ready_target"])
    ready = quality["training_ready_leagues"]
    progress = min(100.0, ready / target * 100)
    remaining = max(0, target - ready)
    mode = _mode(
        runtime["process_count"] > 0,
        status["crawl_queue"],
        hydration_queue,
        hydration_work,
        quality["candidate_buffer_target"],
    )
    ready_by_year = quality["training_ready_by_year"]
    year_floor = quality["min_training_ready_per_year"]
    flags = sum(status["quality_flags"].values())

    lines = [_top_border("FFSIM / CHAMPIONSHIP DATASET", mode, width)]
    lines.extend([
        _line(
            f"updated {snapshot['updated_at']}  ·  refresh {interval:g}s  ·  Control-C closes this dashboard",
            width,
        ),
        _section("STATUS", width),
        _line(
            f"TARGET      {ready:,} / {target:,} ready  ·  {progress:.1f}%  ·  "
            f"{remaining:,} championship events needed",
            width,
        ),
        _line(
            f"HYDRATION   waiting {awaiting:,}  ·  queued {hydration_queue.get('pending', 0):,}  ·  "
            f"active {hydration_queue.get('in_progress', 0):,}  ·  failed {hydration_queue.get('failed', 0):,}",
            width,
        ),
        _line(
            f"DISCOVERY   pending {status['crawl_queue'].get('pending', 0):,}  ·  "
            f"done {status['crawl_queue'].get('done', 0):,}  ·  "
            f"active {status['crawl_queue'].get('in_progress', 0):,}  ·  "
            f"failed {status['crawl_queue'].get('failed', 0):,}",
            width,
        ),
        _line(
            f"HEALTH      RSS {format_bytes(runtime['rss_bytes']) if runtime['process_count'] else 'stopped'}  ·  "
            f"DB {format_gb(storage['total_bytes'])}  ·  "
            f"429s {status['rate_limit_responses']:,}  ·  flags {flags:,}",
            width,
        ),
        _line(
            f"READY/YR    floor {year_floor:,}  ·  "
            f"21 {ready_by_year.get('2021', 0):,}  ·  "
            f"22 {ready_by_year.get('2022', 0):,}  ·  "
            f"23 {ready_by_year.get('2023', 0):,}  ·  "
            f"24 {ready_by_year.get('2024', 0):,}  ·  "
            f"25 {ready_by_year.get('2025', 0):,}",
            width,
        ),
    ])
    if verbose:
        lines.extend(_verbose_lines(status, quality, runtime, storage, width))
    lines.append(_bottom_border(width))
    rendered = "\n".join(lines)
    return _colorize(rendered, mode, status, quality) if color else rendered


def _mode(running, crawl_queue, hydration_queue, hydration_work, buffer):
    if not running:
        return "○ STOPPED"
    if hydration_queue.get("in_progress", 0) or hydration_work >= buffer:
        return "● HYDRATING"
    if crawl_queue.get("in_progress", 0):
        return "● DISCOVERING"
    return "● RUNNING"



def _verbose_lines(status, quality, runtime, storage, width):
    years = status["leagues_by_year"]
    return [
        _section("DETAILS", width),
        _line(
            f"HYDRATION   {quality['fully_hydrated_leagues']:,} complete  ·  "
            f"{status['candidate_leagues']:,} candidates  ·  "
            f"{quality['failed_hydration']:,} failed",
            width,
        ),
        _line(
            f"DISCOVERY   {status['league_seasons']:,} league-seasons  ·  "
            f"{status['users']:,} users  ·  {status['crawl_queue'].get('failed', 0):,} failed",
            width,
        ),
        _line(
            f"DATASET     {status['drafts']:,} drafts  ·  {status['draft_picks']:,} picks  ·  "
            f"{status['team_seasons']:,} team-seasons  ·  {status['raw_objects']:,} raw",
            width,
        ),
        _line(
            f"YEARS       2021 {years.get('2021', 0):,}  2022 {years.get('2022', 0):,}  "
            f"2023 {years.get('2023', 0):,}  2024 {years.get('2024', 0):,}  "
            f"2025 {years.get('2025', 0):,}",
            width,
        ),
        _line(_runtime_line(runtime), width),
        _line(_storage_line(storage), width),
        _line(f"QUALITY     {_counts(status['quality_flags'])}", width),
    ]



def format_bytes(value):
    value = max(0, int(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit in {"B", "KiB"} else f"{amount:.1f} {unit}"
        amount /= 1024
    raise AssertionError("unreachable")


def format_gb(value):
    return f"{max(0, int(value)) / 1_000_000_000:.3f} GB"


def _runtime_line(runtime):
    if runtime.get("error"):
        return f"CRAWLER     memory unavailable ({runtime['error']})"
    if not runtime["process_count"]:
        return "CRAWLER     not running"
    noun = "process" if runtime["process_count"] == 1 else "processes"
    pids = ",".join(map(str, runtime["pids"]))
    return (
        f"CRAWLER     {format_bytes(runtime['rss_bytes'])} RSS  ·  "
        f"{runtime['process_count']} {noun}  ·  pid {pids}"
    )


def _storage_line(storage):
    return (
        f"SQLITE        {format_gb(storage['total_bytes'])} total  ·  "
        f"main {format_gb(storage['main_bytes'])}  ·  "
        f"WAL {format_gb(storage['wal_bytes'])}  ·  "
        f"SHM {format_gb(storage['shm_bytes'])}"
    )


def _queue(counts):
    return "  ".join(
        f"{label} {counts.get(key, 0):,}"
        for key, label in (
            ("pending", "pending"),
            ("in_progress", "active"),
            ("done", "done"),
            ("failed", "failed"),
        )
    )


def _counts(counts):
    if not counts:
        return "none"
    return "  ".join(f"{key}:{value:,}" for key, value in sorted(counts.items()))


def _top_border(title, state, width):
    fixed = f"┌─ {title} "
    tail = f" {state} ┐"
    return fixed + "─" * max(1, width - len(fixed) - len(tail)) + tail


def _section(title, width):
    fixed = f"├─ {title} "
    return fixed + "─" * max(1, width - len(fixed) - 1) + "┤"


def _line(content, width):
    content = content[: width - 4]
    return f"│ {content:<{width - 4}} │"


def _bottom_border(width):
    return "└" + "─" * (width - 2) + "┘"


def _colorize(text, mode, status, quality):
    reset = "\033[0m"
    cyan = "\033[36m"
    green = "\033[32m"
    yellow = "\033[33m"
    dim = "\033[2m"
    title = "FFSIM / CHAMPIONSHIP DATASET"
    text = text.replace(title, f"{cyan}{title}{reset}")
    state_color = dim if mode == "○ STOPPED" else green
    text = text.replace(mode, f"{state_color}{mode}{reset}")
    for section in ("STATUS", "DETAILS"):
        text = text.replace(section, f"{cyan}{section}{reset}")
    if status["request_failures"] or quality["failed_hydration"] or status["quality_flags"]:
        text = text.replace("HEALTH", f"{yellow}HEALTH{reset}", 1)
    return text


def _size(path):
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
