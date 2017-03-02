import os

from charmhelpers.core.hookenv import charm_dir
from charmhelpers.core.templating import render

from reactive.helpers import data_changed, data_commit

CONFIG_PATH = "files"


class ConfigurationRequiredException(Exception):
    def __init__(self, key):
        super().__init__(key)


def required(cfg, key):
    """
    Use this method to make the extend function raise an error if the specified
    configuration option is empty.

    :param cfg: The charm config
    :type cfg: dict
    :param key: The specific charm config option
    :type key: str
    """
    value = cfg[key]
    # False and 0 are valid values for a required option
    if not value and value not in (False, 0):
        raise ConfigurationRequiredException(key)
    return value


class ConfigurationException(Exception):
    """
    Exception raised for errors while generating, rendering or configuring a
    component.

    :param config: The :class:`Config` this exception refers to
    :type config: :class:`Config`
    :param message: Exception message
    :type message: str
    """
    def __init__(self, config, message):
        super().__init__(message)
        self.config = config


class Config:
    """
    The purpose of this class is to handle all config related operations. This
    includes generating the config data and rendering the config file from a
    template.

    :param name: The name of the config
    :type name: str
    :var filename: Filename of the config template file
    :vartype filename: str
    :var path: Path to the config file
    :vartype path: str
    """
    def __init__(self, filename, path, target=None):
        self._config = {}

        self.filename = filename
        self.path = path
        self.template = os.path.join(self.path, self.filename)
        if target:
            self.target = os.path.join(charm_dir(), CONFIG_PATH, target)
        else:
            self.target = os.path.join(charm_dir(), CONFIG_PATH, self.template)

        self.unitdata_key = "charmscaler.config.{}.{}".format(self.path,
                                                              self.filename)

    def __str__(self):
        return self.target

    def extend(self, func, *args):
        """
        Add more configuration data through a generator function which creates
        a dictionary with the config values in place.

        :param func: The config generator function
        :type func: function
        :param *args: Extra arguments to the generator function
        """
        try:
            self._config.update(func(*args))
        except ConfigurationRequiredException as err:
            msg = "Config option '{}' cannot be empty".format(err)
            raise ConfigurationException(self, msg)

    def has_changed(self):
        """
        Check if this config has changed in the unit data store.
        """
        return data_changed(self.unitdata_key, self._config)

    def commit(self):
        """
        Commit the current config to the unit data store.
        """
        data_commit(self.unitdata_key, self._config)

    def render(self):
        """
        Render the configuration data to the configuration file located at
        `path` class variable.
        """
        render(self.template, self.target, self._config)

    def open(self, mode='rb'):
        return open(self.target, mode)

    def exists(self):
        return os.path.isfile(self.target)
