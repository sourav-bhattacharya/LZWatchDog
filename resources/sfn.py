
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import Tag, RemoveTag


@resources.register('step-machine')
class StepFunction(QueryResourceManager):
    """AWS Step Functions State Machine"""

    class resource_type(object):
        service = 'stepfunctions'
        enum_spec = ('list_state_machines', 'stateMachines', None)
        arn = id = 'stateMachineArn'
        name = 'name'
        date = 'creationDate'
        dimension = None
        detail_spec = (
            "describe_state_machine", "stateMachineArn",
            'stateMachineArn', None)
        filter_name = None


@StepFunction.action_registry.register('tag')
class TagStepFunction(Tag):
    """Action to create tag(s) on a step function

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-step-function
                resource: step-machine
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """

    permissions = ('stepfunctions:TagResource',)

    def process_resource_set(self, client, resources, tags):

        tags_lower = []

        for tag in tags:
            tags_lower.append({k.lower(): v for k, v in tag.items()})

        for r in resources:
            client.tag_resource(resourceArn=r['stateMachineArn'], tags=tags_lower)


@StepFunction.action_registry.register('remove-tag')
class UnTagStepFunction(RemoveTag):
    """Action to create tag(s) on a step function

    :example:

    .. code-block:: yaml

            policies:
              - name: step-function-remove-tag
                resource: step-machine
                actions:
                  - type: remove-tag
                    tags: ["test"]
    """

    permissions = ('stepfunctions:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):

        for r in resources:
            client.untag_resource(resourceArn=r['stateMachineArn'], tagKeys=tag_keys)
