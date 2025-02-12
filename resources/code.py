
from __future__ import absolute_import, division, print_function, unicode_literals

from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters.vpc import SubnetFilter, SecurityGroupFilter, VpcFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource, ConfigSource
from c7n.tags import universal_augment
from c7n.utils import local_session, get_retry, type_schema


@resources.register('codecommit')
class CodeRepository(QueryResourceManager):

    retry = staticmethod(get_retry(('Throttling',)))

    class resource_type(object):
        service = 'codecommit'
        enum_spec = ('list_repositories', 'repositories', None)
        batch_detail_spec = (
            'batch_get_repositories', 'repositoryNames', 'repositoryName',
            'repositories', None)
        id = 'repositoryId'
        arn = "Arn"
        name = 'repositoryName'
        date = 'creationDate'
        dimension = None
        filter_name = None


@CodeRepository.action_registry.register('delete')
class DeleteRepository(BaseAction):
    """Action to delete code commit

    It is recommended to use a filter to avoid unwanted deletion of repos

    :example:

    .. code-block:: yaml

            policies:
              - name: codecommit-delete
                resource: codecommit
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("codecommit:DeleteRepository",)

    def process(self, repositories):
        client = local_session(
            self.manager.session_factory).client('codecommit')
        for r in repositories:
            self.process_repository(client, r)

    def process_repository(self, client, repository):
        try:
            client.delete_repository(repositoryName=repository['repositoryName'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting repo:\n %s" % e)


@resources.register('codebuild')
class CodeBuildProject(QueryResourceManager):

    class resource_type(object):
        service = 'codebuild'
        enum_spec = ('list_projects', 'projects', None)
        batch_detail_spec = (
            'batch_get_projects', 'names', None, 'projects', None)
        name = id = 'name'
        arn = 'arn'
        date = 'created'
        dimension = None
        filter_name = None
        config_type = "AWS::CodeBuild::Project"
        type = 'project'
        universal_taggable = object()

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeBuild(self)
        elif source_type == 'config':
            return ConfigSource(self)
        raise ValueError("Unsupported source: %s for %s" % (
            source_type, self.resource_type.config_type))


class DescribeBuild(DescribeSource):

    def augment(self, resources):
        return universal_augment(
            self.manager,
            super(DescribeBuild, self).augment(resources))


@CodeBuildProject.filter_registry.register('subnet')
class BuildSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "vpcConfig.subnets[]"


@CodeBuildProject.filter_registry.register('security-group')
class BuildSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "vpcConfig.securityGroupIds[]"


@CodeBuildProject.filter_registry.register('vpc')
class BuildVpcFilter(VpcFilter):

    RelatedIdsExpression = "vpcConfig.vpcId"


@CodeBuildProject.action_registry.register('delete')
class DeleteProject(BaseAction):
    """Action to delete code build

    It is recommended to use a filter to avoid unwanted deletion of builds

    :example:

    .. code-block:: yaml

            policies:
              - name: codebuild-delete
                resource: codebuild
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("codebuild:DeleteProject",)

    def process(self, projects):
        client = local_session(self.manager.session_factory).client('codebuild')
        for p in projects:
            self.process_project(client, p)

    def process_project(self, client, project):

        try:
            client.delete_project(name=project['name'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting project:\n %s" % e)


@resources.register('codepipeline')
class CodeDeployPipeline(QueryResourceManager):

    retry = staticmethod(get_retry(('Throttling',)))

    class resource_type(object):
        service = 'codepipeline'
        enum_spec = ('list_pipelines', 'pipelines', None)
        detail_spec = ('get_pipeline', 'name', 'name', 'pipeline')
        dimension = filter_name = None
        name = id = 'name'
        date = 'created'
        filter_name = None
        type = ""
