#!/usr/bin/env python

from requests.exceptions import RequestException
import requests_mock
import unittest
import unittest.mock as mock

from reactive.component import ConfigComponent, DockerComponent, HTTPComponent


class TestDockerComponent(unittest.TestCase):
    @classmethod
    @mock.patch("reactive.component.Config")
    def setUpClass(cls, mock_config):
        cls.component = DockerComponent("test-component")

    def test_healthcheck(self):
        # Not much to test at the moment. Important test in charms.docker.
        pass

    @mock.patch("reactive.component.Config")
    @mock.patch("reactive.component.Compose")
    def test_compose_up(self, mock_compose, mock_config):
        self.component.healthcheck = mock.MagicMock()

        self.component.compose_config.has_changed.return_value = True
        self.component.compose_up()
        self.assertTrue(self.component.compose_config.render.called)
        self.assertTrue(self.component._compose.up.called)
        self.assertTrue(self.component.healthcheck.called)


class TestHTTPComponent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.component = HTTPComponent("test-component", 1337, {
            "status": "status",
        })

    def test_paths(self):
        # Existing path
        url = "http://localhost:{port}/{path}".format(
            port=self.component.port,
            path="status"
        )
        self.assertEqual(self.component._get_url("status"), url)

        # Missing path
        self.assertRaises(NotImplementedError, self.component._get_url, "_")


class TestConfigComponent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with mock.patch("reactive.component.Config"):
            cls.component = ConfigComponent("test-component", 1337, {
                "status": "status",
                "configure": "configure"
            })

    @requests_mock.mock()
    def test_configure(self, mock_req):
        url = self.component._get_url("configure")
        mock_req.post(url, status_code=200)

        # Normal configuration procedure when config has changed
        self.component.config.has_changed.return_value = True
        self.component.configure()
        self.assertTrue(self.component.config.render.called)
        self.assertTrue(self.component.config.has_changed.called)
        self.assertTrue(self.component.config.commit.called)
        self.assertEqual(mock_req.call_count, 1)

        self.component.config.reset_mock()

        # No request should be sent if the config has not changed
        self.component.config.has_changed.return_value = False
        self.component.configure()
        self.assertTrue(self.component.config.render.called)
        self.assertTrue(self.component.config.has_changed.called)
        self.assertFalse(self.component.config.commit.called)
        self.assertEqual(mock_req.call_count, 1)

        self.component.config.reset_mock()

        # Invalid config
        self.component.config.has_changed.return_value = True
        mock_req.post(url, status_code=400)
        self.assertRaises(RequestException, self.component.configure)
        self.assertEqual(mock_req.call_count, 2)


if __name__ == "__main__":
    unittest.main()
