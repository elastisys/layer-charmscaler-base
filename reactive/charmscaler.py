import os

from requests.exceptions import HTTPError

from charmhelpers.core import hookenv
from charms.docker import Docker
from charms.reactive import (all_states, hook, is_state, remove_state,
                             set_state, when, when_all, when_not)

from reactive.autoscaler import Autoscaler, MetricValidationException
from reactive.charmpool import Charmpool
from reactive.component import (DockerComponent, DockerComponentStarting,
                                DockerComponentUnhealthy)
from reactive.config import ConfigurationException

cfg = hookenv.config()

AUTOSCALER_VERSION = cfg["autoscaler_version"]
CHARMPOOL_VERSION = cfg["charmpool_version"]

components = [
    Charmpool(cfg, image=cfg["charmpool_image"], tag=CHARMPOOL_VERSION),
    Autoscaler(cfg, image=cfg["autoscaler_image"], tag=AUTOSCALER_VERSION)
]

# All CharmScaler states, each state depends on the states before it
states = [
    "charmscaler.installed",
    "charmscaler.composed",
    "charmscaler.initialized",
    "charmscaler.configured",
    "charmscaler.started",
    "charmscaler.available"
]


def get_state_dependencies(state):
    """
    Returns all of the states that this state depends on
    """
    return states[:states.index(state)]


def _execute(method, *args, classinfo=None, pre_healthcheck=True, **kwargs):
    """
    Helper function to execute the same component-method on all of the charm's
    components.

    :param method: Name of the method to run
    :type method: str
    :param classinfo: Class from which the component needs to be an instance or
                      a subclass of for the method to be called on it.
    :type classinfo: type
    :param pre_healthcheck: If True, a Docker healthcheck will be executed on
                            the components before continuing with the normal
                            operation.
    :type pre_healthcheck: bool
    :returns: True if no errors occured, else False
    """

    # Handlers can fire after the cleanup, simply ignore all executions
    if is_state("charmscaler.cleaned_up"):
        return

    try:
        if pre_healthcheck:
            healthy = _execute("healthcheck", classinfo=DockerComponent,
                               pre_healthcheck=False)
            if not healthy:
                return False

        for component in components:
            if not classinfo or isinstance(component, classinfo):
                getattr(component, method)(*args, **kwargs)

        return True
    except HTTPError as err:
        try:
            error_msg = err.response.json()["message"]
        except Exception:
            error_msg = str(err)
        msg = "HTTP error while executing '{}': {}".format(method, error_msg)
    except ConfigurationException as err:
        msg = "Error while configuring {}: {}".format(err.config.filename, err)
    except (DockerComponentUnhealthy, DockerComponentStarting) as err:
        msg = str(err)
    except MetricValidationException as err:
        msg = str(err)

    hookenv.status_set("blocked", msg)
    hookenv.log(msg, level=hookenv.ERROR)
    return False


@when_not("docker.available")
def wait_for_docker():
    """
    Wait for Docker to get installed and start up.
    """
    hookenv.status_set("maintenance", "Installing Docker")


def _prepare_volume_directories():
    """
    Create directories that are to be mounted as Docker volumes.
    """
    # state storage for containers
    if not os.path.exists('/var/lib/elastisys'):
        os.makedirs('/var/lib/elastisys')
    # container log output
    if not os.path.exists('/var/log/elastisys'):
        os.makedirs('/var/log/elastisys')


@when("docker.available")
@when_not("charmscaler.installed")
def install():
    """
    Prepare and install the CharmScaler components.
    """
    hookenv.status_set("maintenance", "Installing")

    hookenv.application_version_set("{}, {}".format(AUTOSCALER_VERSION,
                                                    CHARMPOOL_VERSION))

    _prepare_volume_directories()

    docker = Docker()

    for component in components:
        msg = "Loading Docker image from {} resource".format(component)
        hookenv.log(msg)
        hookenv.status_set("maintenance", msg)

        path = hookenv.resource_get(str(component))

        if not path:
            msg = "Missing resource: {}".format(component)
            hookenv.log(msg, level=hookenv.ERROR)
            hookenv.status_set("blocked", msg)
            return

        docker.load(path)

    set_state("charmscaler.installed")


