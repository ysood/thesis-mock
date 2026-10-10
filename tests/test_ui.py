"""Render and execute the current UI with the provider and embedding paths blocked."""

import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app import knowledge as kb, llm
from tests.test_v9 import ROOT


class UiTests(unittest.TestCase):
    def test_offline_two_layer_run_preserves_input_and_renders_case_record(self):
        before = llm.FAKE_MODEL
        try:
            with (patch.object(llm, 'model', side_effect=AssertionError('Paid call forbidden')),
                  patch.object(kb, 'vector_store', return_value=None), patch.object(kb, 'search', return_value=[])):
                app = AppTest.from_file(str(ROOT / 'ui.py'), default_timeout=15).run()
                self.assertFalse(app.exception)
                next(s for s in app.selectbox if s.label == 'Load').select('28_ie_gp_practice_to_us_cloud_ehr.json').run()
                next(t for t in app.toggle if t.label == 'Offline fake model (no API key)').set_value(True).run()
                next(b for b in app.button if b.label == 'Run assessment').click().run()
                self.assertFalse(app.exception, [e.message for e in app.exception])
                last = app.session_state['last']
                self.assertIn('organisations', last['request'])
                self.assertEqual(last['request'], {k: v for k, v in last['result']['case_record']['input'].items() if k != 'reference_facts'})
                self.assertEqual(last['result']['workflow'], 'supervisor-v15')
                self.assertEqual(last['result']['decision'], 'needs_review')
                self.assertIn('Case record', [t.label for t in app.tabs])
        finally:
            llm.FAKE_MODEL = before
