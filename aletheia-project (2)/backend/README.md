# Aletheia backend (step 2)

What it does now: accepts an uploaded video **or a link**, checks it is a real video, returns the real file name (or the link), SHA-256, fps and length.
The score is a **placeholder (50 = "Not sure")**. The pulse detector, PDF report and compression come in later steps.
The video is deleted from the server straight after it is read.

## Run it on a Mac

If you already did step 1, just run `pip install -r requirements.txt` again (with the virtual environment active) to add `yt-dlp`, then restart the server.

Open Terminal in the `backend` folder, then:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Leave that window open. You should see `Uvicorn running on http://127.0.0.1:8000`.

## Test it without the website

In a second Terminal window (use any short video you have):

```
curl http://localhost:8000/api/health
curl -F video=@/path/to/clip.mp4 http://localhost:8000/api/analyze
```

You should get JSON with `fileName`, `sha256`, `duration`, `fps` and `score: 50`.

To check the hash is right, run `shasum -a 256 /path/to/clip.mp4` and compare.

## Test links

```
yt-dlp --version
curl -X POST -H "Content-Type: application/json" -d '{"url":"https://EXAMPLE.COM/some-video.mp4"}' http://localhost:8000/api/analyze
```

Try a direct link to an .mp4 file first. Big sites (YouTube, Instagram and so on) may refuse downloads, ask for a login or change often. Keep yt-dlp up to date with `pip install -U yt-dlp`.

Safety check: this must be refused with "This link is not allowed.":

```
curl -X POST -H "Content-Type: application/json" -d '{"url":"http://127.0.0.1:8000/api/health"}' http://localhost:8000/api/analyze
```

Known limits: the link is checked before download, but a site could redirect to another address afterwards. Run the live server with no private services next to it, and keep `MAX_JOBS` low.

## Connect the website

1. In `frontend/js/config.js` set `API_BASE: 'http://localhost:8000'`.
2. In a third Terminal window: `cd frontend && python3 -m http.server 5500`
3. Open http://localhost:5500 and check a video. The Analysis page should show your video's real hash and length.

## Settings (environment variables)

- `MAX_UPLOAD_MB` (default 25): biggest upload accepted.
- `MAX_JOBS` (default 2): videos worked on at the same time.
- `MAX_LINK_MINUTES` (default 5): longest video accepted from a link.
- `DOWNLOAD_TIMEOUT_SEC` (default 120): longest a download may take.
- `ALLOWED_ORIGINS` (default `*`): fine for testing. Before going live, set it to your website address.

## After it works

Run `pip freeze > requirements.lock` so you remember the exact versions that worked.
