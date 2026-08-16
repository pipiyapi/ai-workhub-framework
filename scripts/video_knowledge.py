#!/usr/bin/env python3
"""Local video-to-knowledge pipeline for AI WorkHub.

The deterministic layer stops at a faithful transcript and a structured draft.
Codex performs semantic organization afterwards, without a paid summarization API.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable


URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+", re.I)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}
_FUNASR_MODELS: dict[str, Any] = {}


class PipelineError(RuntimeError):
    pass


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class SourceInfo:
    platform: str
    original_input: str
    original_url: str = ""
    canonical_url: str = ""
    video_id: str = ""
    title: str = ""
    author: str = ""
    published: str = ""
    duration_seconds: float = 0.0
    source_sha256: str = ""


def now_local() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load_config(root: Path) -> dict[str, Any]:
    path = root / "scripts" / "video-knowledge.config.json"
    return json.loads(path.read_text(encoding="utf-8"))


def extract_url(text: str) -> str:
    match = URL_RE.search(text or "")
    if not match:
        return ""
    return match.group(0).rstrip(".,;:!?，。；：！？、）)]}")


def identify_platform(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
    if host.endswith("douyin.com") or host.endswith("iesdouyin.com"):
        return "douyin"
    if host.endswith("bilibili.com") or host.endswith("b23.tv"):
        return "bilibili"
    if host.endswith("youtube.com") or host.endswith("youtu.be"):
        return "youtube"
    return "generic"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def url_hash(url: str) -> str:
    normalized = url.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def slugify(value: str, fallback: str = "video") -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "-", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[-. ]+$", "", value)
    return (value[:80].strip() or fallback)


def command_path(name: str) -> str | None:
    executable_name = name + ".exe" if os.name == "nt" and not name.endswith(".exe") else name
    bundled = Path(__file__).resolve().parent / "tools" / name / executable_name
    if bundled.exists():
        return str(bundled)
    beside_python = Path(sys.executable).parent / executable_name
    if beside_python.exists():
        return str(beside_python)
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg  # type: ignore
            return imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            return None
    return None


def run_command(args: list[str], *, timeout: int = 1800, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, text=True, encoding="utf-8", errors="replace",
                                capture_output=True, timeout=timeout, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PipelineError(f"命令无法执行：{Path(args[0]).name}: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-1600:]
        raise PipelineError(f"{Path(args[0]).name} 失败（exit {result.returncode}）：{detail}")
    return result


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remain = divmod(total, 3600)
    minutes, secs = divmod(remain, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_clock(value: str) -> float:
    value = value.replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def parse_subtitle(path: Path) -> list[Cue]:
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    content = content.replace("\r\n", "\n")
    pattern = re.compile(
        r"(?m)^(?:\d+\s*\n)?\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
        r"(\d{1,2}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)", re.S
    )
    cues: list[Cue] = []
    for start, end, body in pattern.findall(content):
        body = re.sub(r"<[^>]+>", "", body)
        body = html.unescape(re.sub(r"\s+", " ", body)).strip()
        if body:
            cues.append(Cue(parse_clock(start), parse_clock(end), body))
    return dedupe_adjacent_cues(cues)


def dedupe_adjacent_cues(cues: list[Cue]) -> list[Cue]:
    result: list[Cue] = []
    for cue in cues:
        if result and cue.text == result[-1].text:
            result[-1].end = max(result[-1].end, cue.end)
        else:
            result.append(cue)
    return result


def transcript_markdown(info: SourceInfo, cues: list[Cue], method: str, captured: str) -> str:
    title = info.title or info.video_id or "视频原始文字稿"
    yaml_string = lambda value: json.dumps(str(value or ""), ensure_ascii=False)
    lines = [
        "---", "type: external-video-transcript", "ownership: external",
        "source_type: video", f"status: raw", f"platform: {yaml_string(info.platform)}",
        f"video_id: {yaml_string(info.video_id)}", f"source: {yaml_string(info.canonical_url or info.original_url)}",
        f"original_url: {yaml_string(info.original_url)}", f"title: {yaml_string(title)}",
        f"author: {yaml_string(info.author)}", f"published: {yaml_string(info.published)}",
        f"captured: {yaml_string(captured)}", f"duration_seconds: {round(info.duration_seconds, 3)}",
        f"transcript_method: {yaml_string(method)}", "source_complete: true", "---", "",
        f"# {title} - 原始文字稿", "", "## 来源", "",
        f"- 平台：{info.platform}", f"- 作者：{info.author or '未知'}",
        f"- 原始链接：{info.canonical_url or info.original_url or '本地文件'}",
        f"- 获取方式：{method}", "", "## 文字稿", "",
    ]
    lines.extend(f"[{format_timestamp(cue.start)}] {cue.text}" for cue in cues)
    return "\n".join(lines).rstrip() + "\n"


def scan_manifests(raw_root: Path) -> Iterable[tuple[Path, dict[str, Any]]]:
    if not raw_root.exists():
        return []
    found = []
    for path in raw_root.rglob("manifest.json"):
        try:
            found.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    return found


def find_duplicate(raw_root: Path, info: SourceInfo) -> dict[str, Any] | None:
    input_hashes = {url_hash(x) for x in (info.original_url, info.canonical_url) if x}
    for _, manifest in scan_manifests(raw_root):
        if info.platform and info.video_id and manifest.get("platform") == info.platform and manifest.get("video_id") == info.video_id:
            return manifest
        if info.source_sha256 and manifest.get("source_sha256") == info.source_sha256:
            return manifest
        saved_hashes = set(manifest.get("url_hashes") or [])
        if input_hashes & saved_hashes:
            return manifest
    return None


def cookie_args(browser: str | None, root: Path) -> list[str]:
    if browser:
        return ["--cookies-from-browser", browser]
    cookie_file = os.environ.get("VIDEO_KNOWLEDGE_COOKIE_FILE", "").strip()
    if not cookie_file:
        return []
    path = Path(cookie_file).expanduser().resolve()
    vault = (root / "vault").resolve()
    if path == vault or vault in path.parents:
        raise PipelineError("Cookie 文件禁止保存在 Obsidian Vault 内；请移到 Vault 外并仅通过环境变量引用。")
    return ["--cookies", str(path)]


def cookie_file_path(root: Path) -> str:
    args = cookie_args(None, root)
    return args[1] if args else ""


def metadata_from_ytdlp(url: str, browser: str | None, root: Path) -> dict[str, Any]:
    executable = command_path("yt-dlp")
    if not executable:
        return {}
    try:
        result = run_command([executable, "--dump-single-json", "--skip-download", "--no-playlist",
                              *cookie_args(browser, root), url], check=False, timeout=180)
    except PipelineError:
        return {}
    if result.returncode:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def douyin_resolver_endpoint(config: dict[str, Any]) -> str:
    override = os.environ.get("VIDEO_KNOWLEDGE_DOUYIN_RESOLVER_URL", "").strip()
    return override or str(config.get("douyin_resolver_url") or "").strip()


def request_douyin_resolver(url: str, config: dict[str, Any]) -> dict[str, Any]:
    """Resolve Douyin metadata outside the local Douyin network path.

    The endpoint is deliberately configurable. It must implement the open-source
    Douyin_TikTok_Download_API `hybrid/video_data` response shape.
    """
    endpoint = douyin_resolver_endpoint(config)
    if not endpoint:
        return {}
    try:
        import requests  # type: ignore
    except ImportError as exc:
        raise PipelineError("远程抖音解析器需要 requests；请重新运行安装脚本。") from exc
    try:
        response = requests.get(endpoint, params={"url": url, "minimal": "false"}, timeout=90)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise PipelineError(f"远程抖音解析失败：{exc}") from exc
    if not isinstance(payload, dict) or int(payload.get("code") or 0) != 200 or not isinstance(payload.get("data"), dict):
        raise PipelineError(f"远程抖音解析器未返回有效视频数据：{str(payload)[:500]}")
    return payload["data"]


def request_douyin_creator_posts(sec_user_id: str, count: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    endpoint = str(config.get("douyin_creator_posts_url") or "").strip()
    if not endpoint:
        raise PipelineError("未配置抖音账号作品列表解析端点。")
    try:
        import requests  # type: ignore
        response = requests.get(endpoint, params={"sec_user_id": sec_user_id, "max_cursor": 0, "count": count}, timeout=90)
        response.encoding = "utf-8"
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise PipelineError(f"获取抖音账号作品列表失败：{exc}") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    items = data.get("aweme_list") if isinstance(data, dict) else None
    if int(payload.get("code") or 0) != 200 or not isinstance(items, list):
        raise PipelineError(f"抖音账号作品列表返回格式无效：{str(payload)[:500]}")
    return [item for item in items if isinstance(item, dict)]


def normalized_douyin_metadata(data: dict[str, Any], original_url: str) -> dict[str, Any]:
    video_id = str(data.get("aweme_id") or "")
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    duration_ms = float(data.get("duration") or 0)
    created = int(data.get("create_time") or 0)
    published = dt.datetime.fromtimestamp(created).strftime("%Y%m%d") if created else ""
    caption = str(data.get("caption") or data.get("desc") or "").strip()
    # Douyin's caption often contains the whole post body and hashtags. Keep the
    # first non-empty line as the note title; the transcript remains the fact layer.
    title = next((line.strip() for line in caption.splitlines() if line.strip()), caption)
    return {
        "id": video_id,
        "title": title,
        "uploader": str(author.get("nickname") or "").strip(),
        "webpage_url": f"https://www.douyin.com/video/{video_id}" if video_id else original_url,
        "original_url": original_url,
        "duration": duration_ms / 1000 if duration_ms > 10000 else duration_ms,
        "upload_date": published,
    }


def metadata_for_source(info: SourceInfo, browser: str | None, root: Path, config: dict[str, Any]) -> dict[str, Any]:
    if info.platform == "douyin" and douyin_resolver_endpoint(config):
        try:
            return normalized_douyin_metadata(request_douyin_resolver(info.original_url, config), info.original_url)
        except PipelineError:
            pass
    return metadata_from_ytdlp(info.original_url, browser, root)


def apply_metadata(info: SourceInfo, data: dict[str, Any]) -> None:
    if not data:
        return
    info.video_id = str(data.get("id") or info.video_id)
    info.title = str(data.get("title") or data.get("description") or info.title).strip()
    info.author = str(data.get("uploader") or data.get("channel") or data.get("creator") or info.author).strip()
    info.canonical_url = str(data.get("webpage_url") or data.get("original_url") or info.original_url)
    info.duration_seconds = float(data.get("duration") or 0)
    upload = str(data.get("upload_date") or "")
    info.published = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload) == 8 else upload


def try_platform_subtitles(url: str, temp: Path, browser: str | None, root: Path) -> tuple[Path | None, str]:
    executable = command_path("yt-dlp")
    if not executable:
        return None, ""
    base = [executable, "--skip-download", "--no-playlist", "--sub-format", "srt/vtt/best",
            "--sub-langs", "zh-Hans,zh-CN,zh,zh-Hant,en", "-o", str(temp / "subtitle.%(ext)s"),
            *cookie_args(browser, root)]
    for flag, method in (("--write-subs", "platform-subtitle"), ("--write-auto-subs", "platform-auto-subtitle")):
        try:
            run_command([*base, flag, url], check=False, timeout=300)
        except PipelineError:
            return None, ""
        candidates = sorted(p for p in temp.iterdir() if p.suffix.lower() in SUBTITLE_EXTENSIONS)
        for candidate in candidates:
            if parse_subtitle(candidate):
                return candidate, method
    return None, ""


def find_media(directory: Path) -> Path | None:
    candidates = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS]
    return max(candidates, key=lambda p: p.stat().st_size) if candidates else None


def douyin_video_candidates(data: dict[str, Any]) -> list[tuple[int, str]]:
    """Return deduplicated CDN URLs ordered from smallest usable rendition."""
    video = data.get("video") if isinstance(data.get("video"), dict) else {}
    addresses: list[dict[str, Any]] = []
    for key in ("play_addr", "play_addr_265", "play_addr_h264", "download_addr"):
        value = video.get(key)
        if isinstance(value, dict):
            addresses.append(value)
    for bitrate in video.get("bit_rate") or []:
        if isinstance(bitrate, dict) and isinstance(bitrate.get("play_addr"), dict):
            addresses.append(bitrate["play_addr"])
    candidates: dict[str, int] = {}
    for address in addresses:
        size = int(address.get("data_size") or 0)
        for candidate in address.get("url_list") or []:
            url = str(candidate)
            if url.startswith("https://") and "douyin.com/aweme/" not in url:
                candidates[url] = size
    return sorted(((size, url) for url, size in candidates.items()), key=lambda item: (item[0] <= 0, item[0]))


def download_from_douyin_data(info: SourceInfo, temp: Path, config: dict[str, Any], data: dict[str, Any]) -> Path:
    try:
        import requests  # type: ignore
    except ImportError as exc:
        raise PipelineError("远程抖音下载器需要 requests；请重新运行安装脚本。") from exc
    apply_metadata(info, normalized_douyin_metadata(data, info.original_url))
    candidates = douyin_video_candidates(data)
    if not candidates:
        raise PipelineError("远程抖音解析成功，但没有返回可用的 CDN 视频地址。")
    errors: list[str] = []
    output = temp / "source.mp4"
    for expected_size, url in candidates:
        try:
            with requests.get(url, stream=True, timeout=(15, 45), headers={"User-Agent": "Mozilla/5.0"}) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if content_type and "video" not in content_type and "octet-stream" not in content_type:
                    raise PipelineError(f"CDN 返回了非视频内容：{content_type}")
                with output.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            actual_size = output.stat().st_size if output.exists() else 0
            if actual_size < 1024 * 1024:
                raise PipelineError(f"下载文件过小：{actual_size} bytes")
            if expected_size and actual_size < min(expected_size * 0.8, expected_size - 1024 * 1024):
                raise PipelineError(f"下载不完整：预期约 {expected_size} bytes，实际 {actual_size} bytes")
            ffmpeg = command_path("ffmpeg")
            if ffmpeg:
                probe = run_command(
                    [ffmpeg, "-v", "error", "-i", str(output), "-map", "0:a:0", "-t", "1", "-f", "null", "-"],
                    check=False,
                    timeout=60,
                )
                if probe.returncode != 0:
                    detail = (probe.stderr or probe.stdout).strip()[-500:]
                    raise PipelineError(f"CDN 文件没有可解码的音频流：{detail}")
            return output
        except Exception as exc:
            output.unlink(missing_ok=True)
            errors.append(str(exc))
    raise PipelineError("所有远程 CDN 地址均下载失败：" + " | ".join(errors[-3:]))


def download_from_douyin_resolver(info: SourceInfo, temp: Path, config: dict[str, Any]) -> Path:
    return download_from_douyin_data(info, temp, config, request_douyin_resolver(info.original_url, config))


def download_media(info: SourceInfo, temp: Path, config: dict[str, Any], browser: str | None, root: Path,
                   resolved_data: dict[str, Any] | None = None) -> Path:
    errors: list[str] = []
    for downloader in config["downloaders"].get(info.platform, config["downloaders"]["generic"]):
        if downloader == "douyin-resolver":
            try:
                if resolved_data:
                    return download_from_douyin_data(info, temp, config, resolved_data)
                return download_from_douyin_resolver(info, temp, config)
            except PipelineError as exc:
                errors.append(f"douyin-resolver: {exc}")
                continue
        executable = command_path(downloader)
        if not executable:
            errors.append(f"{downloader}: 未安装")
            continue
        if downloader == "yt-dlp":
            args = [executable, "--no-playlist", "--merge-output-format", "mp4", "-o", str(temp / "source.%(ext)s"),
                    *cookie_args(browser, root), info.original_url]
        elif downloader == "lux":
            args = [executable, "-o", str(temp), "-O", "source"]
            cookie_file = cookie_file_path(root)
            if cookie_file:
                args += ["-c", cookie_file]
            args.append(info.original_url)
        else:
            continue
        try:
            result = run_command(args, check=False, timeout=1800)
        except PipelineError as exc:
            errors.append(f"{downloader}: {exc}")
            continue
        media = find_media(temp)
        if result.returncode == 0 and media:
            return media
        errors.append(f"{downloader}: {(result.stderr or result.stdout).strip()[-500:]}")
    raise PipelineError("所有免费本地下载器均失败。\n" + "\n".join(errors))


def extract_embedded_subtitle(media: Path, temp: Path) -> Path | None:
    ffmpeg = command_path("ffmpeg")
    if not ffmpeg or media.suffix.lower() in AUDIO_EXTENSIONS:
        return None
    output = temp / "embedded.srt"
    result = run_command([ffmpeg, "-v", "error", "-i", str(media), "-map", "0:s:0", "-y", str(output)], check=False)
    return output if result.returncode == 0 and output.exists() and parse_subtitle(output) else None


def extract_audio(media: Path, temp: Path) -> Path:
    if media.suffix.lower() == ".wav":
        return media
    ffmpeg = command_path("ffmpeg")
    if not ffmpeg:
        raise PipelineError("缺少 FFmpeg，无法提取供本地 ASR 使用的音频。")
    output = temp / "audio-16k-mono.wav"
    run_command([ffmpeg, "-v", "error", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(output)])
    return output


def clean_asr_text(value: str) -> str:
    return re.sub(r"<\|[^|]+\|>", "", value or "").strip()


def transcribe_funasr(audio: Path, backend: str) -> list[Cue]:
    try:
        from funasr import AutoModel  # type: ignore
    except ImportError as exc:
        raise PipelineError("未安装 FunASR。请先运行 scripts/setup-video-knowledge.ps1。") from exc
    model = _FUNASR_MODELS.get(backend)
    if model is None:
        if backend == "funasr-sensevoice":
            model = AutoModel(model="iic/SenseVoiceSmall", vad_model="fsmn-vad", device="cpu", disable_update=True)
        else:
            model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc",
                              device="cpu", disable_update=True)
        _FUNASR_MODELS[backend] = model
    result = model.generate(input=str(audio), batch_size_s=300, sentence_timestamp=True)
    item = result[0] if isinstance(result, list) and result else result
    if not isinstance(item, dict):
        raise PipelineError("FunASR 返回了无法识别的结果格式。")
    cues: list[Cue] = []
    for sentence in item.get("sentence_info") or []:
        text = clean_asr_text(str(sentence.get("text") or ""))
        if text:
            cues.append(Cue(float(sentence.get("start") or 0) / 1000, float(sentence.get("end") or 0) / 1000, text))
    if not cues:
        text = clean_asr_text(str(item.get("text") or ""))
        if text:
            cues = [Cue(0, 0, text)]
    if not cues:
        raise PipelineError("ASR 完成但没有得到有效讲话内容。")
    return cues


def average_hash(path: Path) -> int | None:
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as image:
            pixels = list(image.convert("L").resize((8, 8)).getdata())
    except (ImportError, OSError):
        return None
    mean = sum(pixels) / len(pixels)
    return sum((1 << index) for index, value in enumerate(pixels) if value >= mean)


def extract_keyframes(media: Path, output: Path, threshold: float, max_distance: int) -> list[tuple[Path, float, str]]:
    ffmpeg = command_path("ffmpeg")
    if not ffmpeg or media.suffix.lower() in AUDIO_EXTENSIONS:
        return []
    output.mkdir(parents=True, exist_ok=True)
    pattern = output / "frame_%05d.jpg"
    result = run_command([ffmpeg, "-hide_banner", "-i", str(media), "-vf", f"select=gt(scene\\,{threshold}),showinfo",
                          "-fps_mode", "vfr", "-q:v", "2", "-y", str(pattern)], check=False, timeout=1800)
    times = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", result.stderr)]
    kept: list[tuple[Path, float, str]] = []
    hashes: list[int] = []
    for index, path in enumerate(sorted(output.glob("frame_*.jpg"))):
        digest = average_hash(path)
        if digest is not None and any((digest ^ old).bit_count() <= max_distance for old in hashes):
            path.unlink()
            continue
        if digest is not None:
            hashes.append(digest)
        timestamp = times[index] if index < len(times) else 0.0
        kept.append((path, timestamp, ""))
    return kept


def apply_ocr(frames: list[tuple[Path, float, str]]) -> list[tuple[Path, float, str]]:
    try:
        from rapidocr import RapidOCR  # type: ignore
    except ImportError as exc:
        raise PipelineError("已请求 OCR，但 RapidOCR 未安装。请运行 setup-video-knowledge.ps1。") from exc
    engine = RapidOCR()
    enriched = []
    for path, timestamp, _ in frames:
        result = engine(str(path))
        texts: list[str] = []
        boxes = getattr(result, "txts", None)
        if boxes:
            texts = [str(x).strip() for x in boxes if str(x).strip()]
        enriched.append((path, timestamp, " / ".join(texts)))
    return enriched


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def render_note(template: str, info: SourceInfo, captured: str, method: str, mode: str,
                transcript_link: str, frames: list[tuple[Path, float, str]], root: Path) -> str:
    frame_lines = []
    for path, timestamp, ocr in frames:
        relative = path.relative_to(root / "vault").as_posix()
        frame_lines.append(f"### {format_timestamp(timestamp)}\n\n![[{relative}]]")
        if ocr:
            frame_lines.append(f"\nOCR：{ocr}")
    source_link = info.canonical_url or info.original_url or "本地文件"
    replacements = {
        "TITLE": info.title or info.video_id or "视频知识笔记", "SOURCE_LINK": source_link,
        "PLATFORM": info.platform, "VIDEO_ID": info.video_id, "AUTHOR": info.author or "未知",
        "PUBLISHED": info.published or "未知", "CAPTURED": captured, "DURATION_SECONDS": str(round(info.duration_seconds, 3)),
        "DURATION_DISPLAY": format_timestamp(info.duration_seconds), "PROCESSING_MODE": mode, "TRANSCRIPT_METHOD": method,
        "KEY_FRAMES": "\n\n".join(frame_lines) if frame_lines else "本次为 Talk / Podcast 模式，或未检测到有意义的场景变化。",
        "TRANSCRIPT_LINK": transcript_link,
        "SOURCE_YAML": json.dumps(source_link, ensure_ascii=False),
        "PLATFORM_YAML": json.dumps(info.platform, ensure_ascii=False),
        "VIDEO_ID_YAML": json.dumps(info.video_id, ensure_ascii=False),
        "AUTHOR_YAML": json.dumps(info.author or "未知", ensure_ascii=False),
        "PUBLISHED_YAML": json.dumps(info.published or "未知", ensure_ascii=False),
        "CAPTURED_YAML": json.dumps(captured, ensure_ascii=False),
        "PROCESSING_MODE_YAML": json.dumps(mode, ensure_ascii=False),
        "TRANSCRIPT_METHOD_YAML": json.dumps(method, ensure_ascii=False),
    }
    for key, value in replacements.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def resolve_input(value: str) -> tuple[SourceInfo, Path | None]:
    possible_path = Path(value.strip().strip('"')).expanduser()
    if possible_path.exists() and possible_path.is_file():
        resolved = possible_path.resolve()
        return SourceInfo(platform="local", original_input=value, title=resolved.stem,
                          video_id=sha256_file(resolved)[:16], source_sha256=sha256_file(resolved)), resolved
    url = extract_url(value)
    if not url:
        raise PipelineError("输入中没有视频链接或有效本地文件。博主名称检索需由 Codex 先联网展示候选并等待确认。")
    return SourceInfo(platform=identify_platform(url), original_input=value, original_url=url, canonical_url=url), None


def doctor(root: Path) -> int:
    config = load_config(root)
    tools = {name: command_path(name) for name in ("ffmpeg", "ffprobe", "yt-dlp", "lux")}
    tool_status = {}
    for name, path in tools.items():
        if not path:
            tool_status[name] = {"path": None, "usable": False}
            continue
        probe_args = [path, "-version"] if name in ("ffmpeg", "ffprobe") else [path, "--version"]
        try:
            result = run_command(probe_args, check=False, timeout=20)
            tool_status[name] = {"path": path, "usable": result.returncode == 0}
        except PipelineError as exc:
            tool_status[name] = {"path": path, "usable": False, "error": str(exc)}
    modules = {}
    for name in ("funasr", "modelscope", "torch", "rapidocr", "PIL"):
        modules[name] = importlib.util.find_spec(name) is not None
    resolver_configured = bool(douyin_resolver_endpoint(config))
    report = {"python": sys.version.split()[0], "tools": tool_status, "python_modules": modules,
              "douyin_resolver_configured": resolver_configured,
              "ready_for_download": bool(resolver_configured or tool_status["yt-dlp"]["usable"] or tool_status["lux"]["usable"]),
              "ready_for_asr": bool(tool_status["ffmpeg"]["usable"] and modules["funasr"]),
              "ready_for_visual": bool(tool_status["ffmpeg"]["usable"]), "root": str(root)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready_for_download"] and report["ready_for_asr"] else 2


def inspect_input(root: Path, value: str, browser: str | None) -> int:
    config = load_config(root)
    info, local = resolve_input(value)
    if local is None:
        apply_metadata(info, metadata_for_source(info, browser, root, config))
    duplicate = find_duplicate(root / config["paths"]["raw_root"], info)
    print(json.dumps({"source": asdict(info), "duplicate": duplicate}, ensure_ascii=False, indent=2))
    return 3 if duplicate else 0


def validate_manifest_outputs(root: Path, manifest: dict[str, Any]) -> dict[str, str]:
    """Verify the two durable outputs before reporting an ingest as complete."""
    result: dict[str, str] = {}
    for key in ("transcript_path", "note_path"):
        value = str(manifest.get(key) or "")
        if not value:
            raise PipelineError(f"manifest 缺少 {key}。")
        path = root / value
        if not path.is_file():
            raise PipelineError(f"入库完整性校验失败，文件不存在：{value}")
        if path.stat().st_size < 100:
            raise PipelineError(f"入库完整性校验失败，文件过小：{value}")
        result[key] = value
    transcript = (root / result["transcript_path"]).read_text(encoding="utf-8")
    note = (root / result["note_path"]).read_text(encoding="utf-8")
    if "## 文字稿" not in transcript or "原始文字稿" not in note:
        raise PipelineError("入库完整性校验失败，文字稿或知识笔记结构不完整。")
    return result


def manifest_for_video(root: Path, raw_root: Path, platform: str, video_id: str) -> dict[str, Any] | None:
    direct = raw_root / platform / slugify(video_id, "video") / "manifest.json"
    candidates = [direct] if direct.is_file() else raw_root.rglob("manifest.json")
    for path in candidates:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(manifest.get("platform") or "") == platform and str(manifest.get("video_id") or "") == video_id:
            validate_manifest_outputs(root, manifest)
            return manifest
    return None


def audit_outputs(root: Path) -> int:
    config = load_config(root)
    raw_root = root / config["paths"]["raw_root"]
    note_root = root / config["paths"]["note_root"]
    manifests = list(raw_root.rglob("manifest.json")) if raw_root.exists() else []
    errors: list[str] = []
    seen: dict[tuple[str, str], Path] = {}
    referenced_notes: set[Path] = set()
    for path in manifests:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            validate_manifest_outputs(root, manifest)
            key = (str(manifest.get("platform") or ""), str(manifest.get("video_id") or ""))
            if key[1] and key in seen:
                errors.append(f"重复视频 ID：{key[0]}:{key[1]}")
            seen[key] = path
            referenced_notes.add((root / str(manifest["note_path"])).resolve())
        except (OSError, json.JSONDecodeError, PipelineError, KeyError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
    notes = list(note_root.glob("*.md")) if note_root.exists() else []
    orphan_notes = [str(path.relative_to(root)) for path in notes if path.resolve() not in referenced_notes]
    temp_dirs = list(Path(tempfile.gettempdir()).glob("ai-workhub-video-*"))
    report = {"status": "ok" if not errors else "failed", "manifests": len(manifests),
              "notes": len(notes), "errors": errors, "orphan_notes": orphan_notes,
              "stale_temp_dirs": [str(path) for path in temp_dirs]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def ingest(root: Path, value: str, mode: str | None, asr_backend: str | None, keep_video: bool,
           enable_ocr: bool, browser: str | None, resolved_data: dict[str, Any] | None = None) -> int:
    config = load_config(root)
    mode = mode or config["default_mode"]
    asr_backend = asr_backend or config["default_asr_backend"]
    info, local = resolve_input(value)
    raw_root = root / config["paths"]["raw_root"]
    if local is None:
        metadata = normalized_douyin_metadata(resolved_data, info.original_url) if resolved_data else metadata_for_source(info, browser, root, config)
        apply_metadata(info, metadata)
    duplicate = find_duplicate(raw_root, info)
    if duplicate:
        print(f"该视频已经于 {duplicate.get('captured', '未知日期')} 加入知识库：[[{duplicate.get('note_name', '未知笔记')}]]")
        return 3

    captured = now_local()
    with tempfile.TemporaryDirectory(prefix="ai-workhub-video-") as temp_name:
        temp = Path(temp_name)
        media = local
        subtitle = None
        method = ""
        if local is None:
            # This workstation cannot reach Douyin webpages, while the configured
            # resolver can return CDN media. Avoid two guaranteed yt-dlp subtitle
            # timeouts; embedded subtitles are still checked after download.
            use_remote_douyin = info.platform == "douyin" and bool(douyin_resolver_endpoint(config))
            if not use_remote_douyin:
                subtitle, method = try_platform_subtitles(info.original_url, temp, browser, root)
            if not subtitle or keep_video or mode == "visual":
                media = download_media(info, temp, config, browser, root, resolved_data)
        if subtitle:
            cues = parse_subtitle(subtitle)
        else:
            if media is None:
                raise PipelineError("既没有可用字幕，也没有获得媒体文件。")
            embedded = extract_embedded_subtitle(media, temp)
            if embedded:
                cues, method = parse_subtitle(embedded), "embedded-subtitle"
            else:
                if asr_backend == "none":
                    raise PipelineError("没有可靠字幕，且 ASR 被禁用。")
                audio = extract_audio(media, temp)
                try:
                    cues = transcribe_funasr(audio, asr_backend)
                    method = asr_backend
                except PipelineError:
                    fallback = "funasr-sensevoice" if asr_backend == "funasr-paraformer" else ""
                    if not config.get("allow_asr_fallback") or not fallback:
                        raise
                    cues = transcribe_funasr(audio, fallback)
                    method = fallback
        if len("".join(c.text for c in cues).strip()) < 10:
            raise PipelineError("文字稿过短，未通过入库校验；没有写入 raw。")

        stable_id = info.video_id or info.source_sha256[:16] or url_hash(info.canonical_url or info.original_url)[:16]
        key = slugify(stable_id, "video")
        title_slug = slugify(info.title or stable_id)
        raw_final = raw_root / info.platform / key
        note_root = root / config["paths"]["note_root"]
        asset_final = root / config["paths"]["asset_root"] / f"{info.platform}-{key}"
        note_path = note_root / f"{title_slug}-{key[:10]}.md"
        transcript_name = f"{title_slug}-transcript.md"
        transcript_path = raw_final / transcript_name

        duplicate = find_duplicate(raw_root, info)
        if duplicate or raw_final.exists():
            duplicate = duplicate or {"captured": "未知日期", "note_name": note_path.stem}
            print(f"该视频已经于 {duplicate.get('captured')} 加入知识库：[[{duplicate.get('note_name')}]]")
            return 3

        frame_temp = temp / "frames"
        frames = extract_keyframes(media, frame_temp, float(config["scene_threshold"]), int(config["perceptual_hash_distance"])) if mode == "visual" and media else []
        if enable_ocr and frames:
            frames = apply_ocr(frames)
        if frames:
            asset_final.mkdir(parents=True, exist_ok=True)
            moved = []
            for path, timestamp, ocr in frames:
                target = asset_final / path.name
                shutil.copy2(path, target)
                moved.append((target, timestamp, ocr))
            frames = moved

        raw_stage = root / config["paths"]["note_root"] / f".raw-stage-{os.getpid()}-{key}"
        raw_stage.mkdir(parents=True, exist_ok=False)
        transcript_content = transcript_markdown(info, cues, method, captured)
        (raw_stage / transcript_name).write_text(transcript_content, encoding="utf-8", newline="\n")
        transcript_link = f"[[{transcript_path.relative_to(root / 'vault').with_suffix('').as_posix()}|原始文字稿]]"
        template = (root / config["paths"]["template"]).read_text(encoding="utf-8")
        note_content = render_note(template, info, captured, method, mode, transcript_link, frames, root)
        if len(transcript_content.encode("utf-8")) < 100 or "## 文字稿" not in transcript_content:
            raise PipelineError("暂存文字稿未通过结构校验；没有提交 raw。")
        if len(note_content.encode("utf-8")) < 100 or "原始文字稿" not in note_content:
            raise PipelineError("暂存知识笔记未通过结构校验；没有提交 raw。")
        manifest = {**asdict(info), "captured": captured, "processing_mode": mode, "transcript_method": method,
                    "url_hashes": sorted({url_hash(x) for x in (info.original_url, info.canonical_url) if x}),
                    "transcript_path": str(transcript_path.relative_to(root)), "note_path": str(note_path.relative_to(root)),
                    "note_name": note_path.stem, "key_frames": [str(p.relative_to(root)) for p, _, _ in frames]}
        (raw_stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        kept_media = ""
        media_target: Path | None = None
        if keep_video and media:
            media_root = root / config["paths"]["media_root"]
            media_root.mkdir(parents=True, exist_ok=True)
            media_target = media_root / f"{info.platform}-{key}{media.suffix.lower()}"
            shutil.copy2(media, media_target)
            kept_media = str(media_target)

        # Commit mutable output first and immutable raw last. If the final raw
        # rename fails, remove the new note so no successful-looking half item
        # remains. Raw is never edited after the rename.
        note_existed = note_path.exists()
        atomic_write(note_path, note_content)
        try:
            raw_final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(raw_stage, raw_final)
        except Exception:
            if not note_existed:
                note_path.unlink(missing_ok=True)
            if media_target:
                media_target.unlink(missing_ok=True)
            if frames and asset_final.exists():
                shutil.rmtree(asset_final, ignore_errors=True)
            raise
        validate_manifest_outputs(root, manifest)
        print(json.dumps({"status": "created", "note": str(note_path), "transcript": str(transcript_path),
                          "key_frames": len(frames), "kept_video": kept_media, "transcript_method": method}, ensure_ascii=False, indent=2))
    return 0


def batch_ingest(root: Path, batch_file: Path, mode: str | None, asr_backend: str | None,
                 keep_video: bool, enable_ocr: bool, browser: str | None) -> int:
    batch_file = batch_file.resolve()
    try:
        batch = json.loads(batch_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"无法读取批处理清单：{exc}") from exc
    items = batch.get("items")
    if not isinstance(items, list) or not items:
        raise PipelineError("批处理清单没有有效 items。")
    config = load_config(root)
    if len(items) > int(config.get("max_videos_per_task", 10)) and not batch.get("confirmed"):
        raise PipelineError("批量数量超过安全上限，清单必须记录 confirmed=true。")

    creator = batch.get("creator") if isinstance(batch.get("creator"), dict) else {}
    sec_user_id = str(creator.get("sec_user_id") or "")
    resolved_by_id: dict[str, dict[str, Any]] = {}
    if sec_user_id:
        creator_items = request_douyin_creator_posts(sec_user_id, max(20, len(items)), config)
        expected_author = str(creator.get("nickname") or "")
        for creator_item in creator_items:
            author = creator_item.get("author") if isinstance(creator_item.get("author"), dict) else {}
            if expected_author and str(author.get("nickname") or "") != expected_author:
                continue
            video_id = str(creator_item.get("aweme_id") or "")
            if video_id:
                resolved_by_id[video_id] = creator_item

    counts = {"created": 0, "existing": 0, "failed": 0}
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or not str(item.get("url") or "").strip():
            counts["failed"] += 1
            continue
        if item.get("status") in ("created", "existing"):
            status = str(item["status"])
            video_id = str(item.get("video_id") or "")
            item["attempts"] = int(item.get("attempts") or 0)
            manifest = manifest_for_video(root, root / config["paths"]["raw_root"], "douyin", video_id) if video_id else None
            if not manifest:
                item["status"] = "failed"
                item["error"] = "批次状态声称已完成，但找不到通过校验的 manifest 输出。"
                counts["failed"] += 1
            else:
                item["transcript_path"] = manifest["transcript_path"]
                item["note_path"] = manifest["note_path"]
                counts[status] += 1
            batch["updated_at"] = now_local()
            atomic_write(batch_file, json.dumps(batch, ensure_ascii=False, indent=2) + "\n")
            continue
        value = str(item["url"])
        video_id = str(item.get("video_id") or "")
        print(f"BATCH [{index}/{len(items)}] {item.get('video_id', '')} {item.get('title', '')}", flush=True)
        try:
            code = ingest(root, value, mode, asr_backend, keep_video, enable_ocr, browser,
                          resolved_by_id.get(video_id))
            status = "existing" if code == 3 else "created"
            item["status"] = status
            item["completed_at"] = now_local()
            item["attempts"] = int(item.get("attempts") or 0) + 1
            manifest = manifest_for_video(root, root / config["paths"]["raw_root"], "douyin", video_id) if video_id else None
            if manifest:
                item["transcript_path"] = manifest["transcript_path"]
                item["note_path"] = manifest["note_path"]
            item.pop("error", None)
            counts[status] += 1
        except PipelineError as exc:
            item["status"] = "failed"
            item["attempted_at"] = now_local()
            item["attempts"] = int(item.get("attempts") or 0) + 1
            item["error"] = str(exc)[-1200:]
            counts["failed"] += 1
            print(f"BATCH ERROR [{index}/{len(items)}]: {exc}", file=sys.stderr, flush=True)
        batch["updated_at"] = now_local()
        atomic_write(batch_file, json.dumps(batch, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "batch-complete", "batch_file": str(batch_file), **counts},
                     ensure_ascii=False, indent=2), flush=True)
    return 1 if counts["failed"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI WorkHub 本地视频知识流水线")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "audit", "inspect", "ingest", "batch-ingest"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", type=Path, required=True)
        if name in ("inspect", "ingest"):
            cmd.add_argument("--input", required=True)
            cmd.add_argument("--cookies-from-browser")
        if name in ("ingest", "batch-ingest"):
            cmd.add_argument("--mode", choices=("talk", "visual"))
            cmd.add_argument("--asr-backend", choices=("funasr-paraformer", "funasr-sensevoice", "none"))
            cmd.add_argument("--keep-video", action="store_true")
            cmd.add_argument("--enable-ocr", action="store_true")
        if name == "batch-ingest":
            cmd.add_argument("--batch-file", type=Path, required=True)
            cmd.add_argument("--cookies-from-browser")
    return parser


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    root = args.root.resolve()
    try:
        if args.command == "doctor":
            return doctor(root)
        if args.command == "audit":
            return audit_outputs(root)
        if args.command == "inspect":
            return inspect_input(root, args.input, args.cookies_from_browser)
        if args.command == "batch-ingest":
            return batch_ingest(root, args.batch_file, args.mode, args.asr_backend, args.keep_video,
                                args.enable_ocr, args.cookies_from_browser)
        return ingest(root, args.input, args.mode, args.asr_backend, args.keep_video, args.enable_ocr, args.cookies_from_browser)
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
