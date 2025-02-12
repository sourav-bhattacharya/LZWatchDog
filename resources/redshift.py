
from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import json
import logging
import itertools

from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction, ModifyVpcSecurityGroupsAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    FilterRegistry, ValueFilter, DefaultVpcBase, AgeFilter,
    CrossAccountAccessFilter)
import c7n.filters.vpc as net_filters
from c7n.filters.kms import KmsRelatedFilter

from c7n.manager import resources
from c7n.resolver import ValuesFrom
from c7n.query import QueryResourceManager
from c7n import tags
from c7n.utils import (
    type_schema, local_session, chunks, generate_arn, get_retry,
    snapshot_identifier)

log = logging.getLogger('custodian.redshift')

filters = FilterRegistry('redshift.filters')
actions = ActionRegistry('redshift.actions')
filters.register('marked-for-op', tags.TagActionFilter)


@resources.register('redshift')
class Redshift(QueryResourceManager):

    class resource_type(object):
        service = 'redshift'
        type = 'cluster'
        enum_spec = ('describe_clusters', 'Clusters', None)
        detail_spec = None
        name = id = 'ClusterIdentifier'
        filter_name = 'ClusterIdentifier'
        filter_type = 'scalar'
        date = 'ClusterCreateTime'
        dimension = 'ClusterIdentifier'
        config_type = "AWS::Redshift::Cluster"

    filter_registry = filters
    action_registry = actions
    retry = staticmethod(get_retry(('Throttling',)))

    permissions = ('iam:ListRoles',)  # account id retrieval
    _generate_arn = None

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn, 'redshift', region=self.config.region,
                account_id=self.account_id, resource_type='cluster',
                separator=':')
        return self._generate_arn


