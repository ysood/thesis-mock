"""Chunk integrity and index migration, without model downloads or paid calls."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import knowledge as kb


class ChunkingTests(unittest.TestCase):
    def test_short_provision_stays_whole(self):
        text = "(a) A health plan.\n(b) A health care clearinghouse."
        self.assertEqual(kb.split_legal_text(text, lambda s: len(s) <= 100), [text])

    def test_numbered_clauses_stay_intact_when_each_fits(self):
        text = "(a) First condition applies.\n(b) Second condition applies.\n(c) Third condition applies."
        chunks = kb.split_legal_text(text, lambda s: len(s.strip()) <= 40)
        self.assertEqual([s.strip() for s in chunks], text.splitlines())
        self.assertEqual("".join(chunks), text)

    def test_wrapped_paragraphs_are_not_split_at_soft_line_breaks(self):
        text = "First paragraph has\na wrapped line.\n\nSecond paragraph has\na wrapped line."
        chunks = kb.split_legal_text(text, lambda s: len(s.strip()) <= 40)
        self.assertEqual([s.strip() for s in chunks], text.split("\n\n"))
        self.assertEqual("".join(chunks), text)

    def test_oversized_clause_falls_back_to_complete_sentences(self):
        text = "(a) First sentence holds. Second sentence also holds. Third sentence holds."
        chunks = kb.split_legal_text(text, lambda s: len(s.strip()) <= 30)
        self.assertEqual([s.strip() for s in chunks],
                         ["(a) First sentence holds.", "Second sentence also holds.", "Third sentence holds."])
        self.assertEqual("".join(chunks), text)

    def test_oversized_sentence_or_word_loses_no_text(self):
        for text in ("One long sentence with several words and no punctuation",
                     "LongUnbrokenIdentifierWithNoSpaces"):
            with self.subTest(text=text):
                chunks = kb.split_legal_text(text, lambda s: len(s) <= 12)
                self.assertEqual("".join(chunks), text)
                self.assertTrue(all(0 < len(s) <= 12 for s in chunks))

    def test_chunks_keep_parent_identity_and_budget_for_heading_and_special_tokens(self):
        # A deterministic tokenizer double counts characters and two special tokens.
        tokenizer = Mock()
        tokenizer.encode.side_effect = lambda s: SimpleNamespace(ids=range(len(s) + 2))
        provisions = {
            "A": {"title": "Title", "text": "(a) First condition.\n(b) Second condition.", "regime": "IE"},
            "B": {"title": "Short", "text": "Body.", "regime": "HIPAA"},
        }
        with patch.object(kb, "embedding_tokenizer", return_value=tokenizer), \
             patch.object(kb, "provisions", return_value=provisions), \
             patch.object(kb, "EMBEDDING_TOKEN_LIMIT", 33):
            windows = list(kb.text_windows())
        self.assertEqual([w["window_id"] for w in windows], ["A#0", "A#1", "B#0"])
        for window in windows:
            parent = provisions[window["provision"]]
            self.assertEqual(window["title"], parent["title"])
            self.assertEqual(window["regime"], parent["regime"])
            self.assertEqual(window["kind"], "provision")
            self.assertTrue(window["text"].startswith(f"{window['provision']} {parent['title']}\n"))
            self.assertLessEqual(len(tokenizer.encode(window["text"]).ids), 33)

    def test_heading_that_cannot_fit_fails_instead_of_silently_truncating(self):
        tokenizer = Mock()
        tokenizer.encode.side_effect = lambda s: SimpleNamespace(ids=range(len(s) + 2))
        with patch.object(kb, "embedding_tokenizer", return_value=tokenizer), \
             patch.object(kb, "provisions", return_value={
                 "A": {"title": "A long title", "text": "Body", "regime": "IE"}}), \
             patch.object(kb, "EMBEDDING_TOKEN_LIMIT", 5):
            with self.assertRaisesRegex(ValueError, "ID and title"):
                list(kb.text_windows())


class IndexMigrationTests(unittest.TestCase):
    def setUp(self):
        self.windows = [{"window_id": "A#0", "provision": "A", "title": "Title", "regime": "IE",
                         "kind": "provision", "text": "A Title\nOriginal law."}]
        self.store = Mock()
        self.store._collection.metadata = {}
        self.store._collection.count.return_value = 1
        self.store._collection.modify.side_effect = self.set_metadata

    def set_metadata(self, *, metadata):
        self.store._collection.metadata = metadata

    def open(self):
        with patch("langchain_chroma.Chroma", return_value=self.store), \
             patch.object(kb, "text_windows", return_value=iter(self.windows)):
            return kb.open_store()

    def test_legacy_index_migrates_once_and_same_count_edit_rebuilds(self):
        self.open()  # Legacy index has the right count but no fingerprint.
        self.open()
        self.assertEqual(self.store.reset_collection.call_count, 1)
        self.assertEqual(self.store.add_texts.call_args.kwargs["metadatas"][0]["title"], "Title")
        self.windows[0]["text"] = "A Title\nAmended law."
        self.open()
        self.assertEqual(self.store.reset_collection.call_count, 2)

    def test_changed_chunking_version_rebuilds(self):
        self.open()
        with patch.object(kb, "CHUNKING_VERSION", "next-version"):
            self.open()
        self.assertEqual(self.store.reset_collection.call_count, 2)

    def test_incomplete_count_rebuilds_even_with_matching_fingerprint(self):
        self.open()
        self.store._collection.count.return_value = 0
        self.open()
        self.assertEqual(self.store.reset_collection.call_count, 2)

    def test_failed_build_is_not_marked_complete(self):
        self.store.add_texts.side_effect = RuntimeError("interrupted")
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            self.open()
        self.store._collection.modify.assert_not_called()
        self.store.add_texts.side_effect = None
        self.open()
        self.assertEqual(self.store.reset_collection.call_count, 2)
        self.assertIn("chunk_fingerprint", self.store._collection.metadata)


if __name__ == "__main__":
    unittest.main()
