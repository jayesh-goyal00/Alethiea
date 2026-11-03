"""Aletheia backend: video verification, pulse detection, compression, and PDF evidence reports.

Run:  uvicorn main:app --reload --port 8000
"""
import asyncio
import os
import re
import shutil
import tempfile
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

import compress
import detector_composite
import linkfetch
import report_generator
import videoinfo

MAX_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_LINK_BYTES = int(os.environ.get("MAX_LINK_MB", "60")) * 1024 * 1024
# For local testing "*" is fine. Before going live, set ALLOWED_ORIGINS to your website address.
ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]
# How many videos are worked on at the same time. Keep low on a small free server.
JOBS = asyncio.Semaphore(int(os.environ.get("MAX_JOBS", "2")))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

app = FastAPI(title="Aletheia API")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])


class Reject(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


@app.get("/api/health")
def health():
    return {"ok": True}


async def save_upload(form, workdir):
    upload = form.get("video")
    if upload is None or not hasattr(upload, "read"):
        raise Reject(400, "No video file was sent.")
    name = videoinfo.safe_name(upload.filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in videoinfo.ALLOWED_EXT:
        raise Reject(415, "This file type is not supported. Use MP4, MOV or WEBM.")
    path = os.path.join(workdir, "upload" + ext)
    size = 0
    with open(path, "wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                raise Reject(413, "This video is too large.")
            out.write(chunk)
    return path, name


async def fetch_link(body, workdir):
    url = body.get("url") if isinstance(body, dict) else None
    try:
        url = await run_in_threadpool(linkfetch.check_url, url)
        path = await run_in_threadpool(linkfetch.download, url, workdir, MAX_LINK_BYTES)
    except videoinfo.VideoError as e:
        raise Reject(422, str(e))
    return path, url[:300]


@app.post("/api/analyze")
async def analyze(request: Request):
    ctype = request.headers.get("content-type", "")
    workdir = tempfile.mkdtemp(prefix="aletheia_")
    try:
        async with JOBS:
            if ctype.startswith("application/json"):
                try:
                    body = await request.json()
                except ValueError:
                    raise Reject(400, "The request was not valid.")
                path, label = await fetch_link(body, workdir)
            elif ctype.startswith("multipart/form-data"):
                path, label = await save_upload(await request.form(), workdir)
            else:
                raise Reject(415, "Send a video file or a link.")

            try:
                info = await run_in_threadpool(videoinfo.probe, path)
            except videoinfo.VideoError as e:
                raise Reject(422, str(e))

            digest = await run_in_threadpool(videoinfo.sha256_of, path)

            # Check if video needs compression under 9.5 MB for the portal
            _, portal_digest = await run_in_threadpool(compress.compress_for_portal, path, workdir)

            # Run composite detector (pulse rPPG + 2D FFT spectral artifacts + boundary blending)
            detector_res = await run_in_threadpool(detector_composite.analyze_video, path)

        score = detector_res.get("score", 50)
        if score >= 70:
            verdict = "Likely fake"
            v_title = "This video looks likely fake"
            v_detail = "Multiple suspicious signs were found in the video."
        elif score >= 40:
            verdict = "Not sure"
            v_title = "We are not sure about this video"
            v_detail = "The pulse signal is weak or unclear. Poor lighting, compression, or alterations can cause this."
        else:
            verdict = "Likely real"
            v_title = "This video looks real"
            v_detail = "A natural pulse signal was found in the face."

        # Generate Evidence Report PDF
        report_id = uuid.uuid4().hex[:12]
        report_filename = f"{report_id}.pdf"
        report_path = os.path.join(REPORTS_DIR, report_filename)

        pdf_data = {
            "report_id": f"ALT-{report_id.upper()}",
            "file_name": label,
            "sha256_original": digest,
            "sha256_portal": portal_digest,
            "duration": info["duration"],
            "fps": info.get("fps", "N/A"),
            "score": score,
            "verdict": verdict,
            "checks": detector_res.get("checks", []),
        }

        try:
            await run_in_threadpool(report_generator.build_evidence_pdf, report_path, pdf_data)
            report_url = f"/api/report/{report_id}.pdf"
        except Exception:
            report_url = None

        result = {
            "fileName": label,
            "sha256": digest,
            "duration": info["duration"],
            "score": score,
            "verdictTitle": v_title,
            "verdictDetail": v_detail,
            "checks": detector_res.get("checks", []),
        }
        if portal_digest:
            result["sha256Portal"] = portal_digest
        if info.get("fps"):
            result["fps"] = info["fps"]
        if report_url:
            result["reportUrl"] = report_url

        return result
    except Reject as r:
        return JSONResponse({"error": r.message}, status_code=r.status)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)  # the video is never kept


@app.get("/api/report/{report_id}.pdf")
async def get_report(report_id: str):
    # Only allow safe hex characters in report_id
    if not re.match(r"^[a-zA-Z0-9_-]{1,32}$", report_id):
        return JSONResponse({"error": "Invalid report ID"}, status_code=400)
    pdf_path = os.path.join(REPORTS_DIR, f"{report_id}.pdf")
    if not os.path.isfile(pdf_path):
        return JSONResponse({"error": "Report not found or expired"}, status_code=404)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"Aletheia_Evidence_Report_{report_id}.pdf",
    )
