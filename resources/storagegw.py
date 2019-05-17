
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('storage-gateway')
class StorageGateway(QueryResourceManager):

    class resource_type(object):
        service = 'storagegateway'
        enum_spec = ('list_gateways', 'Gateways', None)
        arn = id = 'GatewayARN'
        name = 'GatewayName'
        dimension = None
        filter_name = None