@hook("upgrade-charm")
def reinstall():
    """
    Reinstall the CharmScaler on the upgrade-charm hook.
    """
    remove_state("charmscaler.installed")
    remove_state("charmscaler.composed")
    remove_state("charmscaler.configured")
    remove_state("charmscaler.started")
    remove_state("charmscaler.available")


@when("config.changed")
def reconfigure():
    remove_state("charmscaler.composed")
    remove_state("charmscaler.configured")
    remove_state("charmscaler.available")


@hook("update-status")
def update_status():
    # We only update the status if we're up and running
    if all_states(*states):
        _execute("healthcheck", classinfo=DockerComponent,
                 pre_healthcheck=False)


@when_all(*get_state_dependencies("charmscaler.composed"))
@when_not("scalable-charm.available")
def scalable_charm_wait():
    """
    Wait for a juju-info relation to a charm that is going to be autoscaled.
    """
    hookenv.status_set("blocked", "Waiting for relation to scalable charm")


@when("charmscaler.composed")
@when_not("scalable-charm.available")
def scalable_charm_lost():
    stop()

    remove_state("charmscaler.composed")
    remove_state("charmscaler.configured")
    remove_state("charmscaler.started")
    remove_state("charmscaler.available")


@when_all(*get_state_dependencies("charmscaler.composed"))
@when_not("charmscaler.composed")
@when("scalable-charm.available")
def compose(scale_relation):
    """
    Start all of the Docker components. If the Compose manifest has changed the
    affected Docker containers will be recreated.

    :param scale_relation: Relation object for the charm that is going to be
                           autoscaled.
    :type scale_relation: JujuInfoClient
    """
    class ComposeException(Exception):
        pass

    try:
        scale_relation_ids = scale_relation.conversation().relation_ids

        if len(scale_relation_ids) > 1:
            raise ComposeException("Cannot scale more than one application at "
                                   "the same time. Deploy more CharmScalers.")

        # This could happen if the state hasn't been updated yet but the
        # relation is removed.
        if len(scale_relation_ids) < 1:
            raise ComposeException("Scalable charm relation was lost")

        application = hookenv.remote_service_name(scale_relation_ids[0])

        if _execute("compose_up", cfg, application, classinfo=DockerComponent,
                    pre_healthcheck=False):
            set_state("charmscaler.composed")
            return
    except ComposeException as err:
        msg = "Error while composing: {}".format(err)

        hookenv.status_set("blocked", msg)
        hookenv.log(msg, level=hookenv.ERROR)


@when_all(*get_state_dependencies("charmscaler.initialized"))
@when_not("charmscaler.initialized")
def initialize():
    """
    Initialize the autoscaler.
    """
    if _execute("initialize", classinfo=Autoscaler):
        set_state("charmscaler.initialized")


@when_all(*get_state_dependencies("charmscaler.configured"))
@when_not("db-api.available")
def wait_for_influxdb():
    """
    Wait for relation to InfluxDB charm.
    """
    hookenv.status_set("blocked", "Waiting for InfluxDB relation")


@when_all(*get_state_dependencies("charmscaler.configured"))
@when_not("charmscaler.configured")
@when("charmscaler.metrics.available")
@when("db-api.available")
def configure(influxdb):
    """
    Configure the autoscaler. This is done at every run, however, if the config
    is unchanged nothing happens.
    """
    from reactive import charmscaler_metrics
    metrics = charmscaler_metrics.get_metrics()
    if _execute("configure", cfg, influxdb, metrics, classinfo=Autoscaler):
        set_state("charmscaler.configured")


@when_all(*get_state_dependencies("charmscaler.started"))
@when_not("charmscaler.started")
def start():
    """
    Start the autoscaler.
    """
    if _execute("start", classinfo=Autoscaler):
        set_state("charmscaler.started")


def stop():
    """
    Stop the autoscaler and stop all Docker containers.
    """
    _execute("stop", classinfo=Autoscaler)
    _execute("compose_stop", classinfo=DockerComponent)


@when_all(*get_state_dependencies("charmscaler.available"))
@when_not("charmscaler.available")
def available():
    """
    We're good to go!
    """
    hookenv.status_set("active", "Available")
    set_state("charmscaler.available")


@hook("stop")
def cleanup():
    """
    Cleanup all components by removing Docker containers and images.
    """
    _execute("cleanup", pre_healthcheck=False, classinfo=DockerComponent)
    set_state("charmscaler.cleaned_up")
