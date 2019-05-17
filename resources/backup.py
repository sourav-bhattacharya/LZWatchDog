
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session


@resources.register('backup-plan')
class BackupPlan(QueryResourceManager):

    class resource_type(object):
        service = 'backup'
        enum_spec = ('list_backup_plans', 'BackupPlansList', None)
        detail_spec = ('get_backup_plan', 'BackupPlanId', 'BackupPlanId', 'BackupPlan')
        id = 'BackupPlanName'
        name = 'BackupPlanId'
        arn = 'BackupPlanArn'
        dimension = None
        filter_name = None
        filter_type = None

    def augment(self, resources):
        super(BackupPlan, self).augment(resources)
        client = local_session(self.session_factory).client('backup')
        results = []
        for r in resources:
            try:
                tags = client.list_tags(ResourceArn=r['BackupPlanArn']).get('Tags', {})
            except client.exceptions.ResourceNotFoundException:
                continue
            r['Tags'] = [{'Name': k, 'Value': v} for k, v in tags.items()]
            results.append(r)

        return results

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.session_factory).client('backup')
        resources = []

        for rid in resource_ids:
            try:
                resources.append(
                    client.get_backup_plan(BackupPlanId=rid)['BackupPlan'])
            except client.exceptions.ResourceNotFoundException:
                continue
        return resources
