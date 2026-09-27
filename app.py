"""Math Problems Search — Streamlit app.

Syncs the Overleaf project (via its git bridge) once per app process
and provides grep-like search over the .tex files. Auth comes later.
"""

import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Math Problems Search")

OVERLEAF_GIT_BASE = "https://git.overleaf.com"
CLONE_TIMEOUT_S = 300
CONTEXT_LINES = 2
MAX_FILES_SHOWN = 50
MAX_MATCHES_PER_FILE = 20
MAX_TOTAL_MATCHES = 500


def get_secret(key: str) -> str | None:
    try:
        value = st.secrets.get(key)
    except Exception:
        return None
    return value or None


@st.cache_resource(show_spinner=False)
def clone_overleaf(project_id: str, token: str) -> dict:
    """Shallow-clone the Overleaf project once per app process."""
    dest = Path(tempfile.mkdtemp(prefix="overleaf_repo_"))
    url = f"{OVERLEAF_GIT_BASE.replace('https://', f'https://git:{token}@')}/{project_id}"
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        capture_output=True,
        text=True,
        timeout=CLONE_TIMEOUT_S,
    )
    if proc.returncode != 0:
        err = (proc.stderr or "unknown git error").replace(token, "***").strip()
        raise RuntimeError(err)

    def in_repo(p: Path) -> bool:
        return ".git" not in p.parts

    all_files = [p for p in dest.rglob("*") if p.is_file() and in_repo(p)]
    return {
        "path": dest,
        "synced_at": datetime.now(timezone.utc),
        "tex_files": sorted((p for p in all_files if p.suffix == ".tex"), key=str),
        "file_count": len(all_files),
    }


@st.cache_data(show_spinner=False, ttl="1h")
def search_files(repo_path: str, query: str) -> dict:
    """Case-insensitive grep-like search over all .tex files."""
    try:
        pattern = re.compile(query, re.IGNORECASE)
        literal_fallback = False
    except re.error:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        literal_fallback = True

    results = []
    total = 0
    truncated = False
    for path in sorted(Path(repo_path).rglob("*.tex")):
        if ".git" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        matches = [(i + 1, line) for i, line in enumerate(lines) if pattern.search(line)]
        if not matches:
            continue
        results.append({"path": path, "lines": lines, "matches": matches})
        total += len(matches)
        if total >= MAX_TOTAL_MATCHES:
            truncated = True
            break

    return {
        "results": results,
        "total": total,
        "literal_fallback": literal_fallback,
        "truncated": truncated,
    }


def build_hunks(match_linenos: list[int], total_lines: int) -> list[tuple[int, int, set[int]]]:
    """Merge matching line numbers into (start, end, match_lines) hunks with context."""
    hunks: list[tuple[int, int, set[int]]] = []
    for ln in match_linenos:
        lo = max(1, ln - CONTEXT_LINES)
        hi = min(total_lines, ln + CONTEXT_LINES)
        if hunks and lo <= hunks[-1][1] + 1:
            prev_lo, _, prev_matches = hunks[-1]
            hunks[-1] = (prev_lo, hi, prev_matches | {ln})
        else:
            hunks.append((lo, hi, {ln}))
    return hunks


def render_results(search: dict, repo_path: Path) -> None:
    results = search["results"]
    if not results:
        st.info("No matches found.")
        return

    st.write(f"**{search['total']}** matches in **{len(results)}** files")
    notes = []
    if search["literal_fallback"]:
        notes.append("invalid regex — searched for the literal text instead")
    if search["truncated"]:
        notes.append(f"stopped after {MAX_TOTAL_MATCHES} matches")
    if len(results) > MAX_FILES_SHOWN:
        notes.append(f"showing first {MAX_FILES_SHOWN} files")
    if notes:
        st.caption("; ".join(notes).capitalize() + ".")

    for res in results[:MAX_FILES_SHOWN]:
        rel = res["path"].relative_to(repo_path)
        matches = res["matches"]
        st.markdown(f"**{rel}** ({len(matches)} matches)")
        shown = matches[:MAX_MATCHES_PER_FILE]
        for lo, hi, match_lines in build_hunks([n for n, _ in shown], len(res["lines"])):
            block = [
                f"{'>' if n in match_lines else ' '} {n:>4}: {res['lines'][n - 1]}"
                for n in range(lo, hi + 1)
            ]
            st.code("\n".join(block), language="latex")
        if len(matches) > MAX_MATCHES_PER_FILE:
            st.caption(f"… and {len(matches) - MAX_MATCHES_PER_FILE} more matches in this file.")


def search_input() -> str:
    """Search field that reruns on every keystroke (falls back to Enter-based input)."""
    label = "Search (regex supported)"
    placeholder = r"e.g. tetivn|nejednakost"
    try:
        from st_keyup import st_keyup
    except ImportError:
        return st.text_input(label, placeholder=placeholder).strip()
    return (st_keyup(label, placeholder=placeholder, debounce=300) or "").strip()


def main() -> None:
    st.title("Math Problems Search")

    project_id = get_secret("overleaf_project_id")
    token = get_secret("overleaf_token")
    if not project_id or not token:
        st.error("Overleaf credentials are not configured.")
        st.markdown(
            "Add the following to `.streamlit/secrets.toml` (locally) or to the "
            "app's **Secrets** on Streamlit Cloud:\n\n"
            "```toml\n"
            'overleaf_project_id = "<id from overleaf.com/project/<id>>"\n'
            'overleaf_token = "<token from Account Settings → Git Integration>"\n'
            "```"
        )
        st.stop()

    with st.spinner("Syncing from Overleaf…"):
        try:
            repo = clone_overleaf(project_id, token)
        except Exception as exc:
            st.error(f"Overleaf sync failed: {exc}")
            st.stop()

    st.caption(
        f"Last synced: {repo['synced_at']:%Y-%m-%d %H:%M:%S} UTC · "
        f"{repo['file_count']} files in project"
    )

    query = search_input()

    if not query:
        return

    search = search_files(str(repo["path"]), query)
    render_results(search, repo["path"])


if __name__ == "__main__":
    main()
