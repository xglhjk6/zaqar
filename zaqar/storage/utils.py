# Copyright (c) 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License.  You may obtain a copy
# of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

import copy

from oslo.config import cfg
import six
from stevedore import driver

from zaqar.common import errors
from zaqar.common import utils
from zaqar.openstack.common import log

LOG = log.getLogger(__name__)


def dynamic_conf(uri, options, conf=None):
    """Given metadata, yields a dynamic configuration.

    :param uri: pool location
    :type uri: six.text_type
    :param options: additional pool metadata
    :type options: dict
    :param conf: Optional conf object to copy
    :type conf: `oslo.config.cfg.ConfigOpts`
    :returns: Configuration object suitable for constructing storage
              drivers
    :rtype: oslo.config.cfg.ConfigOpts
    """
    storage_type = six.moves.urllib_parse.urlparse(uri).scheme

    # NOTE(cpp-cabrera): parse storage-specific opts:
    # 'drivers:storage:{type}'
    storage_opts = utils.dict_to_conf({'uri': uri, 'options': options})
    storage_group = u'drivers:message_store:%s' % storage_type

    # NOTE(cpp-cabrera): register those options!
    if conf is None:
        conf = cfg.ConfigOpts()
    else:
        conf = copy.copy(conf)

    if storage_group not in conf:
        conf.register_opts(storage_opts,
                           group=storage_group)

    if 'drivers' not in conf:
        # NOTE(cpp-cabrera): parse general opts: 'drivers'
        driver_opts = utils.dict_to_conf({'storage': storage_type})
        conf.register_opts(driver_opts, group=u'drivers')

    conf.set_override('storage', storage_type, 'drivers')
    conf.set_override('uri', uri, group=storage_group)
    return conf


def load_storage_driver(conf, cache, storage_type=None, control_mode=False):
    """Loads a storage driver and returns it.

    The driver's initializer will be passed conf and cache as
    its positional args.

    :param conf: Configuration instance to use for loading the
        driver. Must include a 'drivers' group.
    :param cache: Cache instance that the driver can (optionally)
        use to reduce latency for some operations.
    :param storage_type: The storage_type to load. If None, then
        the `drivers` option will be used.
    :param control_mode: (Default False). Determines which
        driver type to load; if False, the data driver is
        loaded. If True, the control driver is loaded.
    """

    mode = 'control' if control_mode else 'data'
    driver_type = 'zaqar.{0}.storage'.format(mode)
    storage_type = storage_type or conf['drivers'].storage

    try:
        mgr = driver.DriverManager(driver_type,
                                   storage_type,
                                   invoke_on_load=True,
                                   invoke_args=[conf, cache])

        return mgr.driver

    except Exception as exc:
        LOG.exception(exc)
        raise errors.InvalidDriver(exc)


def keyify(key, iterable):
    """Make an iterator from an iterable of dicts compared with a key.

    :param key: A key exists for all dict inside the iterable object
    :param iterable: The input iterable object
    """

    class Keyed(object):
        def __init__(self, obj):
            self.obj = obj

        def __eq__(self, other):
            return self.obj[key] == other.obj[key]

        def __ne__(self, other):
            return self.obj[key] != other.obj[key]

        def __lt__(self, other):
            return self.obj[key] < other.obj[key]

        def __le__(self, other):
            return self.obj[key] <= other.obj[key]

        def __gt__(self, other):
            return self.obj[key] > other.obj[key]

        def __ge__(self, other):
            return self.obj[key] >= other.obj[key]

    for item in iterable:
        yield Keyed(item)


def can_connect(uri, conf=None):
    """Given a URI, verifies whether it's possible to connect to it.

    :param uri: connection string to a storage endpoint
    :type uri: six.text_type
    :returns: True if can connect else False
    :rtype: bool
    """
    conf = dynamic_conf(uri, {}, conf=conf)
    storage_type = six.moves.urllib_parse.urlparse(uri).scheme

    try:
        # NOTE(cabrera): create a mock configuration containing only
        # the URI field. This should be sufficient to initialize a
        # storage driver.
        driver = load_storage_driver(conf, None,
                                     storage_type=storage_type)
        return driver.is_alive()
    except Exception as exc:
        LOG.debug('Can\'t connect to: %s \n%s' % (uri, exc))
        return False