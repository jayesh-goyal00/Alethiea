"""Downloads a video from a link, safely. Uses the yt-dlp program."""
import glob
import ipaddress
import os
import socket
import subprocess
from urllib.parse import urlparse

from videoinfo import VideoError

MAX_MINUTES = int(os.environ.get("MAX_LINK_MINUTES", "5"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT_SEC", "120"))


def _public(ip_text):
    ip = ipaddress.ip_address(ip_text.split("%")[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global  # False for private, loopback, link-local, reserved and similar


def check_url(url, resolver=socket.getaddrinfo):
    """Raises VideoError unless the link is a normal public web address."""
    if not isinstance(url, str) or not url.strip() or len(url) > 2000:
        raise VideoError("Paste a full link starting with http:// or https://")
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise VideoError("Paste a full link starting with http:// or https://")
    if p.username or p.password:
        raise VideoError("Links with a user name or password are not allowed.")
    try:
        port = p.port
    except ValueError:
        raise VideoError("This link is not valid.")
    if port not in (None, 80, 443):
        raise VideoError("This link is not allowed.")
    try:
        infos = resolver(p.hostname, port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise VideoError("Could not find this website. Check the link.")
    addrs = {i[4][0] for i in infos}
    if not addrs or not all(_public(a) for a in addrs):
        raise VideoError("This link is not allowed.")
    return url.strip()


def download(url, workdir, max_bytes):
    """Downloads one video into workdir and returns its path. Raises VideoError if it fails."""
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "--quiet",
        "--max-filesize", str(max_bytes),
        "--match-filter", "duration <=? %d" % (MAX_MINUTES * 60),
        "--socket-timeout", "20",
        "--extractor-args", "youtube:player_client=android,ios",
        "--user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "-f", "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "--merge-output-format", "mp4",
        "-o", os.path.join(workdir, "download.%(ext)s"),
        "--", url,
    ]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp is not installed on the server.")
    except subprocess.TimeoutExpired:
        raise VideoError("The download took too long. Try a shorter video or upload the file.")
    files = [f for f in glob.glob(os.path.join(workdir, "download.*")) if not f.endswith((".part", ".ytdl"))]
    if run.returncode != 0 or not files:
        err = run.stderr.lower() if run.stderr else ""
        if "larger than" in err or "max-filesize" in err:
            raise VideoError("This video is too large. Choose a shorter clip or upload a smaller file.")
        if "sign in" in err or "bot" in err or "login" in err:
            raise VideoError("This platform requires a login or blocked automated access. Please download the clip and upload the file instead.")
        if "private" in err:
            raise VideoError("This video is private or unavailable.")
        raise VideoError("Could not download a video from this link. It may be restricted, too long, too large, or not a video. Try uploading the file directly.")
    path = files[0]
    if os.path.getsize(path) > max_bytes:
        raise VideoError("This video is too large.")
    return path
