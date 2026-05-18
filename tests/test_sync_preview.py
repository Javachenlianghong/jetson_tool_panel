import unittest

from core.sync_preview import parse_sync_preview_output


class SyncPreviewTest(unittest.TestCase):
    def test_parse_sync_preview_counts_and_rows(self):
        result = parse_sync_preview_output([
            "Changed/new files: 2",
            "Deleted files    : 1",
            "  upload src/main.cpp",
            "  upload README.md",
            "  delete old.txt",
            "Dry run only; nothing uploaded.",
        ])

        self.assertEqual(result["changed"], 2)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["rows"][0]["action"], "upload")
        self.assertEqual(result["rows"][2]["path"], "old.txt")
        self.assertIn("待上传 2", result["summary"])

    def test_parse_empty_sync_preview(self):
        result = parse_sync_preview_output([
            "Changed/new files: 0",
            "Deleted files    : 0",
            "Dry run only; nothing uploaded.",
        ])

        self.assertEqual(result["total"], 0)
        self.assertIn("没有发现", result["summary"])


if __name__ == "__main__":
    unittest.main()
