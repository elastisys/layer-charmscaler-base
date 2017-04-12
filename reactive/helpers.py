import hashlib
import logging

from charmhelpers.core import unitdata
from charmhelpers.core.hookenv import log as juju_log


def data_changed(data_id, data, hash_type="md5"):
    """
    Similar to the data_changed function in charms.reactive.helpers but without
    the kv().set step. Usable when you don't want the data to be updated until
    later on. For example to make sure the data is only updated when a task has
    finished successfully.
    """
    key = "reactive.data_changed.{}".format(data_id)
    alg = getattr(hashlib, hash_type)
    old_hash = unitdata.kv().get(key)
    new_hash = alg(data).hexdigest()
    return old_hash != new_hash


def data_commit(data_id, data, hash_type="md5"):
    """
    Used in conjunction with data_changed() to update the changes in the
    datastore.
    """
    key = "reactive.data_changed.{}".format(data_id)
    alg = getattr(hashlib, hash_type)
    new_hash = alg(data).hexdigest()
    unitdata.kv().set(key, new_hash)


def log_to_juju(name):
    """
    Forward logging to the Juju log
    """
    class JujuHandler(logging.Handler):
        def emit(self, record):
            log_entry = self.format(record)
            juju_log(log_entry, level=record.levelname)
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    log.addHandler(JujuHandler())
