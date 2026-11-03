# Aletheia: progress and plan (handoff file)

Last updated: 3 Nov 2026. Paste this file into a new chat if the conversation limit is reached.

## 1. What Aletheia is

A website for people in India who find a deepfake video of themselves (or someone they know). It does two things:

1. **Check Video**: user uploads a file or pastes a link. The backend looks for a natural pulse in the face (rPPG) and returns a score from 0 to 100, three check results and an evidence report PDF.
2. **Report Incident**: a 3-step guide to file a complaint on cybercrime.gov.in ("Report Suspect" > "Deepfake"), with a plain-words description the user can copy.

The site never submits anything to the government portal for the user.

## 2. Done so far

### Frontend (finished, in `frontend3.zip`)
Plain HTML, CSS and JS, no build step. Files: `index.html`, `css/style.css`, `js/config.js`, `js/api.js`, `js/app.js`, `images/step-2..5.jpg`.
Runs in **demo mode** (fixed 88% result) while `API_BASE` in `js/config.js` is empty.

Changes made in this chat:
- The portal description no longer contains the score, SHA hash or detector verdict. It describes what happened to the person.
- The description is now written in **Report Incident, step 1** (not on the Analysis Score page). The user picks what happened, optionally adds where/when and their own words, and can tick "Someone is asking me for money". The text is built by `buildDesc()` in `js/app.js`, stays within 500 characters, and can be edited by hand. "Reset to my answers" rebuilds it.
- "Summary" wording replaced by "description" everywhere (final checklist now says "Description ready to paste (100 to 500 characters)").
- Money demand: ticking the checkbox shows a "Call 1930 now" box and adds a line to the description. The 1930 card in the final checklist says to call if any money is demanded or already paid.
- README and the "What is the evidence report?" text updated to match.

Preview link (private to the owner): https://claude.ai/artifact/967u6KRQY6uExb39RgHPs7

### Backend
**Steps 1 and 2 written** (in `aletheia-project.zip`, folder `backend/`). FastAPI: `POST /api/analyze` accepts a file upload **or a link**, checks it is a real video with ffprobe, returns the real file name (or link), SHA-256, fps and length, deletes the file, and returns a **placeholder score of 50**. Owner ran step 1 on a MacBook (Python 3, ffmpeg, git installed, project in the user folder): the curl test and the website showed the correct hash, length 0:14 and fps 30.00.
Step 2 (links) adds `linkfetch.py`: link safety checks (http/https only, ports 80/443, no passwords, blocks private/loopback/internal addresses) and download with `yt-dlp` (size, length and time limits), plus a job limit (`MAX_JOBS`). Tested in the sandbox: the URL checks, and the download wrapper with a stand-in yt-dlp. **Not tested**: real yt-dlp downloads and `main.py` end to end (no internet or FastAPI in the sandbox). Known limit: a site could redirect to an internal address after the check.
The frontend `js/api.js` shows the backend's own error message.

## 3. Backend contract the frontend expects

`POST /api/analyze`
- File upload: `multipart/form-data`, field `video`. Link: JSON `{ "url": "https://..." }`.
- Response JSON: `fileName`, `sha256`, `fps`, `duration`, `score` (0-100), `checks[]` (`label`, `text`, `ok`), `reportUrl` (optional PDF link).
- Score bands: under 40 likely real, 40 to 69 not sure, 70 and up likely fake.
- Any error: non-2xx status.

`GET /api/report/{id}.pdf`: evidence report with file name, SHA-256, length, fps, score and verdict, the three checks, date and time, and a disclaimer.

## 4. Decisions and findings

