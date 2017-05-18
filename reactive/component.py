import os

import backoff
from requests import Session
from requests.exceptions import RequestException

from charmhelpers.core.hookenv import log, status_set, DEBUG
from charms.docker import Compose, Docker

from reactive.config import Config
from reactive.helpers import log_to_juju

# Maximum number of seconds to wait for container to become healthy.
# This is mainly important during startup because that can take a while.
HEALTH_RETRY_LIMIT = 60

# Number of retries for a failed HTTP request.
HTTP_RETRY_LIMIT = 5

log_to_juju("backoff")


class Component:
    """
    Base class for all the different components that the charm is managing.

    :param name: Name of the component
    :type name: str
    """
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


class DockerComponentUnhealthy(Exception):
    def __init__(self, component):
        self.component = component
        super().__init__("Unhealthy component: {} - "
                         "Check the Docker container logs".format(component))


class DockerComponent(Component):
    """
    A Docker component is used for software which is executed as Docker images.
    With it you can generate a Docker Compose yaml-manifest and then start
    the Docker Compose services.

    :param name: Name of the component
    :type name: str
    :param tag: Docker image tag
    :type tag: str
    :var compose_config: Every Docker component has a :class:`Config` object
                         which is created with the name docker-compose.yml
                         under the folder path named after the component's
                         ':paramref:`name`' parameter.
    :vartype compose_config: :class:`Config`
    """
    def __init__(self, name, *args, image=None, tag="latest"):
        super().__init__(name, *args)
        self.compose_config = Config("docker-compose.yml", name)
        self.compose_config.extend(lambda: {
            "image": image,
            "tag": tag
        })

    @property
    def _compose(self):
        return Compose(os.path.dirname(str(self.compose_config)))

    @backoff.on_exception(backoff.constant, DockerComponentUnhealthy,
                          max_tries=HEALTH_RETRY_LIMIT, jitter=None)
    def healthcheck(self):
        """
        Healthcheck is used to poll the Docker health state. A health test
        command need to be specified in the Compose manifest or in the
        Dockerfile.

        If the Docker container is not healthy a
        :class:`DockerComponentUnhealthy` is raised. If not, the container is
        currently considered healthy by the test command.

        :raises: DockerComponentUnhealthy
        """
        log("Healthchecking {}".format(self.name), level=DEBUG)
        if not Docker().healthcheck(self.name):
            raise DockerComponentUnhealthy(self)

    def compose_up(self):
        """
        Generate, render and (re)start the component's Docker Compose services.

        If the content of the compose file is unchanged after it has been
        rendered nothing happens.
        """
        # TODO Would be nice to have support for multiple compose files and/or
        #      the project flag in charms.docker.
        #
        # Dotfiles are ignored when creating a charm archive to push to the
        # charmstore. We need to generate the .env files during runtime.
        compose_env = Config("dotenv", "common", "{}/.env".format(self.name))
        if not compose_env.exists():
            compose_env.extend(lambda: {"name": "charmscaler"})
            compose_env.render()

        self.compose_config.render()

        # TODO This will show up even though a restart might not have occured.
        msg = "(Re)starting Docker Compose service: {}".format(self)
        status_set("maintenance", msg)
        log(msg)

        self._compose.up()

        # Healthcheck Docker containers to make sure that they are working
        # as they should after they have been (re)started.
        self.healthcheck()

    def compose_stop(self):
        self._compose.stop()


class HTTPComponent(Component):
    """
    Components with a HTTP REST API.

    :param name: Name of the component
    :type name: str
    :param port: The port the component is supposed to listen on
    :type port: int
    :param paths: The REST API URL paths. The paths are dependent on which
                  operations the component is capable of.
    :type paths: dict
    """
    def __init__(self, name, port, paths):
        super().__init__(name)
        self.port = port
        self.paths = paths

        self._session = Session()

    def _get_url(self, path):
        try:
            return "http://localhost:{port}/{path}".format(
                port=self.port,
                path=self.paths[path]
            )
        except KeyError:
            msg = "Missing REST API path '{}' for {}".format(path, self.name)
            raise NotImplementedError(msg)

    @backoff.on_exception(backoff.expo, RequestException,
                          max_tries=HTTP_RETRY_LIMIT)
    def send_request(self, path, method="GET", headers=None, data=None,
                     data_type="json"):
        """
        Send requests to the REST API of the component.

        :param path: REST API path
        :param method: Request method to use. Default: GET
        :param headers: Request headers
        :param data: Request data
        :param data_type: Request data type. Default: json
        :returns: requests.Response
        :raises: requests.exceptions.RequestException
        """
        url = self._get_url(path)

        if method == "GET":
            response = self._session.get(url, headers=headers)
        elif method == "POST":
            if data_type == "json":
                response = self._session.post(url, headers=headers, json=data)
            elif data_type == "file":
                # Start from the beginning if this has already been read, for
                # example during a retry
                data.seek(0)
                response = self._session.post(url, headers=headers, data=data)
            else:
                raise Exception("Unhandeled data type: {}".format(data_type))
        else:
            raise Exception("Unhandeled REST API verb: {}".format(method))

        log("Request URL: {}".format(url), level=DEBUG)
        log("Response status: {}".format(response.status_code), level=DEBUG)
        log("Response data: {}".format(response.text), level=DEBUG)

        response.raise_for_status()

        return response


class ConfigComponent(HTTPComponent):
    """
    A config component have the capabilities of generating and rendering a
    configuration file from a specific template file.

    :param name: Name of the component
    :type name: str
    :param port: The port the component is supposed to listen on
    :type port: int
    :param paths: The REST API URL paths. The paths are dependent on which
                  operations the component is capable of.
    :type paths: dict
    :var config: Every config component has a :class:`Config` object which is
                 created with the name config.json under the folder path named
                 after the component's ':paramref:`name`' parameter.
    :vartype config: :class:`Config`
    """
    def __init__(self, name, port, paths):
        super().__init__(name, port, paths)
        self.config = Config("config.json", name)

    def configure(self):
        """
        Generate, render and push a new config to the component.

        If the content of the config file is unchanged after it has been
        rendered nothing happens.

        On errors, :class:`config.ConfigurationException` is raised.

        :raises: config.ConfigurationException,
                 requests.exceptions.RequestException
        """
        self.config.render()

        if self.config.has_changed():
            msg = "Configuring {}".format(self)
            status_set("maintenance", msg)
            log(msg)

            with self.config.open() as config_file:
                self.send_request("configure", method="POST",
                                  headers={"content-type": "application/json"},
                                  data=config_file, data_type="file")
                self.config.commit()
