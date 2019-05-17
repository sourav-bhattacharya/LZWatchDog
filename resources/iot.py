
from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('iot')
class IoT(QueryResourceManager):

    class resource_type(object):
        service = 'iot'
        enum_spec = ('list_things', 'things', None)
        name = "thingName"
        id = "thingName"
        arn = "thingArn"
        dimension = None
        default_report_fields = (
            'thingName',
            'thingTypeName'
        )