### Video size and the portal
- The portal limit is **10 MB** (from the project's README and screenshots). **Not verified**: check it on the live Deepfake form. Other portal forms have other limits.
- Analyze the **original** video on the server (analysis limit can be 20 MB or more). Make a separate, smaller copy for the portal.
- Detection: use 2 or 3 **continuous** windows of 10 to 15 seconds with a clear face and little movement, not random pieces.
- Portal copy: **one continuous clip**. Compress (lower bitrate and resolution with ffmpeg on the server) rather than cut. Trim to one unbroken section only if needed.
- Compressing changes the file, so show **two SHA-256 hashes** in the report (original and submitted copy) and tell the user to keep the original. Ask a lawyer or I4C what evidence they accept.

### Pulse detection (rPPG) is a weak signal
- The Netherlands Forensic Institute (NFI) and UvA work on "blood flow detection". It is not yet fully validated for court and is a supporting technique.
- NFI coverage says heartbeat signals can carry over from the original footage into deepfakes and that the newest deepfakes can mimic heartbeats. So a pulse does not prove a video is real and a flat pulse does not prove it is fake.
- No public NFI GitHub repository was found.
- Accuracy depends on lighting, movement, camera and compression. Effect on Indian users (skin tone, WhatsApp compression) is **untested**. Must be validated on Indian test videos.
- **To do in the frontend**: change "Fake ones usually don't" on the Check Video page, and make a weak pulse lead to "Not sure", never a confident "fake".

### Detector building blocks (none tested yet)
- **pyVHR** (Python, pip): main pulse library. Check its `LICENSE`.
- **rPPG-Toolbox** (NeurIPS 2023): later option. Licence looked like "Other" in one listing, so read it first.
- Fallback: write POS or CHROM yourself with NumPy and SciPy.
- Free classifiers on Hugging Face: Improved EfficientViT (`faisalishfaq2005/deepfake-detection-efficientnet-vit`, MIT, about 20M parameters), DeepGuard (`pip install deepguard`, MIT), `Arko007/deepfake-detector-dfd-sota` (Apache-2.0, about 308M parameters, probably too heavy for free CPU). Accuracy on new generators and Indian data is unknown.
- Plan: **layered**. (1) ffprobe metadata and hash, (2) pulse check, (3) one small classifier on 12 to 16 sampled face frames. Show "Likely fake" only if at least two signals agree, otherwise "Not sure".

### Free hosting (checked 3 Nov 2026)
- Frontend: free static hosting (Hugging Face static Space, Cloudflare Pages, Netlify, GitHub Pages). Check current terms.
- Backend:
  - Hugging Face Docker Space: free CPU specs are 2 vCPU, 16 GB RAM, sleeps when idle. But the official docs say Docker/Gradio Spaces need a paid plan. **Unreliable.**
  - Oracle Cloud Always Free: ARM VM now **2 OCPU / 12 GB** (cut from 4 / 24 on 15 Jun 2026; many guides are outdated). Needs a card for verification. "Out of capacity" errors are common. Check that OpenCV, PyTorch and ffmpeg work on ARM.
  - Own computer plus a free tunnel (Cloudflare Tunnel): fine for demos only.

### Storage and operation
- Videos only in temporary disk space, **deleted right after analysis**. Victims upload sensitive material, so keep as little as possible and do not log full URLs.
- PDFs under long random IDs with automatic expiry (a few days). No database needed at first.
- Run 1 or 2 analyses at a time. Rate-limit per IP. Update `yt-dlp` regularly. Block links to internal addresses. Add a privacy page and state that Aletheia is not run by I4C or the government.
- If analysis takes more than 30 to 60 seconds, switch to a job ID plus polling (small frontend change).

## 5. Status of next steps

1. [x] **Set up the computer**: Python 3.9 virtual environment (`backend/.venv`), ffmpeg 9.0.2, ffprobe, yt-dlp installed and working.
2. [x] **Backend skeleton tested**: `POST /api/analyze` tested with file upload and live links, health check passed, frontend connected via `API_BASE: 'http://localhost:8000'`.
3. [ ] **Collect 30 to 50 test videos**: `test_videos/real/` and `test_videos/fake/` directories created; waiting for test clips.
4. [x] **Pulse detection implemented**: `backend/detector_pulse.py` using OpenCV face tracking + POS (Plane-Orthogonal-to-Skin) rPPG + Welch PSD spectral analysis. Weak/unclear pulse defaults to score 50 ("Not sure").
5. [x] **Detector evaluation script**: `backend/evaluate.py` scans `test_videos/real/` and `test_videos/fake/` and outputs a benchmark table with scores, BPM, and time per video.
6. [x] **Build evidence report PDF**: `backend/report_generator.py` uses ReportLab to generate downloadable forensic certificates with both SHA-256 hashes, metadata, score, checks, and legal disclaimers. Served at `GET /api/report/{id}.pdf`.
7. [x] **Server-side compression**: `backend/compress.py` creates a continuous copy under 9.2 MB for the portal using ffmpeg, with original and compressed SHA-256 hashes recorded.
8. [x] **Frontend wording fixes**: Fixed overclaiming on pulse detection in `index.html` and `app.js`; added Privacy & Safety page.
9. [ ] **Test one small classifier** (Hugging Face / CPU) on sampled face frames once test videos are ready.
10. [ ] **Deploy**: Free hosting / Docker setup when ready.

## 6. Open questions

- Is the 10 MB limit on the live Deepfake form correct, and which formats does it accept?
- Which classifier gives the fewest false "fake" results on real Indian videos?
- Can a free Oracle ARM VM be created in an Indian region, and is analysis fast enough on 2 OCPU?
- What evidence format and hash handling do I4C or police accept? (Ask a lawyer.)

## 7. How to continue in a new chat

Upload `frontend3.zip` and this file, then say which step from section 5 you are on. Ask for one step at a time and paste any error messages.
