
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('cloudsearch')
class CloudSearch(QueryResourceManager):

    class resource_type(object):
        service = "cloudsearch"
        enum_spec = ("describe_domains", "DomainStatusList", None)
        name = id = "DomainName"
        dimension = "DomainName"
        filter_name = 'DomainNames'
        filter_type = 'list'
        type = "domain"


@CloudSearch.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('cloudsearch:DeleteDomain',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudsearch')
        for r in resources:
            if r['Created'] is not True or r['Deleted'] is True:
                continue
            client.delete_domain(DomainName=r['DomainName'])
