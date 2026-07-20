import unittest

from utils import combine_yamls


class CombineYamlsTest(unittest.TestCase):
    def test_sorts_address_bearing_entries(self):
        combined = combine_yamls([
            [{"label": "later", "addr": 0x08000020}],
            [{"label": "earlier", "addr": {"J": 0x08000010}}],
        ])

        self.assertEqual(
            [entry["label"] for entry in combined],
            ["earlier", "later"],
        )

    def test_preserves_non_address_entry_order(self):
        combined = combine_yamls([
            [{"label": "Second", "vals": []}],
            [{"label": "First", "vars": []}],
        ])

        self.assertEqual(
            [entry["label"] for entry in combined],
            ["Second", "First"],
        )


if __name__ == "__main__":
    unittest.main()
