
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('directconnect')
class DirectConnect(QueryResourceManager):

    class resource_type(object):
        service = 'directconnect'
        enum_spec = ('describe_connections', 'connections', None)
        id = 'connectionId'
        name = 'connectionName'
        filter_name = 'connectionId'
        dimension = None
        type = "dxcon"
