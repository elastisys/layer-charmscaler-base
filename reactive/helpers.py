import hashlib
import sys
import traceback

from charmhelpers.core import hookenv, unitdata


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


def backoff_handler(details, level=hookenv.DEBUG):
    """
    Slightly modified version of the default backoff handler to log using
    DEBUG level rather than spamming the log with errors for every backoff
    """
    fmt = "Backing off {0}(...) for {1:.1f}s"
    msg = fmt.format(details["target"].__name__, details["wait"])

    exc_typ, exc, _ = sys.exc_info()
    if exc is not None:
        exc_fmt = traceback.format_exception_only(exc_typ, exc)[-1]
        msg = "{0} ({1})".format(msg, exc_fmt.rstrip("\n"))
    else:
        msg = "{0} ({1})".format(msg, details["value"])

    hookenv.log(msg, level=level)
