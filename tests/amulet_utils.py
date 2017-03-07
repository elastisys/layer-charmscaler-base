import amulet
from juju.client.connection import JujuData
import logging
import os
import requests
import subprocess
import yaml

log = logging.getLogger(__name__)


def get_juju_credentials():
    jujudata = JujuData()

    controller_name = jujudata.current_controller()

    controller = jujudata.controllers()[controller_name]
    endpoint = controller["api-endpoints"][0]

    models = jujudata.models()[controller_name]
    model_name = models["current-model"]
    model_uuid = models["models"][model_name]["uuid"]

    accounts = jujudata.accounts()[controller_name]
    username = accounts["user"]
    password = accounts.get("password")

    return {
        "endpoint": endpoint,
        "model_uuid": model_uuid,
        "username": username,
        "password": password
    }


def _download_resource(url, target_path):
    r = requests.get(url, stream=True)
    r.raise_for_status()

    log.info("Downloading resource {} to {}".format(url, target_path))

    with open(target_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)


def _get_resource(charm, resource):
    env = "{}_RESOURCE_{}".format(charm.upper(), resource.upper())
    default_url = ("https://api.jujucharms.com/charmstore/v5/"
                   "~elastisys/{}/resource/{}".format(charm, resource))
    resource_path = os.getenv(env, default_url)

    if os.path.isfile(resource_path):
        return resource_path

    try:
        target_path = "/tmp/{}-{}.tar".format(charm, resource)
        _download_resource(resource_path, target_path)
        return target_path
    except requests.exceptions.RequestException:
        message = "resource '{}' not found".format(resource_path)
        amulet.raise_status(amulet.FAIL, msg=message)


def attach_resource(charm, resource):
    if not _has_resource(charm, resource):
        resource_path = _get_resource(charm, resource)
        _attach_resource(charm, resource, resource_path)


# Creds to https://github.com/juju-solutions/bundle-canonical-kubernetes/blob/master/tests/amulet_utils.py  # noqa

def _attach_resource(charm, resource, resource_path):
    ''' Upload a resource to a deployed model.
    :param: charm - the application to attach the resource
    :param: resource - The charm's resouce key
    :param: resource_path - the path on disk to upload the
    resource'''

    # the primary reason for this method is to replace a shell
    # script in the $ROOT dir of the charm
    cmd = ['juju', 'attach', charm, "{}={}".format(resource, resource_path)]
    subprocess.call(cmd)


def _has_resource(charm, resource):
    ''' Poll the controller to determine if we need to upload a resource
    '''
    cmd = ['juju', 'resources', charm, '--format=yaml']
    output = subprocess.check_output(cmd)
    resource_list = yaml.safe_load(output)
    for resource in resource_list['resources']:
        # We can assume this is the correct resource if it has a filesize
        # matches the name of the resource in the charms resource stream
        if 'name' in resource and (charm in resource['name'] and
                                   resource['size'] > 0):
            # Display the found resource
            print('Uploading {} for {}'.format(resource['name'], charm))
            return True
    return False
