# Creds to https://github.com/juju-solutions/bundle-canonical-kubernetes/blob/master/tests/amulet_utils.py # noqa

import subprocess
import yaml


def attach_resource(charm, resource, resource_path):
    ''' Upload a resource to a deployed model.
    :param: charm - the application to attach the resource
    :param: resource - The charm's resouce key
    :param: resource_path - the path on disk to upload the
    resource'''

    # the primary reason for this method is to replace a shell
    # script in the $ROOT dir of the charm
    cmd = ['juju', 'attach', charm, "{}={}".format(resource, resource_path)]

    # Poll the controller to determine if resource placement is needed
    if not has_resource(charm, resource):
        subprocess.call(cmd)


def has_resource(charm, resource):
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
