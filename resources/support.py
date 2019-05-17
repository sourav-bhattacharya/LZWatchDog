
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('support-case')
class SupportCase(QueryResourceManager):

    class resource_type(object):
        service = 'support'
        enum_spec = ('describe_cases', 'cases', None)
        filter_name = 'caseIdList'
        filter_type = 'list'
        id = 'caseId'
        name = 'displayId'
        date = 'timeCreated'
        dimension = None
        arn = False
