
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import functools
import itertools

from c7n.filters import ValueFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import universal_augment, register_universal_tags
from c7n.utils import generate_arn, local_session, type_schema, chunks


@resources.register('workspaces')
class Workspace(QueryResourceManager):

    class resource_type(object):
        service = 'workspaces'
        enum_spec = ('describe_workspaces', 'Workspaces', None)
        type = 'workspace'
        name = id = dimension = 'WorkspaceId'
        filter_name = None

    augment = universal_augment
    _generate_arn = None

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn, 'workspaces', region=self.config.region,
                account_id=self.account_id, resource_type='workspace', separator='/')
        return self._generate_arn


register_universal_tags(Workspace.filter_registry, Workspace.action_registry)


@Workspace.filter_registry.register('connection-status')
class WorkspaceConnectionStatusFilter(ValueFilter):
    """Filter Workspaces based on user connection information

    :example:

    .. code-block:: yaml

            policies:

              - name: workspaces-abandoned
                resource: workspaces
                filters:
                  - type: connection-status
                    value_type: age
                    key: LastKnownUserConnectionTimestamp
                    op: ge
                    value: 90

              - name: workspaces-expensive-zombies
                resource: workspaces
                filters:
                  - "WorkspaceProperties.RunningMode": ALWAYS_ON
                  - type: connection-status
                    value_type: age
                    key: LastKnownUserConnectionTimestamp
                    op: ge
                    value: 30
    """

    schema = type_schema('connection-status', rinherit=ValueFilter.schema)
    permissions = ('workspaces:DescribeConnectionStatus',)
    annotation_key = 'c7n:ConnectionStatus'

    def get_connection_status(self, client, workspace_ids):
        connection_status_chunk = self.manager.retry(
            client.describe_workspaces_connection_status,
            WorkspaceIds=workspace_ids
        )['WorkspacesConnectionStatus']

        return connection_status_chunk

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('workspaces')
        annotate_map = {r['WorkspaceId']: r for r in resources if self.annotation_key not in r}
        with self.executor_factory(max_workers=2) as w:
            self.log.debug(
                'Querying connection status for %d workspaces' % len(annotate_map))
            for status in itertools.chain(*w.map(
                functools.partial(self.get_connection_status, client),
                chunks(annotate_map.keys(), 25)
            )):
                annotate_map[status['WorkspaceId']][self.annotation_key] = status
        return list(filter(self, resources))

    def get_resource_value(self, k, i):
        return super(WorkspaceConnectionStatusFilter, self).get_resource_value(
            k, i[self.annotation_key])
