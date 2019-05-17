
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('dlm-policy')
class DLMPolicy(QueryResourceManager):

    class resource_type(object):
        service = 'dlm'
        id = name = 'PolicyId'
        enum_spec = (
            'get_lifecycle_policies', 'Policies', None)
        detail_spec = ('get_lifecycle_policy', 'PolicyId', 'PolicyId', 'Policy')
        filter_name = 'PolicyIds'
        filter_type = 'list'
        dimension = None
        arn = False
