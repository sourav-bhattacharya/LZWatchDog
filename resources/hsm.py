
from __future__ import absolute_import, division, print_function, unicode_literals

import functools

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import (RemoveTag, Tag, universal_augment)
from c7n.utils import generate_arn


@resources.register('cloudhsm-cluster')
class CloudHSMCluster(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsmv2'
        type = 'cluster'
        resource_type = 'cloudhsm'
        enum_spec = ('describe_clusters', 'Clusters', None)
        id = name = 'ClusterId'
        filter_name = 'Filters'
        filter_type = 'scalar'
        dimension = None
        # universal_taggable = True
        # Note: resourcegroupstaggingapi still points to hsm-classic

    augment = universal_augment

    @property
    def generate_arn(self):
        return functools.partial(
            generate_arn,
            'cloudhsm',
            region=self.config.region,
            account_id=self.account_id,
            resource_type='cluster',
            separator='/')


@CloudHSMCluster.action_registry.register('tag')
class Tag(Tag):
    """Action to add tag(s) to CloudHSM Cluster(s)

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudhsm
                resource: aws.cloudhsm-cluster
                filters:
                  - "tag:OwnerName": missing
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
    """

    permissions = ('cloudhsmv2:TagResource',)

    def process_resource_set(self, client, clusters, tags):
        for c in clusters:
            try:
                client.tag_resource(ResourceId=c['ClusterId'], TagList=tags)
            except client.exceptions.CloudHsmResourceNotFoundException:
                continue


@CloudHSMCluster.action_registry.register('remove-tag')
class RemoveTag(RemoveTag):
    """Action to remove tag(s) from CloudHSM Cluster(s)

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudhsm
                resource: aws.cloudhsm-cluster
                filters:
                  - "tag:OldTagKey": present
                actions:
                  - type: remove-tag
                    tags: [OldTagKey1, OldTagKey2]
    """

    permissions = ('cloudhsmv2:UntagResource',)

    def process_resource_set(self, client, clusters, tag_keys):
        for c in clusters:
            client.untag_resource(ResourceId=c['ClusterId'], TagKeyList=tag_keys)


@resources.register('hsm')
class CloudHSM(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsm'
        enum_spec = ('list_hsms', 'HsmList', None)
        arn = id = 'HsmArn'
        name = 'Name'
        date = dimension = None
        detail_spec = (
            "describe_hsm", "HsmArn", None, None)
        filter_name = None


@resources.register('hsm-hapg')
class PartitionGroup(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsm'
        enum_spec = ('list_hapgs', 'HapgList', None)
        detail_spec = ('describe_hapg', 'HapgArn', None, None)
        arn = id = 'HapgArn'
        name = 'HapgSerial'
        date = 'LastModifiedTimestamp'
        dimension = None
        filter_name = None


@resources.register('hsm-client')
class HSMClient(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsm'
        enum_spec = ('list_luna_clients', 'ClientList', None)
        detail_spec = ('describe_luna_client', 'ClientArn', None, None)
        arn = id = 'ClientArn'
        name = 'Label'
        date = dimension = None
        filter_name = None
