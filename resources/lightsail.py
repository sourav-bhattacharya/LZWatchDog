
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('lightsail-instance')
class Instance(QueryResourceManager):

    class resource_type(object):
        service = 'lightsail'
        enum_spec = ('get_instances', 'instances', None)
        arn = id = 'arn'
        name = 'name'
        date = 'createdAt'
        dimension = None
        filter_name = None


@resources.register('lightsail-db')
class Database(QueryResourceManager):

    class resource_type(object):
        service = 'lightsail'
        enum_spec = ('get_relational_databases', 'relationDatabases', None)
        name = 'name'
        arn = id = 'arn'
        date = 'createdAt'
        dimension = None
        filter_name = None


@resources.register('lightsail-elb')
class LoadBalancer(QueryResourceManager):

    class resource_type(object):
        service = 'lightsail'
        enum_spec = ('get_load_balancers', 'loadBalancers', None)
        name = 'name'
        arn = id = 'arn'
        date = 'createdAt'
        dimension = None
        filter_name = None
