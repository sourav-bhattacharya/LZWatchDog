
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('waf')
class WAF(QueryResourceManager):

    class resource_type(object):
        service = "waf"
        enum_spec = ("list_web_acls", "WebACLs", None)
        detail_spec = ("get_web_acl", "WebACLId", "WebACLId", "WebACL")
        name = "Name"
        id = "WebACLId"
        dimension = "WebACL"
        filter_name = None
        config_type = "AWS::WAF::WebACL"
        type = "webacl"


@resources.register('waf-regional')
class RegionalWAF(QueryResourceManager):

    class resource_type(object):
        service = "waf-regional"
        enum_spec = ("list_web_acls", "WebACLs", None)
        detail_spec = ("get_web_acl", "WebACLId", "WebACLId", "WebACL")
        name = "Name"
        id = "WebACLId"
        dimension = "WebACL"
        filter_name = None
        config_type = "AWS::WAFRegional::WebACL"
        type = "webacl"
