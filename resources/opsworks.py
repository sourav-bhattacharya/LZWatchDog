
from __future__ import absolute_import, division, print_function, unicode_literals

from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema
from c7n import utils


class StateTransitionFilter(object):
    """Filter instances by state.

    Try to simplify construction for policy authors by automatically
    filtering elements (filters or actions) to the instances states
    they are valid for. Separate from ec2 class as uses ['status']
    instead of ['State']['Name'].

    For more details see
    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html
    """
    valid_origin_states = ()

    def filter_instance_state(self, instances, states=None):
        states = states or self.valid_origin_states
        orig_length = len(instances)
        results = [i for i in instances
                   if i['Status'] in states]
        self.log.info("%s %d of %d instances" % (
            self.__class__.__name__, len(results), orig_length))
        return results


@resources.register('opswork-stack')
class OpsworkStack(QueryResourceManager):

    class resource_type(object):
        service = 'opsworks'
        enum_spec = ('describe_stacks', 'Stacks', None)
        filter_name = 'StackIds'
        filter_type = 'list'
        id = 'StackId'
        name = 'Name'
        date = 'CreatedAt'
        dimension = "StackId"
        arn = "Arn"


@OpsworkStack.action_registry.register('delete')
class DeleteStack(BaseAction, StateTransitionFilter):
    """Action to delete Opswork Stack

    It is recommended to use a filter to avoid unwanted deletion of stacks

    :example:

    .. code-block:: yaml

            policies:
              - name: opswork-delete
                resource: opswork-stack
                actions:
                  - delete
    """

    valid_origin_states = ('terminating', 'stopping', 'shutting_down', 'terminated', 'stopped')

    schema = type_schema('delete')
    permissions = ("opsworks:DescribeApps", "opsworks:DescribeLayers",
        "opsworks:DescribeInstances", "opsworks:DeleteStack",
        "opsworks:DeleteApp", "opsworks:DeleteLayer",
        "opsworks:DeleteInstance")

    def process(self, stacks):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_stack, stacks))

    def process_stack(self, stack):
        client = local_session(
            self.manager.session_factory).client('opsworks')
        try:
            stack_id = stack['StackId']
            for app in client.describe_apps(StackId=stack_id)['Apps']:
                client.delete_app(AppId=app['AppId'])
            instances = client.describe_instances(StackId=stack_id)['Instances']
            orig_length = len(instances)
            instances = self.filter_instance_state(instances)
            if(len(instances) != orig_length):
                self.log.exception(
                    "All instances must be stopped before deletion. Stack Id: %s Name: %s." %
                    (stack_id, stack['Name']))
                return
            for instance in instances:
                instance_id = instance['InstanceId']
                # Validation Exception raised for instances that are stopping when delete is called
                retryable = ('ValidationException'),
                retry = utils.get_retry(retryable, max_attempts=8)
                try:
                    retry(client.delete_instance, InstanceId=instance_id)
                except ClientError as e2:
                    if e2.response['Error']['Code'] in retryable:
                        return True
                    raise
            for layer in client.describe_layers(StackId=stack_id)['Layers']:
                client.delete_layer(LayerId=layer['LayerId'])
            client.delete_stack(StackId=stack_id)
        except ClientError as e:
            self.log.exception(
                "Exception deleting stack:\n %s" % e)


@OpsworkStack.action_registry.register('stop')
class StopStack(BaseAction):
    """Action to stop Opswork Stack (Stops all instances under stack)

    It is recommended to use a filter to avoid unwanted stopping of stacks

    :example:

    .. code-block:: yaml

            policies:
              - name: opswork-stop
                resource: opswork-stack
                actions:
                  - stop
    """

    schema = type_schema('stop')
    permissions = ("opsworks:StopStack",)

    def process(self, stacks):
        with self.executor_factory(max_workers=10) as w:
            list(w.map(self.process_stack, stacks))

    def process_stack(self, stack):
        client = local_session(
            self.manager.session_factory).client('opsworks')
        try:
            stack_id = stack['StackId']
            client.stop_stack(StackId=stack_id)
        except ClientError as e:
            self.log.exception(
                "Exception stopping stack:\n %s" % e)


@resources.register('opswork-cm')
class OpsworksCM(QueryResourceManager):

    class resource_type(object):
        service = "opsworkscm"
        enum_spec = ('describe_servers', 'Servers', None)
        filter_name = 'ServerName'
        filter_type = 'scalar'
        name = id = 'ServerName'
        date = 'CreatedAt'
        dimension = None
        arn = "ServerArn"


@OpsworksCM.action_registry.register('delete')
class CMDelete(BaseAction):
    """Action to delete Opswork for Chef Automate server

    It is recommended to use a filter to avoid unwanted deletion of servers

    :example:

    .. code-block:: yaml

            policies:
              - name: opsworks-cm-delete
                resource: opswork-cm
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("opsworks-cm:DeleteServer",)

    def process(self, servers):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_server, servers))

    def process_server(self, server):
        client = local_session(
            self.manager.session_factory).client('opsworkscm')
        try:
            client.delete_server(ServerName=server['ServerName'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting server:\n %s" % e)
