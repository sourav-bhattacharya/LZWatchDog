
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.actions import Action
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('kafka')
class Kafka(QueryResourceManager):

    class resource_type(object):
        service = 'kafka'
        enum_spec = ('list_clusters', 'ClusterInfoList', None)
        arn = id = 'ClusterArn'
        name = 'ClusterName'
        date = 'CreationTime'
        dimension = None
        filter_name = 'ClusterNameFilter'
        filter_type = 'scalar'


@Kafka.filter_registry.register('security-group')
class KafkaSGFilter(SecurityGroupFilter):

    RelatedIdsExpression = "BrokerNodeGroupInfo.SecurityGroups[]"


@Kafka.filter_registry.register('subnet')
class KafkaSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "BrokerNodeGroupInfo.ClientSubnets[]"


@Kafka.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('kafka:DeleteCluster',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kafka')

        for r in resources:
            try:
                client.delete_cluster(ClusterArn=r['ClusterArn'])
            except client.exceptions.NotFoundException:
                continue
