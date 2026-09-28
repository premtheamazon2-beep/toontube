"""Builds a .srt subtitle file from scene narration text and durations."""


def _fmt(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(entries: list[tuple[str, float, float]], out_path: str):
    """entries: list of (text, start_seconds, end_seconds)"""
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (text, start, end) in enumerate(entries, 1):
            f.write(f"{i}\n{_fmt(start)} --> {_fmt(end)}\n{text.strip() or ' '}\n\n")
