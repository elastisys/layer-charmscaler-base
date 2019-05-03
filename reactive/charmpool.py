from reactive.component import DockerComponent
from reactive.config import required


class Charmpool(DockerComponent):
    """
    The charmpool component.

    :param cfg: The charm configuration
    :type cfg: dict
    :param tag: Docker image tag
    :type tag: str
    """
    def __init__(self, cfg, image, tag):
        super().__init__("charmpool", image=image, tag=tag)

    def compose_up(self, cfg, application):
        """
        Generates and runs the Charmpool's Docker compose file.

        :raises: component.DockerComponentUnhealthy
        """
        self.compose_config.extend(compose_config, cfg, application)
        super().compose_up()


def compose_config(cfg, application):
    """
    Generates Charmpool config dict.

    :param cfg: The charm configuration
    :type cfg: dict
    :param application: The name of the application that is being autoscaled
    :type application: str
    :returns: dict with Charmpool's Docker compose config
    """
    config = {
        "application": application
    }

    for key in (
            "juju_api_endpoint",
            "juju_ca_cert",
            "juju_model_uuid",
            "juju_username",
            "juju_password",
            "juju_refresh_interval",
    ):
        config[key] = required(cfg, key)

    return config
