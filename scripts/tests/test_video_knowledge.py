import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "video_knowledge.py"
SPEC = importlib.util.spec_from_file_location("video_knowledge", SCRIPT)
vk = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = vk
SPEC.loader.exec_module(vk)


class VideoKnowledgeTests(unittest.TestCase):
    def test_extracts_url_from_share_text(self):
        text = "3.21 复制打开抖音，看看作品 https://v.douyin.com/abc123/ 口令"
        self.assertEqual(vk.extract_url(text), "https://v.douyin.com/abc123/")

    def test_identifies_supported_platforms(self):
        self.assertEqual(vk.identify_platform("https://v.douyin.com/x/"), "douyin")
        self.assertEqual(vk.identify_platform("https://www.bilibili.com/video/BV1x"), "bilibili")
        self.assertEqual(vk.identify_platform("https://b23.tv/x"), "bilibili")

    def test_slug_is_windows_safe(self):
        self.assertEqual(vk.slugify('A/B:C*D? "test"'), "A-B-C-D- -test")

    def test_parses_and_deduplicates_srt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.srt"
            path.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\n你好\n\n"
                "2\n00:00:02,000 --> 00:00:03,500\n你好\n\n"
                "3\n00:00:04,000 --> 00:00:05,000\n世界\n",
                encoding="utf-8",
            )
            cues = vk.parse_subtitle(path)
            self.assertEqual([cue.text for cue in cues], ["你好", "世界"])
            self.assertEqual(cues[0].end, 3.5)

    def test_duplicate_by_platform_id(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            item = raw / "douyin" / "123"
            item.mkdir(parents=True)
            manifest = {"platform": "douyin", "video_id": "123", "note_name": "已有笔记"}
            (item / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            info = vk.SourceInfo(platform="douyin", original_input="x", video_id="123")
            self.assertEqual(vk.find_duplicate(raw, info)["note_name"], "已有笔记")

    def test_transcript_preserves_timestamps(self):
        info = vk.SourceInfo(platform="local", original_input="x", title="示例")
        text = vk.transcript_markdown(info, [vk.Cue(65, 66, "原话")], "funasr-paraformer", "2026-08-16T12:00:00+08:00")
        self.assertIn("[00:01:05] 原话", text)
        self.assertIn("status: raw", text)

    def test_note_yaml_escapes_metadata(self):
        template = (SCRIPT.parents[1] / "vault" / "system" / "templates" / "video-knowledge.md").read_text(encoding="utf-8")
        info = vk.SourceInfo(platform="bilibili", original_input="x", title="标题", author='A "quoted" author')
        rendered = vk.render_note(template, info, "2026-08-16T12:00:00+08:00", "platform-subtitle", "talk", "[[raw/x]]", [], SCRIPT.parents[1])
        self.assertIn('author: "A \\"quoted\\" author"', rendered)
        self.assertNotIn("{{", rendered)

    def test_douyin_metadata_uses_first_caption_line(self):
        data = {
            "aweme_id": "123",
            "caption": "适合作为标题的第一行\n后续是完整简介\n#标签",
            "author": {"nickname": "作者"},
            "duration": 426435,
        }
        result = vk.normalized_douyin_metadata(data, "https://v.douyin.com/x/")
        self.assertEqual(result["title"], "适合作为标题的第一行")
        self.assertEqual(result["duration"], 426.435)
        self.assertEqual(result["webpage_url"], "https://www.douyin.com/video/123")

    def test_douyin_candidates_prefer_small_complete_rendition(self):
        data = {"video": {"play_addr": {"data_size": 30, "url_list": ["https://cdn.example/small.mp4"]},
                          "play_addr_h264": {"data_size": 100, "url_list": ["https://cdn.example/large.mp4"]}}}
        self.assertEqual(vk.douyin_video_candidates(data)[0], (30, "https://cdn.example/small.mp4"))

    def test_local_ingest_transaction_and_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "vault" / "system" / "templates").mkdir(parents=True)
            shutil.copy2(SCRIPT.parents[1] / "scripts" / "video-knowledge.config.json", root / "scripts" / "video-knowledge.config.json")
            shutil.copy2(SCRIPT.parents[1] / "vault" / "system" / "templates" / "video-knowledge.md",
                         root / "vault" / "system" / "templates" / "video-knowledge.md")
            media = root / "sample.wav"
            media.write_bytes(b"synthetic-test-audio")
            cues = [vk.Cue(0, 2, "这是用于验证事务式入库的测试讲话内容。")]
            with mock.patch.object(vk, "extract_audio", return_value=media), mock.patch.object(vk, "transcribe_funasr", return_value=cues):
                self.assertEqual(vk.ingest(root, str(media), "talk", "funasr-paraformer", False, False, None), 0)
                self.assertEqual(vk.ingest(root, str(media), "talk", "funasr-paraformer", False, False, None), 3)
            self.assertEqual(len(list((root / "vault" / "raw" / "video").rglob("manifest.json"))), 1)
            self.assertEqual(len(list((root / "vault" / "outputs" / "video-knowledge" / "notes").glob("*.md"))), 1)

    def test_manifest_output_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "vault" / "raw" / "video" / "local" / "1" / "x-transcript.md"
            note = root / "vault" / "outputs" / "video-knowledge" / "notes" / "x.md"
            transcript.parent.mkdir(parents=True)
            note.parent.mkdir(parents=True)
            transcript.write_text("# 标题 - 原始文字稿\n\n## 文字稿\n\n[00:00:00] " + "内容" * 50, encoding="utf-8")
            note.write_text("# 标题\n\n## 基本信息\n\n## 原始文字稿\n\n[[raw]]\n" + "内容" * 50, encoding="utf-8")
            manifest = {"transcript_path": str(transcript.relative_to(root)), "note_path": str(note.relative_to(root))}
            result = vk.validate_manifest_outputs(root, manifest)
            self.assertEqual(result["note_path"], str(note.relative_to(root)))

    def test_manifest_output_validation_rejects_missing_note(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "transcript.md"
            transcript.write_text("## 文字稿\n" + "内容" * 50, encoding="utf-8")
            with self.assertRaises(vk.PipelineError):
                vk.validate_manifest_outputs(root, {"transcript_path": "transcript.md", "note_path": "missing.md"})


if __name__ == "__main__":
    unittest.main()
