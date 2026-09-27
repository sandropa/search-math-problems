# Math Problems Search

Streamlit app that clones our Overleaf lectures project and searches the `.tex` files.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

You need `.streamlit/secrets.toml` (gitignored — ask a maintainer for values):

```toml
overleaf_project_id = "<id from overleaf.com/project/<id>>"
overleaf_token = "<Overleaf → Account Settings → Git Integration token>"
```

## Deploy (Streamlit Cloud)

Point the app at `app.py` and paste the same secrets into **Settings → Secrets**.
The Overleaf project is cloned once per app restart.
