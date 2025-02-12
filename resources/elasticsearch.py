
from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import logging
import itertools

from c7n.actions import Action, ModifyVpcSecurityGroupsAction
from c7n.filters import MetricsFilter, FilterRegistry
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, VpcFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import (
    chunks, local_session, get_retry, type_schema, generate_arn)
from c7n.tags import Tag, RemoveTag, TagActionFilter, TagDelayedAction

log = logging.getLogger('custodian.es')
filters = FilterRegistry('es.filters')
filters.register('marked-for-op', TagActionFilter)


@resources.register('elasticsearch')
class ElasticSearchDomain(QueryResourceManager):

    class resource_type(object):
        service = 'es'
        type = "elasticsearch"
        enum_spec = (
            'list_domain_names', 'DomainNames[].DomainName', None)
        id = 'DomainName'
        name = 'Name'
        dimension = "DomainName"
        filter_name = None

    filter_registry = filters
    _generate_arn = _account_id = None
    retry = staticmethod(get_retry(('Throttled',)))

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                'es',
                region=self.config.region,
                account_id=self.config.account_id,
                resource_type='domain',
                separator='/')
        return self._generate_arn

    def get_resources(self, resource_ids):
        client = local_session(self.session_factory).client('es')
        return client.describe_elasticsearch_domains(
            DomainNames=resource_ids)['DomainStatusList']

    def augment(self, domains):
        client = local_session(self.session_factory).client('es')
        model = self.get_model()

        def _augment(resource_set):
            resources = self.retry(
                client.describe_elasticsearch_domains,
                DomainNames=resource_set)['DomainStatusList']
            for r in resources:
                rarn = self.generate_arn(r[model.id])
                r['Tags'] = self.retry(
                    client.list_tags, ARN=rarn).get('TagList', [])
            return resources

        with self.executor_factory(max_workers=1) as w:
            return list(itertools.chain(
                *w.map(_augment, chunks(domains, 5))))


@ElasticSearchDomain.filter_registry.register('subnet')
class Subnet(SubnetFilter):

    RelatedIdsExpression = "VPCOptions.SubnetIds[]"


@ElasticSearchDomain.filter_registry.register('security-group')
class SecurityGroup(SecurityGroupFilter):

    RelatedIdsExpression = "VPCOptions.SecurityGroupIds[]"


@ElasticSearchDomain.filter_registry.register('vpc')
class Vpc(VpcFilter):

    RelatedIdsExpression = "VPCOptions.VPCId"


@ElasticSearchDomain.filter_registry.register('metrics')
class Metrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [{'Name': 'ClientId',
                 'Value': self.manager.account_id},
                {'Name': 'DomainName',
                 'Value': resource['DomainName']}]


@ElasticSearchDomain.action_registry.register('modify-security-groups')
class ElasticSearchModifySG(ModifyVpcSecurityGroupsAction):
    """Modify security groups on an Elasticsearch domain"""

    permissions = ('es:UpdateElasticsearchDomainConfig',)

    def process(self, domains):
        groups = super(ElasticSearchModifySG, self).get_groups(domains)
        client = local_session(self.manager.session_factory).client('es')

        for dx, d in enumerate(domains):
            client.update_elasticsearch_domain_config(
                DomainName=d['DomainName'],
                VPCOptions={
                    'SecurityGroupIds': groups[dx]})


@ElasticSearchDomain.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('es:DeleteElastisearchDomain',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('es')
        for r in resources:
            client.delete_elasticsearch_domain(DomainName=r['DomainName'])


@ElasticSearchDomain.action_registry.register('tag')
class ElasticSearchAddTag(Tag):
    """Action to create tag(s) on an existing elasticsearch domain

    :example:

    .. code-block:: yaml

                policies:
                  - name: es-add-tag
                    resource: elasticsearch
                    filters:
                      - "tag:DesiredTag": absent
                    actions:
                      - type: tag
                        key: DesiredTag
                        value: DesiredValue
    """
    permissions = ('es:AddTags',)

    def process_resource_set(self, client, domains, tags):
        for d in domains:
            try:
                client.add_tags(ARN=d['ARN'], TagList=tags)
            except client.exceptions.ResourceNotFoundExecption:
                continue


@ElasticSearchDomain.action_registry.register('remove-tag')
class ElasticSearchRemoveTag(RemoveTag):
    """Removes tag(s) on an existing elasticsearch domain

    :example:

    .. code-block:: yaml

        policies:
          - name: es-remove-tag
            resource: elasticsearch
            filters:
              - "tag:ExpiredTag": present
            actions:
              - type: remove-tag
                tags: ['ExpiredTag']
        """
    permissions = ('es:RemoveTags',)

    def process_resource_set(self, client, domains, tags):
        for d in domains:
            try:
                client.remove_tags(ARN=d['ARN'], TagKeys=tags)
            except client.exceptions.ResourceNotFoundExecption:
                continue


@ElasticSearchDomain.action_registry.register('mark-for-op')
class ElasticSearchMarkForOp(TagDelayedAction):
    """Tag an elasticsearch domain for action later

    :example:

    .. code-block:: yaml

                policies:
                  - name: es-delete-missing
                    resource: elasticsearch
                    filters:
                      - "tag:DesiredTag": absent
                    actions:
                      - type: mark-for-op
                        days: 7
                        op: delete
                        tag: c7n_es_delete
    """
