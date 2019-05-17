
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('gamelift-build')
class GameLiftBuild(QueryResourceManager):

    class resource_type(object):
        service = 'gamelift'
        enum_spec = ('list_builds', 'Builds', None)
        id = 'BuildId'
        name = 'Name'
        date = 'CreationTime'
        dimension = None
        filter_name = None
        arn = False


@resources.register('gamelift-fleet')
class GameLiftFleet(QueryResourceManager):

    class resource_type(object):
        service = 'gamelift'
        enum_spec = ('list_fleets', 'FleetIds', None)
        id = 'FleetId'
        arn = "FleetArn"
        name = 'Name'
        date = 'CreationTime'
        dimension = None
        batch_detail_spec = (
            "describe_fleet_attributes", "FleetIds", None, "FleetAttributes", None)
        filter_name = None
