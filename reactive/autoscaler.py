from requests.exceptions import HTTPError

from charmhelpers.core.hookenv import local_unit, log

from reactive.component import ConfigComponent, DockerComponent
from reactive.config import Config, required


class Autoscaler(DockerComponent, ConfigComponent):
    """
    This class includes the specific instructions and manages the necesssary
    lifecycle operations of the Autoscaler component.

    :param cfg: The charm configuration
    :type cfg: dict
    :param tag: Docker image tag
    :type tag: str
    """
    def __init__(self, cfg, tag):
        self.unit_id = local_unit().replace('/', '-')
        super().__init__("autoscaler", cfg["port_autoscaler"], {
            "initialize": "autoscaler/instances",
            "status": "autoscaler/instances/{}/status".format(self.unit_id),
            "configure": "autoscaler/instances/{}/config".format(self.unit_id),
            "start": "autoscaler/instances/{}/start".format(self.unit_id),
            "stop": "autoscaler/instances/{}/stop".format(self.unit_id)
        }, tag=tag)

    def compose_up(self, *args, **kwargs):
        """
        Generates and runs the Autoscaler's Docker compose file.

        :raises: component.DockerComponentUnhealthy
        """
        self.compose_config.extend(lambda: {"port": self.port})
        super().compose_up()

    def initialize(self):
        """
        Render a blueprint configuration and launch an instance using said
        blueprint.

        :raises: requests.exceptions.RequestException
        """
        blueprint_config = Config("blueprint.json", self.name)

        blueprint_config.extend(lambda: {
            "id": self.unit_id
        })

        blueprint_config.render()

        with blueprint_config.open() as config_file:
            try:
                self.send_request("initialize", method="POST",
                                  headers={"content-type": "application/json"},
                                  data=config_file, data_type="file")
            except HTTPError as err:
                def is_ready():
                    """
                    Checks if the Autoscaler server is ready.
                    """
                    try:
                        self.send_request("status")
                    except HTTPError as err:
                        log("Autoscaler status request error: {}".format(err))
                        return False
                    return True

                # Check if the Autoscaler instance already has been created
                if err.response.status_code != 400 or not is_ready():
                    raise err

    def configure(self, cfg, influxdb, metrics):
        """
        Generate the Autoscaler-specfic config values and configure the
        instance.

        :param cfg: The charm configuration
        :type cfg: dict
        :param influxdb: InfluxDB information
        :type influxdb: dict
        :raises: config.ConfigurationException
        :raises: requests.exceptions.RequestException
        """
        self.config.extend(autoscaler_config, cfg, influxdb, metrics)
        super().configure()

    def start(self):
        """
        Start the Autoscaler.

        :raises: requests.exceptions.RequestException
        """
        self.send_request("start", method="POST")

    def stop(self):
        """
        Stop the Autoscaler.

        :raises: requests.exceptions.RequestException
        """
        self.send_request("stop", method="POST")


def alerts_config(cfg):
    """
    Generates the alerts config dict.

    :param cfg: The charm configuration
    :type cfg: dict
    :returns: dict with alert configuration options
    """
    if not required(cfg, "alert_enabled"):
        return None

    return {
        "recipients": required(cfg, "alert_receivers").split(),
        "levels": required(cfg, "alert_levels").split(),
        "sender": required(cfg, "alert_sender"),
        "smtp": {
            "host": required(cfg, "alert_smtp_host"),
            "port": required(cfg, "alert_smtp_port"),
            "ssl": required(cfg, "alert_smtp_ssl"),
            "username": required(cfg, "alert_smtp_username"),
            "password": required(cfg, "alert_smtp_password")
        }
    }


def influxdb_config(influxdb):
    """
    Returns the InfluxDB relation data as dict to use in config.

    :param influxdb: InfluxDB relation data object
    :type influxdb: InfluxdbClient
    :returns: dict with InfluxDB configuration options
    """
    return {
        "host": influxdb.hostname(),
        "port": influxdb.port(),
        "username": influxdb.user(),
        "password": influxdb.password(),
    }


def _validate_metrics(metrics):
    # TODO
    return metrics


def autoscaler_config(cfg, influxdb, metrics):
    """
    Generates the Autoscaler's config dict.

    :param influxdb: InfluxDB relation data object
    :type influxdb: InfluxdbClient
    :returns: dict with the Autoscaler's configuration
    """
    return {
        "name": "{} Autoscaler".format(required(cfg, "name")),
        "alert": alerts_config(cfg),
        "influxdb": influxdb_config(influxdb),
        "metrics": _validate_metrics(metrics),
        "metric": {
            "poll_interval": required(cfg, "metric_poll_interval")
        },
        "scaling": {
            "min_units": required(cfg, "scaling_units_min"),
            "max_units": required(cfg, "scaling_units_max"),
            "interval": required(cfg, "scaling_interval")
        },
        "cloudpool": {
            "url": required(cfg, "charmpool_url")
        }
    }
