"""
fetch_data.py - gets the two challenge workbooks onto the server when the app starts.

WHY: the challenge data must not be in this public repo. It lives in a PRIVATE GitHub repo instead, and the
     deployed app downloads it with a read-only token that is stored only in the host's settings (Render).
HOW: 1. If both files are already in data/ (e.g. on your laptop), do nothing.
     2. Otherwise read DATA_REPO_TOKEN from the environment and download each file through the GitHub API.
     3. Never raise. Return (ok, message) so the app can show "data not loaded" instead of crashing.
SAFETY: the token is only ever put in a request header. It is never printed, logged or put in a message.

Environment variables:
  DATA_REPO_TOKEN   (secret) fine-grained GitHub token, read-only "Contents" on the data repo only
  DATA_REPO         owner/name of the private repo   (default: Kasimshaik2508/motor-self-inspection-data)
  DATA_REPO_BRANCH  branch holding the files         (default: main)
"""
import os
import urllib.error
import urllib.parse
import urllib.request

FILES = ["PS-03_inspection_cases.xlsx", "PS-03_evaluation_set.xlsx"]
DATA_DIR = os.environ.get("PS03_DATA", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))


def _missing():
    return [f for f in FILES if not os.path.isfile(os.path.join(DATA_DIR, f))]


def ensure_data():
    """Returns (ok: bool, message: str). The message is safe to show on the website."""
    missing = _missing()
    if not missing:
        return True, "Data files found."

    token = os.environ.get("DATA_REPO_TOKEN", "").strip()
    repo = os.environ.get("DATA_REPO", "Kasimshaik2508/motor-self-inspection-data").strip()
    branch = os.environ.get("DATA_REPO_BRANCH", "main").strip()
    if not token:
        return False, ("Data not loaded: the DATA_REPO_TOKEN setting is empty on the server, "
                       f"and these files are missing: {', '.join(missing)}.")

    os.makedirs(DATA_DIR, exist_ok=True)
    for name in missing:
        url = (f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(name)}"
               f"?ref={urllib.parse.quote(branch)}")
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.raw",       # ask for the file bytes, not JSON
            "User-Agent": "motor-self-inspection-app",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        target = os.path.join(DATA_DIR, name)
        tmp = target + ".part"
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as out:
                out.write(r.read())
            os.replace(tmp, target)                        # only a complete download gets the real name
        except urllib.error.HTTPError as e:
            hint = {401: "the token is wrong or expired",
                    403: "the token is not allowed to read this repo",
                    404: f"repo '{repo}', branch '{branch}' or file '{name}' was not found "
                         "(or the token cannot see that repo)"}.get(e.code, "GitHub refused the request")
            return False, f"Data not loaded: downloading {name} failed (HTTP {e.code}: {hint})."
        except Exception as e:                             # network down, timeout, disk error...
            return False, f"Data not loaded: downloading {name} failed ({type(e).__name__})."
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return True, f"Downloaded {len(missing)} data file(s) from the private data repo."


if __name__ == "__main__":                                 # manual test: python backend/fetch_data.py
    print(ensure_data())
