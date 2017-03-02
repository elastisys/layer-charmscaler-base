#!/usr/bin/env python

from requests.exceptions import RequestException
import requests_mock
import unittest
import unittest.mock as mock

# Disable backoff retry calls
import backoff
def noop_decorator(wait_gen, exception, max_tries=None, jitter=None):  # noqa
    def decorator(f):
        return f
    return decorator
backoff.on_exception = noop_decorator  # noqa

from reactive.autoscaler import Autoscaler


class TestAutoscaler(unittest.TestCase):
    @classmethod
    @mock.patch.dict("os.environ", {
        "JUJU_UNIT_NAME": "openstackscaler/1",
        "CHARM_DIR": "/tmp"
    })
    @mock.patch("reactive.component.Config")
    @mock.patch("reactive.component.Compose")
    def setUpClass(cls, mock_compose, mock_config):
        cls.autoscaler = Autoscaler({
            "name": "OpenStackScaler",
            "port_autoscaler": 8080
        }, "latest")

    def setUp(self):
        patcher = mock.patch("reactive.component.HTTP_RETRY_LIMIT")
        self.addCleanup(patcher.stop)
        retry_limit_patch = patcher.start()
        retry_limit_patch.return_value = 0

    @requests_mock.mock()
    @mock.patch("reactive.autoscaler.Config")
    def test_initialize(self, mock_req, mock_config):
        initialize_url = self.autoscaler._get_url("initialize")
        instance_status_url = self.autoscaler._get_url("status")

        # OK initalization
        mock_req.post(initialize_url, status_code=200)
        self.autoscaler.initialize()
        self.assertEqual(mock_req.call_count, 1)

        # Initialization error
        mock_req.post(initialize_url, status_code=500)
        self.assertRaises(RequestException,
                          self.autoscaler.initialize)
        self.assertEqual(mock_req.call_count, 2)

        # Instance already created
        mock_req.post(initialize_url, status_code=400)
        mock_req.get(instance_status_url, status_code=200)
        self.autoscaler.initialize()
        self.assertEqual(mock_req.call_count, 4)

        # Instance already created with error on status lookup
        mock_req.post(initialize_url, status_code=400)
        mock_req.get(instance_status_url, status_code=500)
        self.assertRaises(RequestException,
                          self.autoscaler.initialize)
        self.assertEqual(mock_req.call_count, 6)

    @requests_mock.mock()
    def test_start(self, mock_req):
        url = self.autoscaler._get_url("start")

        # Start OK
        mock_req.post(url, status_code=200)
        self.autoscaler.start()
        self.assertEqual(mock_req.call_count, 1)

        # Start error
        mock_req.post(url, status_code=500)
        self.assertRaises(RequestException, self.autoscaler.start)
        self.assertEqual(mock_req.call_count, 2)

    @requests_mock.mock()
    def test_stop(self, mock_req):
        url = self.autoscaler._get_url("stop")

        # Stop OK
        mock_req.post(url, status_code=200)
        self.autoscaler.stop()
        self.assertEqual(mock_req.call_count, 1)

        # Stop error
        mock_req.post(url, status_code=500)
        self.assertRaises(RequestException, self.autoscaler.stop)
        self.assertEqual(mock_req.call_count, 2)


if __name__ == "__main__":
    unittest.main()
