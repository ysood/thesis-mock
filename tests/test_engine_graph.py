import unittest

from engine import graph, tools


class GraphHints(unittest.TestCase):
    def setUp(self):
        self.mode = graph.MODE

    def tearDown(self):
        graph.MODE = self.mode

    def test_runtime_mode_adds_nothing(self):
        graph.MODE = 'runtime'
        result = tools.read(tools.new_record(), ['region_a'], 'A-REG 19')
        self.assertNotIn('graph_hints', result)
        self.assertNotIn('GRAPH:', tools.prompt(['region_a']))

    def test_generated_mode_shows_routes_exceptions_and_lower_level_effects(self):
        graph.MODE = 'generated'
        hints = tools.read(tools.new_record(), ['region_a'], 'A-REG 19')['graph_hints']
        text = str(hints)
        self.assertIn('apply only to transfers which are occasional', text)
        self.assertTrue(any(e['by'] == 'A1-HIA 7' and e['relation'] == 'restricts_route'
                            for e in hints['cross_corpus_effects']))
        self.assertIn('GRAPH:', tools.prompt(['region_a']))

    def test_other_corpora_get_pointers_not_node_detail(self):
        graph.MODE = 'generated'
        hints = tools.describe_node('A-REG 18', ['region_b'])['graph_hints']
        self.assertNotIn('built_from_this_provision', hints)
        self.assertTrue(any(x['with'] == 'B-RAA 3' for x in hints['other_jurisdictions']))

    def test_continuation_reads_do_not_repeat_hints(self):
        graph.MODE = 'generated'
        self.assertNotIn('graph_hints', tools.read(tools.new_record(), ['region_a'], 'A-REG 19', start=1))


if __name__ == '__main__':
    unittest.main()