@filters.register('default-vpc')
class DefaultVpc(DefaultVpcBase):
    """ Matches if an redshift database is in the default vpc

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-default-vpc
                resource: redshift
                filters:
                  - default-vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, redshift):
        return (redshift.get('VpcId') and
                self.match(redshift.get('VpcId')) or False)


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "VpcSecurityGroups[].VpcSecurityGroupId"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = ""

    def get_permissions(self):
        return RedshiftSubnetGroup(self.manager.ctx, {}).get_permissions()

    def get_related_ids(self, resources):
        group_ids = set()
        for r in resources:
            group_ids.update(
                [s['SubnetIdentifier'] for s in
                 self.groups[r['ClusterSubnetGroupName']]['Subnets']])
        return group_ids

    def process(self, resources, event=None):
        self.groups = {r['ClusterSubnetGroupName']: r for r in
                       RedshiftSubnetGroup(self.manager.ctx, {}).resources()}
        return super(SubnetFilter, self).process(resources, event)


filters.register('network-location', net_filters.NetworkLocation)


@filters.register('param')
class Parameter(ValueFilter):
    """Filter redshift clusters based on parameter values

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-no-ssl
                resource: redshift
                filters:
                  - type: param
                    key: require_ssl
                    value: false
                    op: eq
    """

    schema = type_schema('param', rinherit=ValueFilter.schema)
    group_params = ()

    permissions = ("redshift:DescribeClusterParameters",)

    def process(self, clusters, event=None):
        groups = {}
        for r in clusters:
            for pg in r['ClusterParameterGroups']:
                groups.setdefault(pg['ParameterGroupName'], []).append(
                    r['ClusterIdentifier'])

        def get_params(group_name):
            c = local_session(self.manager.session_factory).client('redshift')
            paginator = c.get_paginator('describe_cluster_parameters')
            param_group = list(itertools.chain(*[p['Parameters']
                for p in paginator.paginate(ParameterGroupName=group_name)]))
            params = {}
            for p in param_group:
                v = p['ParameterValue']
                if v != 'default' and p['DataType'] in ('integer', 'boolean'):
                    # overkill..
                    v = json.loads(v)
                params[p['ParameterName']] = v
            return params

        with self.executor_factory(max_workers=3) as w:
            group_names = groups.keys()
            self.group_params = dict(
                zip(group_names, w.map(get_params, group_names)))
        return super(Parameter, self).process(clusters, event)

    def __call__(self, db):
        params = {}
        for pg in db['ClusterParameterGroups']:
            params.update(self.group_params[pg['ParameterGroupName']])
        return self.match(params)


@filters.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    """
    Filter a resource by its associcated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'

    :example:

        .. code-block:: yaml

            policies:
                - name: redshift-kms-key-filters
                  resource: redshift
                  filters:
                    - type: kms-key
                      key: c7n:AliasName
                      value: "^(alias/aws/)"
                      op: regex
    """
    RelatedIdsExpression = 'KmsKeyId'


@actions.register('delete')
class Delete(BaseAction):
    """Action to delete a redshift cluster

    To prevent unwanted deletion of redshift clusters, it is recommended to
    apply a filter to the rule

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-no-ssl
                resource: redshift
                filters:
                  - type: param
                    key: require_ssl
                    value: false
                    op: eq
                actions:
                  - type: delete
    """

    schema = type_schema(
        'delete', **{'skip-snapshot': {'type': 'boolean'}})

    permissions = ('redshift:DeleteCluster',)

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for db_set in chunks(clusters, size=5):
                futures.append(
                    w.submit(self.process_db_set, db_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting redshift set \n %s",
                        f.exception())

    def process_db_set(self, db_set):
        skip = self.data.get('skip-snapshot', False)
        c = local_session(self.manager.session_factory).client('redshift')
        for db in db_set:
            params = {'ClusterIdentifier': db['ClusterIdentifier']}
            if skip:
                params['SkipFinalClusterSnapshot'] = True
            else:
                params['FinalClusterSnapshotIdentifier'] = snapshot_identifier(
                    'Final', db['ClusterIdentifier'])
            try:
                c.delete_cluster(**params)
            except ClientError as e:
                if e.response['Error']['Code'] == "InvalidClusterState":
                    self.log.warning(
                        "Cannot delete cluster when not 'Available' state: %s",
                        db['ClusterIdentifier'])
                    continue
                raise


@actions.register('retention')
class RetentionWindow(BaseAction):
    """Action to set the snapshot retention period (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-snapshot-retention
                resource: redshift
                filters:
                  - type: value
                    key: AutomatedSnapshotRetentionPeriod
                    value: 21
                    op: ne
                actions:
                  - type: retention
                    days: 21
    """

    date_attribute = 'AutomatedSnapshotRetentionPeriod'
    schema = type_schema(
        'retention',
        **{'days': {'type': 'number'}})
    permissions = ('redshift:ModifyCluster',)

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_snapshot_retention,
                    cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception setting Redshift retention  \n %s",
                        f.exception())

    def process_snapshot_retention(self, cluster):
        current_retention = int(cluster.get(self.date_attribute, 0))
        new_retention = self.data['days']

        if current_retention < new_retention:
            self.set_retention_window(
                cluster,
                max(current_retention, new_retention))
            return cluster

    def set_retention_window(self, cluster, retention):
        c = local_session(self.manager.session_factory).client('redshift')
        c.modify_cluster(
            ClusterIdentifier=cluster['ClusterIdentifier'],
            AutomatedSnapshotRetentionPeriod=retention)


@actions.register('snapshot')
class Snapshot(BaseAction):
    """Action to take a snapshot of a redshift cluster

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-snapshot
                resource: redshift
                filters:
                  - type: value
                    key: ClusterStatus
                    value: available
                    op: eq
                actions:
                  - snapshot
    """

    schema = type_schema('snapshot')
    permissions = ('redshift:CreateClusterSnapshot',)

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client('redshift')
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_cluster_snapshot,
                    client, cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception creating Redshift snapshot  \n %s",
                        f.exception())
        return clusters

    def process_cluster_snapshot(self, client, cluster):
        cluster_tags = cluster.get('Tags')
        client.create_cluster_snapshot(
            SnapshotIdentifier=snapshot_identifier(
                'Backup',
                cluster['ClusterIdentifier']),
            ClusterIdentifier=cluster['ClusterIdentifier'],
            Tags=cluster_tags)


@actions.register('enable-vpc-routing')
class EnhancedVpcRoutine(BaseAction):
    """Action to enable enhanced vpc routing on a redshift cluster

    More: https://docs.aws.amazon.com/redshift/latest/mgmt/enhanced-vpc-routing.html

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-enable-enhanced-routing
                resource: redshift
                filters:
                  - type: value
                    key: EnhancedVpcRouting
                    value: false
                    op: eq
                actions:
                  - type: enable-vpc-routing
                    value: true
    """

    schema = type_schema(
        'enable-vpc-routing',
        value={'type': 'boolean'})
    permissions = ('redshift:ModifyCluster',)

    def process(self, clusters):
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_vpc_routing,
                    cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception changing Redshift VPC routing  \n %s",
                        f.exception())
        return clusters

    def process_vpc_routing(self, cluster):
        current_routing = bool(cluster.get('EnhancedVpcRouting', False))
        new_routing = self.data.get('value', True)

        if current_routing != new_routing:
            c = local_session(self.manager.session_factory).client('redshift')
            c.modify_cluster(
                ClusterIdentifier=cluster['ClusterIdentifier'],
                EnhancedVpcRouting=new_routing)


@actions.register('set-public-access')
class RedshiftSetPublicAccess(BaseAction):
    """
    Action to set the 'PubliclyAccessible' setting on a redshift cluster

    :example:

    .. code-block:: yaml

            policies:
                - name: redshift-set-public-access
                  resource: redshift
                  filters:
                    - PubliclyAccessible: true
                  actions:
                    - type: set-public-access
                      state: false
    """

    schema = type_schema(
        'set-public-access',
        state={'type': 'boolean'})
    permissions = ('redshift:ModifyCluster',)

    def set_access(self, c):
        client = local_session(self.manager.session_factory).client('redshift')
        client.modify_cluster(
            ClusterIdentifier=c['ClusterIdentifier'],
            PubliclyAccessible=self.data.get('state', False))

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = {w.submit(self.set_access, c): c for c in clusters}
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception setting Redshift public access on %s  \n %s",
                        futures[f]['ClusterIdentifier'], f.exception())
        return clusters


@actions.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):
    """Action to create an action to be performed at a later time

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-terminate-unencrypted
                resource: redshift
                filters:
                  - "tag:custodian_cleanup": absent
                  - type: value
                    key: Encrypted
                    value: false
                    op: eq
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    op: delete
                    days: 5
                    msg: "Unencrypted Redshift cluster: {op}@{action_date}"
    """


@actions.register('tag')
class Tag(tags.Tag):
    """Action to add tag/tags to a redshift cluster

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-tag
                resource: redshift
                filters:
                  - "tag:RedshiftTag": absent
                actions:
                  - type: tag
                    key: RedshiftTag
                    value: "Redshift Tag Value"
    """

    concurrency = 2
    batch_size = 5
    permissions = ('redshift:CreateTags',)

    def process_resource_set(self, client, resources, tags):
        for rarn, r in zip(self.manager.get_arns(resources), resources):
            client.create_tags(ResourceName=rarn, Tags=tags)


@actions.register('unmark')
@actions.register('remove-tag')
class RemoveTag(tags.RemoveTag):
    """Action to remove tag/tags from a redshift cluster

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-remove-tag
                resource: redshift
                filters:
                  - "tag:RedshiftTag": present
                actions:
                  - type: remove-tag
                    tags: ["RedshiftTags"]
    """

    concurrency = 2
    batch_size = 5
    permissions = ('redshift:DeleteTags',)

    def process_resource_set(self, client, resources, tag_keys):
        for rarn, r in zip(self.manager.get_arns(resources), resources):
            client.delete_tags(ResourceName=rarn, TagKeys=tag_keys)


@actions.register('tag-trim')
class TagTrim(tags.TagTrim):
    """Action to remove tags from a redshift cluster

    This can be used to prevent reaching the ceiling limit of tags on a
    resource

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-tag-trim
                resource: redshift
                filters:
                  - type: value
                    key: "length(Tags)"
                    op: ge
                    value: 10
                actions:
                  - type: tag-trim
                    space: 1
                    preserve:
                      - RequiredTag1
                      - RequiredTag2
    """

    max_tag_count = 10
    permissions = ('redshift:DeleteTags',)

    def process_tag_removal(self, client, resource, candidates):
        arn = self.manager.generate_arn(resource['DBInstanceIdentifier'])
        client.delete_tags(ResourceName=arn, TagKeys=candidates)


@resources.register('redshift-subnet-group')
class RedshiftSubnetGroup(QueryResourceManager):
    """Redshift subnet group."""

    class resource_type(object):
        service = 'redshift'
        type = 'redshift-subnet-group'
        id = name = 'ClusterSubnetGroupName'
        enum_spec = (
            'describe_cluster_subnet_groups', 'ClusterSubnetGroups', None)
        filter_name = 'ClusterSubnetGroupName'
        filter_type = 'scalar'
        dimension = None
        date = None
        config_type = "AWS::Redshift::ClusterSubnetGroup"


@resources.register('redshift-snapshot')
class RedshiftSnapshot(QueryResourceManager):
    """Resource manager for Redshift snapshots.
    """

    filter_registry = FilterRegistry('redshift-snapshot.filters')
    action_registry = ActionRegistry('redshift-snapshot.actions')

    filter_registry.register('marked-for-op', tags.TagActionFilter)

    _generate_arn = None

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn, 'redshift', region=self.config.region,
                account_id=self.account_id, resource_type='snapshot',
                separator=':')
        return self._generate_arn

    class resource_type(object):
        service = 'redshift'
        type = 'redshift-snapshot'
        enum_spec = ('describe_cluster_snapshots', 'Snapshots', None)
        name = id = 'SnapshotIdentifier'
        filter_name = None
        filter_type = None
        dimension = None
        date = 'SnapshotCreateTime'
        config_type = "AWS::Redshift::ClusterSnapshot"


@actions.register('modify-security-groups')
class RedshiftModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):
    """Modify security groups on a Redshift cluster"""

    permissions = ('redshift:ModifyCluster',)

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client('redshift')
        groups = super(
            RedshiftModifyVpcSecurityGroups, self).get_groups(clusters)

        for idx, c in enumerate(clusters):
            client.modify_cluster(
                ClusterIdentifier=c['ClusterIdentifier'],
                VpcSecurityGroupIds=groups[idx])


@RedshiftSnapshot.filter_registry.register('age')
class RedshiftSnapshotAge(AgeFilter):
    """Filters redshift snapshots based on age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-old-snapshots
                resource: redshift-snapshot
                filters:
                  - type: age
                    days: 21
                    op: gt
    """

    schema = type_schema(
        'age', days={'type': 'number'},
        op={'$ref': '#/definitions/filters_common/comparison_operators'})

    date_attribute = 'SnapshotCreateTime'


@RedshiftSnapshot.filter_registry.register('cross-account')
class RedshiftSnapshotCrossAccount(CrossAccountAccessFilter):
    """Filter all accounts that allow access to non-whitelisted accounts
    """
    permissions = ('redshift:DescribeClusterSnapshots',)
    schema = type_schema(
        'cross-account',
        whitelist={'type': 'array', 'items': {'type': 'string'}},
        whitelist_from=ValuesFrom.schema)

    def process(self, snapshots, event=None):
        accounts = self.get_accounts()
        snapshots = [s for s in snapshots if s.get('AccountsWithRestoreAccess')]
        results = []
        for s in snapshots:
            s_accounts = {a.get('AccountId') for a in s[
                'AccountsWithRestoreAccess']}
            delta_accounts = s_accounts.difference(accounts)
            if delta_accounts:
                s['c7n:CrossAccountViolations'] = list(delta_accounts)
                results.append(s)
        return results


@RedshiftSnapshot.action_registry.register('delete')
class RedshiftSnapshotDelete(BaseAction):
    """Filters redshift snapshots based on age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-delete-old-snapshots
                resource: redshift-snapshot
                filters:
                  - type: age
                    days: 21
                    op: gt
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('redshift:DeleteClusterSnapshot',)

    def process(self, snapshots):
        log.info("Deleting %d Redshift snapshots", len(snapshots))
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, snapshot_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting snapshot set \n %s",
                        f.exception())
        return snapshots

    def process_snapshot_set(self, snapshots_set):
        c = local_session(self.manager.session_factory).client('redshift')
        for s in snapshots_set:
            c.delete_cluster_snapshot(
                SnapshotIdentifier=s['SnapshotIdentifier'],
                SnapshotClusterIdentifier=s['ClusterIdentifier'])


