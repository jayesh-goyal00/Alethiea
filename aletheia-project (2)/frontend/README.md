# Aletheia frontend

Plain HTML, CSS and JavaScript. No build step.

```
frontend/
  index.html        page markup (4 views: Check Video, Analysis Score, Report Incident, How It Works)
  css/style.css     all styles
  js/config.js      set API_BASE here
  js/api.js         the only file that talks to the backend
  js/app.js         navigation, validation, wizard, result rendering
```

## Run it

Open `index.html` in a browser, or serve the folder:

```
python3 -m http.server 5500
```

With `API_BASE: ''` the app runs in demo mode (fixed 88% result).
Set `API_BASE` in `js/config.js` (for example `http://localhost:8000`) to use your backend.
If the backend is on another origin, enable CORS for the frontend's origin.

## Backend contract

### POST /api/analyze

Links can be from any website, so the backend must download the video itself (for example with yt-dlp).

Upload: `multipart/form-data` with the file in field `video` (up to 9.6 MB). The app trims larger files to 9.6 MB in the browser (re-recorded as WEBM) before sending.
Link: `application/json` with `{ "url": "https://..." }`.

Return JSON:

```json
{
  "fileName": "incident_clip.mp4",
  "sha256": "9f2c41a7...c82e4",
  "fps": "29.97",
  "duration": "0:42",
  "score": 88,
  "checks": [
    { "label": "Pulse wave", "text": "Flat. No pulse pattern found.", "ok": false },
    { "label": "Face life signs", "text": "Skin looks computer-made.", "ok": false },
    { "label": "Heart rate signal", "text": "No clear heart rate found.", "ok": false }
  ],
  "reportUrl": "/api/report/abc123.pdf"
}
```

- `score` is 0 to 100. Under 40 shows Likely real, 40 to 69 Not sure, 70 and up Likely fake.
- `checks`, `verdictTitle`, `verdictDetail`, `reportUrl` and `sha256` are optional.
- `reportUrl`: the "Download Evidence Report" button opens it. Without it, the button prints the page.
- On an error, return a non-2xx status. The app shows "Could not check the video."

### Evidence report PDF should contain

File name and SHA-256 hash, video length and frames per second, the score and verdict,
the three check results, and the date and time of the check.

## Screenshots

`images/step-2.jpg` to `images/step-5.jpg` are the annotated portal screenshots shown in the filing steps
(red boxes mark what to click or fill). Replace a file with the same name to update it.

## Notes

- The portal takes files up to 10 MB, so the app trims videos to 9.6 MB in the browser and offers the result as a download.
  Output is MP4 where the browser supports it, otherwise WEBM. Check that the portal accepts the format you get.
- The portal description is written in Report Incident, step 1, from the person's own answers (what happened, where and when,
  their own words, whether money is demanded). It is built in `buildDesc()` in `js/app.js`. It does not contain the score,
  verdict or hash. The portal allows 100 to 500 characters, so the text box is capped at 500 and warns under 100.
  The person can edit the text freely; "Reset to my answers" rebuilds it.
