"""Math Problems Search — Streamlit app.

Phase 1: syncs the Overleaf project (via its git bridge) once per app
process and lists the .tex files found. Search and auth come later.
"""

import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Math Problems Search")

OVERLEAF_GIT_BASE = "https://git.overleaf.com"
CLONE_TIMEOUT_S = 300


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
    st.subheader(f"{len(repo['tex_files'])} .tex files")
    for path in repo["tex_files"]:
        st.text(path.relative_to(repo["path"]))


if __name__ == "__main__":
    main()