@RedshiftSnapshot.action_registry.register('mark-for-op')
class RedshiftSnapshotTagDelayedAction(tags.TagDelayedAction):
    """Action to create a delayed actions to be performed on a redshift snapshot

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-snapshot-expiring
                resource: redshift-snapshot
                filters:
                  - "tag:custodian_cleanup": absent
                  - type: age
                    days: 14
                    op: eq
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    msg: "Snapshot expiring: {op}@{action_date}"
                    op: delete
                    days: 7
    """


@RedshiftSnapshot.action_registry.register('tag')
class RedshiftSnapshotTag(tags.Tag):
    """Action to add tag/tags to a redshift snapshot

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-required-tags
                resource: redshift-snapshot
                filters:
                  - "tag:RequiredTag1": absent
                actions:
                  - type: tag
                    key: RequiredTag1
                    value: RequiredValue1
    """

    concurrency = 2
    batch_size = 5
    permissions = ('redshift:CreateTags',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            arn = self.manager.generate_arn(
                r['ClusterIdentifier'] + '/' + r['SnapshotIdentifier'])
            client.create_tags(ResourceName=arn, Tags=tags)


@RedshiftSnapshot.action_registry.register('unmark')
@RedshiftSnapshot.action_registry.register('remove-tag')
class RedshiftSnapshotRemoveTag(tags.RemoveTag):
    """Action to remove tag/tags from a redshift snapshot

    :example:

    .. code-block:: yaml

            policies:
              - name: redshift-remove-tags
                resource: redshift-snapshot
                filters:
                  - "tag:UnusedTag1": present
                actions:
                  - type: remove-tag
                    tags: ["UnusedTag1"]
    """

    concurrency = 2
    batch_size = 5
    permissions = ('redshift:DeleteTags',)

    def process_resource_set(self, client, resources, tag_keys):
        for r in resources:
            arn = self.manager.generate_arn(
                r['ClusterIdentifier'] + '/' + r['SnapshotIdentifier'])
            client.delete_tags(ResourceName=arn, TagKeys=tag_keys)


@RedshiftSnapshot.action_registry.register('revoke-access')
class RedshiftSnapshotRevokeAccess(BaseAction):
    """Revokes ability of accounts to restore a snapshot

    :example:

        .. code-block: yaml

            policies:
              - name: redshift-snapshot-revoke-access
                resource: redshift-snapshot
                filters:
                  - type: cross-account
                    whitelist:
                      - 012345678910
                actions:
                  - type: revoke-access
    """
    permissions = ('redshift:RevokeSnapshotAccess',)
    schema = type_schema('revoke-access')

    def validate(self):
        for f in self.manager.iter_filters():
            if isinstance(f, RedshiftSnapshotCrossAccount):
                return self
        raise PolicyValidationError(
            '`revoke-access` may only be used in '
            'conjunction with `cross-account` filter on %s' % (self.manager.data,))

    def process_snapshot_set(self, client, snapshot_set):
        for s in snapshot_set:
            for a in s.get('c7n:CrossAccountViolations', []):
                try:
                    self.manager.retry(
                        client.revoke_snapshot_access,
                        SnapshotIdentifier=s['SnapshotIdentifier'],
                        AccountWithRestoreAccess=a)
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ClusterSnapshotNotFound':
                        continue
                    raise

    def process(self, snapshots):
        client = local_session(self.manager.session_factory).client('redshift')
        with self.executor_factory(max_workers=2) as w:
            futures = {}
            for snapshot_set in chunks(snapshots, 25):
                futures[w.submit(
                    self.process_snapshot_set, client, snapshot_set)
                ] = snapshot_set
            for f in as_completed(futures):
                if f.exception():
                    self.log.exception(
                        'Exception while revoking access on %s: %s' % (
                            ', '.join(
                                [s['SnapshotIdentifier'] for s in futures[f]]),
                            f.exception()))
