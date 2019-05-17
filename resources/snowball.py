
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('snowball-cluster')
class SnowballCluster(QueryResourceManager):

    class resource_type(object):
        service = 'snowball'
        enum_spec = ('list_clusters', 'ClusterListEntries', None)
        detail_spec = (
            'describe_cluster', 'ClusterId', 'ClusterId', 'ClusterMetadata')
        id = 'ClusterId'
        name = 'Description'
        date = 'CreationDate'
        dimension = None
        filter_name = None
        arn = False


@resources.register('snowball')
class Snowball(QueryResourceManager):

    class resource_type(object):
        service = 'snowball'
        enum_spec = ('list_jobs', 'JobListEntries', None)
        detail_spec = (
            'describe_job', 'JobId', 'JobId', 'JobMetadata')
        id = 'JobId'
        name = 'Description'
        date = 'CreationDate'
        dimension = None
        filter_name = None
        arn = False
