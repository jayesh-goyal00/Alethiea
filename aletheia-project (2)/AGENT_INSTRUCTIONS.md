# Instructions for the AI coding agent

You are helping a non-programmer finish **Aletheia**, a website for people in India who find a deepfake video of themselves.
Read `ALETHEIA_PROGRESS.md` first (full background, decisions, next steps), then `backend/README.md`.
The owner uses a **MacBook** (Python 3, ffmpeg and git are already installed). Explain what you do in plain, simple words. Do not assume technical knowledge.

## Project layout

- `frontend/`: plain HTML, CSS and JS, no build step. Talks to the backend only through `frontend/js/api.js`.
- `backend/`: FastAPI. `main.py` (endpoint), `videoinfo.py` (ffprobe + SHA-256), `linkfetch.py` (safe link download with yt-dlp).
- The detector score is currently a **placeholder of 50 ("Not sure")**. Do not present it as a real result.

## Rules (important)

1. Only create, edit or delete files **inside this project folder**. Never touch the owner's other files, and never delete their videos.
2. No `sudo`. Do not install anything outside the project's virtual environment (`backend/.venv`) without asking first. Ask before installing large packages (for example PyTorch).
3. Never upload videos or links anywhere except the local backend. Do not push to GitHub or any remote.
4. Do not weaken the safety checks in `backend/linkfetch.py` (blocking private, internal and local addresses; http/https only; ports 80/443 only). Ask first if you think a change is needed.
5. Uploaded videos must never be kept on the server. They are deleted right after analysis.
6. Never claim a video is proven real or proven fake. Pulse detection is a weak signal; a weak or unclear result should lead to "Not sure".
7. If something fails, show the exact error, say what you think caused it, and fix it. Do not hide failures or skip tests.

## Task 1: set up and verify what already exists (do this first)

These are the steps the owner did by hand earlier. Do them now and report each result.

1. `cd backend`, create the virtual environment: `python3 -m venv .venv`, activate it: `source .venv/bin/activate`.
2. `pip install -r requirements.txt` (this includes `yt-dlp`). Check `ffmpeg -version`, `ffprobe -version` and `yt-dlp --version` all work.
3. Start the backend in the background: `uvicorn main:app --reload --port 8000`. Confirm `curl http://localhost:8000/api/health` returns `{"ok":true}`.
4. Find any short `.mp4` the owner has (for example in `~/Downloads`; ask the owner if none is found). Test an upload. Note: in curl the field must be named `video` and the path must be written in full or with `$HOME`, not `~`:
   `curl -F "video=@$HOME/Downloads/FILE.mp4" http://localhost:8000/api/analyze`
   Expect JSON with `fileName`, `sha256`, `duration`, `fps`, `score: 50`.
5. Check the hash: `shasum -a 256 FILE.mp4` must equal the `sha256` returned.
6. Test a link with a direct `.mp4` link (ask the owner for one if you do not have one):
   `curl -X POST -H "Content-Type: application/json" -d '{"url":"https://..."}' http://localhost:8000/api/analyze`
7. Safety test, which **must** return "This link is not allowed.":
   `curl -X POST -H "Content-Type: application/json" -d '{"url":"http://127.0.0.1:8000/api/health"}' http://localhost:8000/api/analyze`
8. Connect the website: in `frontend/js/config.js` set `API_BASE: 'http://localhost:8000'`. In a second background process run `python3 -m http.server 5500` inside `frontend/`. Open http://localhost:5500, upload the same video and press "Check This Video". The Analysis page must show the same hash and the real length and fps. Also test "Paste a link". Use a browser tool if you have one; if not, tell the owner exactly what to click and what they should see.
9. Leave both servers running when you finish and tell the owner the website address.

Report in this format: a list of each step with PASS or FAIL, then any errors with exact text.

## Task 2: small frontend wording fixes

- On the Check Video page, change "Real faces show a faint pulse in their skin color. Fake ones usually don't." to something that does not overclaim (a pulse can be copied into deepfakes, and compressed or dark videos can hide a real pulse).
- Make sure a weak or unclear pulse result is described as "Not sure", not "fake". Keep the wording simple, for ordinary people.

## Task 3: test videos and a comparison script (needs the owner's help)

1. Create `test_videos/real/` and `test_videos/fake/` and ask the owner to put clips there (real ones from Indian phones and WhatsApp, plus fakes).
2. Write `backend/evaluate.py`: runs candidate detectors on every video in those folders and prints a table with the file, the score from each detector and the **time per video**.
3. Candidates, in this order: (a) a simple pulse method (POS or CHROM, written with NumPy/SciPy, or `pyVHR` if it installs cleanly; check its licence), (b) one small free classifier from Hugging Face (for example `faisalishfaq2005/deepfake-detection-efficientnet-vit`, MIT, about 20M parameters, run on CPU on 12 to 16 sampled face frames). Ask before installing PyTorch.
4. Use 2 or 3 **continuous** windows of 10 to 15 seconds with a clear face, not random pieces.
5. Goal: find the combination that rarely marks real videos as "Likely fake". Show "Likely fake" only if at least two signals agree; otherwise "Not sure".

## Later tasks (do not start without the owner's go-ahead)

Evidence report PDF with both the original and the submitted-copy SHA-256; server-side ffmpeg compression of one continuous clip to under about 9.5 MB for the portal; deployment on free hosting; privacy page. See `ALETHEIA_PROGRESS.md` sections 4 and 5.
