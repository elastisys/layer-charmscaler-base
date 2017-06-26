#!/usr/bin/env python

import unittest
import unittest.mock as mock

from reactive.config import Config, ConfigurationException, required


class TestConfig(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("reactive.config.charm_dir")
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_extend(self):
        cfg = Config("test-config", "path")

        # Initial config
        self.assertEqual(cfg._config, {})

        # Extended config
        def extend_func(data):
            return {
                "some": "stuff",
                "more": data
            }
        cfg.extend(extend_func, "stuff")
        self.assertEqual(cfg._config, {
            "some": "stuff",
            "more": "stuff"
        })

    @mock.patch("reactive.config.open", new_callable=mock.mock_open)
    def test_has_changed(self, mock_open):
        cfg = Config("test-config", "path")

        # Rather than having to render a file we fake the config file reads
        # by returning the config content
        def _fake_read():
            return str(cfg._config).encode("utf-8")
        mock_open.return_value.read.side_effect = _fake_read

        # Initial config
        self.assertTrue(cfg.has_changed())

        # Changed config
        cfg.extend(lambda: {"more": "stuff"})
        self.assertTrue(cfg.has_changed())

        # Uncommited config
        self.assertTrue(cfg.has_changed())

        # Unchanged config after commit
        cfg.commit()
        self.assertFalse(cfg.has_changed())

    def test_empty_required_value(self):
        cfg = Config("test-config", "path")
        some_data = {"some": "stuff", "more": None}
        self.assertRaises(ConfigurationException, cfg.extend, lambda data: {
            "some": data["some"],
            "more": required(data, "more")
        }, some_data)


if __name__ == "__main__":
    unittest.main()
