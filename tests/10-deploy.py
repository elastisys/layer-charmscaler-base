#!/usr/bin/env python3.5
import amulet
from amulet_utils import attach_resource, get_juju_credentials
import asyncio
import json
from juju import loop
from juju.errors import JujuAPIError
from juju.model import Model
import logging
import re
import unittest

log = logging.getLogger(__name__)

SCALABLE_CHARM = "ubuntu"


class TestCharm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = amulet.Deployment(series="xenial")

        credentials = get_juju_credentials()

        cls.d.add("charmscaler")

        cls.d.configure("charmscaler", {
            "juju_api_endpoint": credentials["endpoint"],
            "juju_model_uuid": credentials["model_uuid"],
            "juju_username": credentials["username"],
            "juju_password": credentials["password"],
            "scaling_units_min": 1,
            "scaling_units_max": 1
        })

        cls.d.add("influxdb", charm="cs:~chris.macnaughton/influxdb-7")
        cls.d.add("telegraf", charm="cs:telegraf-2")
        cls.d.add(SCALABLE_CHARM)

        cls.d.relate("charmscaler:db-api", "influxdb:query")
        cls.d.relate("telegraf:influxdb-api", "influxdb:query")
        cls.d.relate("telegraf:juju-info",
                     "{}:juju-info".format(SCALABLE_CHARM))
        cls.d.relate("charmscaler:scalable-charm",
                     "{}:juju-info".format(SCALABLE_CHARM))

        try:
            cls.d.setup(timeout=900)
            cls.d.sentry.wait()
        except amulet.helpers.TimeoutError:
            message = "Environment wasn't stood up in time"
            amulet.raise_status(amulet.SKIP, msg=message)

        for resource in ["autoscaler", "charmpool"]:
            attach_resource("charmscaler", resource)

        try:
            cls.d.sentry.wait_for_messages({"charmscaler": "Available"})
        except amulet.helpers.TimeoutError:
            message = "CharmScaler charm did not become available in time"
            amulet.raise_status(amulet.FAIL, msg=message)

    def _configure(self, config):
        self.d.configure("charmscaler", config)
        try:
            self.d.sentry.wait_for_messages({"charmscaler": "Available"})
        except amulet.helpers.TimeoutError:
            message = "Timeout configuring charmscaler: {}".format(config)
            amulet.raise_status(amulet.FAIL, msg=message)

    async def _manual_scale(self, expected_units):
        log.info("Scaling '{}' to {} unit(s)...".format(SCALABLE_CHARM,
                                                        expected_units))

        self._configure({
            "scaling_units_min": expected_units,
            "scaling_units_max": expected_units
        })

        try:
            m = Model()
            await m.connect_current()
            try:
                for i in amulet.helpers.timeout_gen(300):
                    actual_units = len(m.applications[SCALABLE_CHARM].units)
                    if actual_units == expected_units:
                        break
                    await asyncio.sleep(0)
            finally:
                await m.disconnect()
        except amulet.helpers.TimeoutError:
            msg = ("The CharmScaler did not scale the application '{}' to {} "
                   "unit(s) in time.").format(SCALABLE_CHARM, expected_units)
            amulet.raise_status(amulet.FAIL, msg=msg)
        except JujuAPIError as e:
            msg = ("Juju API error: {}").format(str(e))
            amulet.raise_status(amulet.FAIL, msg=msg)

    def test_scaling(self):
        loop.run(*[self._manual_scale(count) for count in [2, 4, 1]])

    def test_restricted(self):
        self.d.configure("charmscaler", {
            "scaling_units_max": 5
        })
        try:
            self.d.sentry.wait_for_messages({
                "charmscaler":
                re.compile(r"Refusing to set a capacity limit max value")
            })
        except amulet.helpers.TimeoutError:
            message = "Never got restricted status message from charmscaler"
            amulet.raise_status(amulet.FAIL, msg=message)

        self._configure({
            "scaling_units_max": 4
        })

    def _run_action(self, action, action_args):
        charmscaler = self.d.sentry["charmscaler"][0]
        action_id = charmscaler.run_action(action, action_args=action_args)
        log.info("Running action {} with ID {}".format(action, action_id))

        try:
            output = self.d.action_fetch(action_id, raise_on_timeout=True,
                                         full_output=True)

            message = "" if "message" not in output else output["message"]
            self.assertEqual(output["status"], "completed", message)

            return None if "results" not in output else output["results"]
        except amulet.helpers.TimeoutError:
            message = "Timeout while executing action {}".format(action)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_alert_mails(self):
        ports = self._run_action("smtpserver", {
            "operation": "start"
        })["ports"]
        self.addCleanup(self._run_action, "smtpserver", {
            "operation": "stop",
            "port": ports["rpc"]
        })
        self.addCleanup(self._configure, {
            "alert_enabled": False,
            "charmpool_url": "http://charmpool:80"
        })

        # The SMTP server is running on the host while the autoscaler is
        # running inside a Docker container
        docker_inspect_output = json.loads(self._run_action("docker-inspect", {
            "container": "autoscaler"
        })["output"])
        docker_host_ip = (docker_inspect_output[0]["NetworkSettings"]
                          ["Networks"]["charmscaler_default"]["Gateway"])

        self._configure({
            "alert_enabled": True,
            "alert_levels": "INFO NOTICE WARN ERROR FATAL",
            "alert_receivers": "foo@charmscaler",
            "alert_sender": "bar@charmscaler",
            "alert_smtp_host": docker_host_ip,
            "alert_smtp_port": ports["smtp"],
            "alert_smtp_ssl": False,
            "alert_smtp_username": "foo",
            "alert_smtp_password": "bar"
        })

        self._configure({
            "charmpool_url": "http://not-charmpool:1234"
        })

        for i in amulet.helpers.timeout_gen(300):
            count = self._run_action("smtpserver", {
                "operation": "inboxcount",
                "port": ports["rpc"]
            })["count"]

            if int(count) > 0:
                break


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("websocket").setLevel(logging.WARNING)
    logging.getLogger("websockets.protocol").setLevel(logging.WARNING)
    logging.getLogger("deployer").setLevel(logging.WARNING)
    unittest.main()
