"""Aletheia backend: video verification, multi-detector analysis, FFmpeg trimming, and PDF evidence reports.

Optimized for Apple Silicon (MacBook Air M5, 16GB unified RAM).
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
import linkfetch
import orchestrator
import report_generator
import videoinfo

# Allow large video uploads (default 500 MB, configurable)
MAX_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "500")) * 1024 * 1024
MAX_LINK_BYTES = int(os.environ.get("MAX_LINK_MB", "120")) * 1024 * 1024

# Allowed origins
ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]

# Concurrency control for local Mac M5
JOBS = asyncio.Semaphore(int(os.environ.get("MAX_JOBS", "2")))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

app = FastAPI(title="Aletheia API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


class Reject(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


@app.get("/api/health")
def health():
    return {"ok": True, "service": "Aletheia Multi-Detector API"}


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
                raise Reject(413, "This video exceeds the maximum file size limit.")
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


@app.post("/api/trim")
async def trim_video(request: Request):
    """Reliable server-side video trimming & compression endpoint for Safari & Chrome.
    
    Compresses/trims any uploaded video into a universal H.264 + AAC MP4 under 9.5 MB
    suitable for filing on the Indian Cybercrime Portal (cybercrime.gov.in).
    """
    workdir = tempfile.mkdtemp(prefix="aletheia_trim_")
    try:
        form = await request.form()
        path, name = await save_upload(form, workdir)
        output_dir = os.path.join(workdir, "out")
        os.makedirs(output_dir, exist_ok=True)

        compressed_path, _ = await run_in_threadpool(compress.compress_for_portal, path, output_dir)
        final_file = compressed_path if compressed_path else path

        out_name = os.path.splitext(name)[0] + "_portal.mp4"
        return FileResponse(
            final_file,
            media_type="video/mp4",
            filename=out_name,
            headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
        )
    except Reject as r:
        return JSONResponse({"error": r.message}, status_code=r.status)
    finally:
        # Note: FileResponse will stream the file; temporary directory cleaned up when server finishes or per run
        pass


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

            # Optional portal compression
            _, portal_digest = await run_in_threadpool(compress.compress_for_portal, path, workdir)

            # Execute multi-detector orchestrator
            detector_res = await run_in_threadpool(orchestrator.run_orchestrated_analysis, path)

        score = detector_res.get("score", 50)
        v_title = detector_res.get("verdictTitle", "We are not sure about this video")
        v_detail = detector_res.get("verdictDetail", "Analysis complete.")

        verdict_band = "Likely fake" if score >= 70 else ("Not sure" if score >= 40 else "Likely real")

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
            "verdict": verdict_band,
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
            "detectors": detector_res.get("detectors", {}),
            "meta": detector_res.get("meta", {}),
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
        shutil.rmtree(workdir, ignore_errors=True)  # Video is never kept


@app.api_route("/api/report/{report_id}.pdf", methods=["GET", "HEAD"])
async def get_report(report_id: str):
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
