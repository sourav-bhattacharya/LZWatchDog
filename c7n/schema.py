# Copyright 2016-2017 Sourav Bhattacharya, Specialist - AWS & Azure Platform Enablement @Rio Tinto, Montreal, QC, Canada 
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Jsonschema validation of LZ Watch Dog config.

We start with a walkthrough of the various class registries
of resource types and assemble and generate the schema.

We do some specialization to reduce overall schema size
via reference usage, although in some cases we prefer
copies, due to issues with inheritance via reference (
allowedProperties and enum extension).

All filters and actions are annotated with schema typically using
the utils.type_schema function.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from collections import Counter
import json
import logging

from jsonschema import Draft4Validator as Validator
from jsonschema.exceptions import best_match

from c7n.policy import execution
from c7n.provider import clouds
from c7n.resources import load_resources
from c7n.resolver import ValuesFrom
from c7n.filters.core import ValueFilter, EventFilter, AgeFilter, OPERATORS, VALUE_TYPES


def validate(data, schema=None):
    if schema is None:
        schema = generate()
        Validator.check_schema(schema)

    validator = Validator(schema)
    errors = list(validator.iter_errors(data))
    if not errors:
        return check_unique(data) or []
    try:
        resp = policy_error_scope(specific_error(errors[0]), data)
        name = isinstance(
            errors[0].instance,
            dict) and errors[0].instance.get(
            'name',
            'unknown') or 'unknown'
        return [resp, name]
    except Exception:
        logging.exception(
            "specific_error failed, traceback, followed by fallback")

    return list(filter(None, [
        errors[0],
        best_match(validator.iter_errors(data)),
    ]))


def check_unique(data):
    counter = Counter([p['name'] for p in data.get('policies', [])])
    for k, v in list(counter.items()):
        if v == 1:
            counter.pop(k)
    if counter:
        return [ValueError(
            "Only one policy with a given name allowed, duplicates: {}".format(counter)),
            list(counter.keys())[0]]


def policy_error_scope(error, data):
    """Scope a schema error to its policy name and resource."""
    err_path = list(error.absolute_path)
    if err_path[0] != 'policies':
        return error
    pdata = data['policies'][err_path[1]]
    pdata.get('name', 'unknown')
    error.message = "Error on policy:{} resource:{}\n".format(
        pdata.get('name', 'unknown'), pdata.get('resource', 'unknown')) + error.message
    return error


def specific_error(error):
    """Try to find the best error for humans to resolve

    The jsonschema.exceptions.best_match error is based purely on a
    mix of a strong match (ie. not anyOf, oneOf) and schema depth,
    this often yields odd results that are semantically confusing,
    instead we can use a bit of structural knowledge of schema to
    provide better results.
    """
    if error.validator not in ('anyOf', 'oneOf'):
        return error

    r = t = None

    if isinstance(error.instance, dict):
        t = error.instance.get('type')
        r = error.instance.get('resource')

    if r is not None:
        found = None
        for idx, v in enumerate(error.validator_value):
            if v['$ref'].rsplit('/', 2)[1].endswith(r):
                found = idx
                break
        if found is not None:
            # error context is a flat list of all validation
            # failures, we have to index back to the policy
            # of interest.
            for e in error.context:
                # resource policies have a fixed path from
                # the top of the schema
                if e.absolute_schema_path[4] == found:
                    return specific_error(e)
            return specific_error(error.context[idx])

    if t is not None:
        found = None
        for idx, v in enumerate(error.validator_value):
            if '$ref' in v and v['$ref'].rsplit('/', 2)[-1] == t:
                found = idx
                break
            elif 'type' in v and t in v['properties']['type']['enum']:
                found = idx
                break

        if found is not None:
            for e in error.context:
                for el in reversed(e.absolute_schema_path):
                    if isinstance(el, int):
                        if el == found:
                            return e
                        break
    return error


def generate(resource_types=()):
    resource_defs = {}
    definitions = {
        'resources': resource_defs,
        'iam-statement': {
            'additionalProperties': False,
            'type': 'object',
            'properties': {
                'Sid': {'type': 'string'},
                'Effect': {'type': 'string', 'enum': ['Allow', 'Deny']},
                'Principal': {'anyOf': [
                    {'type': 'string'},
                    {'type': 'object'}, {'type': 'array'}]},
                'NotPrincipal': {'anyOf': [{'type': 'object'}, {'type': 'array'}]},
                'Action': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                'NotAction': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                'Resource': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                'NotResource': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                'Condition': {'type': 'object'}
            },
            'required': ['Sid', 'Effect'],
            'oneOf': [
                {'required': ['Principal', 'Action', 'Resource']},
                {'required': ['NotPrincipal', 'Action', 'Resource']},
                {'required': ['Principal', 'NotAction', 'Resource']},
                {'required': ['NotPrincipal', 'NotAction', 'Resource']},
                {'required': ['Principal', 'Action', 'NotResource']},
                {'required': ['NotPrincipal', 'Action', 'NotResource']},
                {'required': ['Principal', 'NotAction', 'NotResource']},
                {'required': ['NotPrincipal', 'NotAction', 'NotResource']}
            ]
        },
        'actions': {},
        'filters': {
            'value': ValueFilter.schema,
            'event': EventFilter.schema,
            'age': AgeFilter.schema,
            # Shortcut form of value filter as k=v
            'valuekv': {
                'type': 'object',
                'minProperties': 1,
                'maxProperties': 1},
        },
        'filters_common': {
            'comparison_operators': {
                'enum': list(OPERATORS.keys())},
            'value_types': {'enum': VALUE_TYPES},
            'value_from': ValuesFrom.schema,
            'value': {'oneOf': [
                {'type': 'array'},
                {'type': 'string'},
                {'type': 'boolean'},
                {'type': 'number'},
                {'type': 'null'}]},
        },
        'policy': {
            'type': 'object',
            'required': ['name', 'resource'],
            'additionalProperties': False,
            'properties': {
                'name': {
                    'type': 'string',
                    'pattern': "^[A-z][A-z0-9]*(-[A-z0-9]+)*$"},
                'region': {'type': 'string'},
                'tz': {'type': 'string'},
                'start': {'format': 'date-time'},
                'end': {'format': 'date-time'},
                'resource': {'type': 'string'},
                'max-resources': {'anyOf': [
                    {'type': 'integer', 'minimum': 1},
                    {'$ref': '#/definitions/max-resources-properties'}
                ]},
                'max-resources-percent': {'type': 'number', 'minimum': 0, 'maximum': 100},
                'comment': {'type': 'string'},
                'comments': {'type': 'string'},
                'description': {'type': 'string'},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
                'mode': {'$ref': '#/definitions/policy-mode'},
                'source': {'enum': ['describe', 'config']},
                'actions': {
                    'type': 'array',
                },
                'filters': {
                    'type': 'array'
                },
                #
                # TODO: source queries should really move under
                # source. This was initially used for describe sources
                # to expose server side query mechanisms, however its
                # important to note it also prevents resource cache
                # utilization between policies that have different
                # queries.
                'query': {
                    'type': 'array', 'items': {'type': 'object'}}

            },
        },
        'policy-mode': {
            'anyOf': [e.schema for _, e in execution.items()],
        },
        'max-resources-properties': {
            'type': 'object',
            'properties': {
                'amount': {"type": 'integer', 'minimum': 1},
                'op': {'enum': ['or', 'and']},
                'percent': {'type': 'number', 'minimum': 0, 'maximum': 100}
            }
        }
    }

    resource_refs = []
    for cloud_name, cloud_type in clouds.items():
        for type_name, resource_type in cloud_type.resources.items():
            if resource_types and type_name not in resource_types:
                continue
            alias_name = None
            r_type_name = "%s.%s" % (cloud_name, type_name)
            if cloud_name == 'aws':
                alias_name = type_name
            resource_refs.append(
                process_resource(
                    r_type_name,
                    resource_type,
                    resource_defs,
                    alias_name,
                    definitions
                ))

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        'id': 'http://schema.cloudcustodian.io/v0/custodian.json',
        'definitions': definitions,
        'type': 'object',
        'required': ['policies'],
        'additionalProperties': False,
        'properties': {
            'vars': {'type': 'object'},
            'policies': {
                'type': 'array',
                'additionalItems': False,
                'items': {'anyOf': resource_refs}
            }
        }
    }

    return schema


def process_resource(type_name, resource_type, resource_defs, alias_name=None, definitions=None):
    r = resource_defs.setdefault(type_name, {'actions': {}, 'filters': {}})

    seen_actions = set()  # Aliases get processed once
    action_refs = []
    for action_name, a in resource_type.action_registry.items():
        if a in seen_actions:
            continue
        else:
            seen_actions.add(a)
        if a.schema_alias:
            if action_name in definitions['actions']:

                if definitions['actions'][action_name] != a.schema: # NOQA
                    msg = "Schema mismatch on type:{} action:{} w/ schema alias ".format(
                        type_name, action_name)
                    raise SyntaxError(msg)
            definitions['actions'][action_name] = a.schema
            action_refs.append({'$ref': '#/definitions/actions/%s' % action_name})
        else:
            r['actions'][action_name] = a.schema
            action_refs.append(
                {'$ref': '#/definitions/resources/%s/actions/%s' % (
                    type_name, action_name)})

    # one word action shortcuts
    action_refs.append(
        {'enum': list(resource_type.action_registry.keys())})

    nested_filter_refs = []
    filters_seen = set()
    for k, v in sorted(resource_type.filter_registry.items()):
        if v in filters_seen:
            continue
        else:
            filters_seen.add(v)
        nested_filter_refs.append(
            {'$ref': '#/definitions/resources/%s/filters/%s' % (
                type_name, k)})
    nested_filter_refs.append(
        {'$ref': '#/definitions/filters/valuekv'})

    filter_refs = []
    filters_seen = set()  # for aliases
    for filter_name, f in sorted(resource_type.filter_registry.items()):
        if f in filters_seen:
            continue
        else:
            filters_seen.add(f)

        if filter_name in ('or', 'and', 'not'):
            continue
        if f.schema_alias:
            if filter_name in definitions['filters']:
                assert definitions['filters'][filter_name] == f.schema, "Schema mismatch on filter w/ schema alias" # NOQA
            definitions['filters'][filter_name] = f.schema
            filter_refs.append({
                '$ref': '#/definitions/filters/%s' % filter_name})
            continue
        elif filter_name == 'value':
            r['filters'][filter_name] = {
                '$ref': '#/definitions/filters/value'}
            r['filters']['valuekv'] = {
                '$ref': '#/definitions/filters/valuekv'}
        elif filter_name == 'event':
            r['filters'][filter_name] = {
                '$ref': '#/definitions/filters/event'}
        else:
            r['filters'][filter_name] = f.schema
        filter_refs.append(
            {'$ref': '#/definitions/resources/%s/filters/%s' % (
                type_name, filter_name)})
    filter_refs.append(
        {'$ref': '#/definitions/filters/valuekv'})

    # one word filter shortcuts
    filter_refs.append(
        {'enum': list(resource_type.filter_registry.keys())})

    resource_policy = {
        'allOf': [
            {'$ref': '#/definitions/policy'},
            {'properties': {
                'resource': {'enum': [type_name]},
                'filters': {
                    'type': 'array',
                    'items': {'anyOf': filter_refs}},
                'actions': {
                    'type': 'array',
                    'items': {'anyOf': action_refs}}}},
        ]
    }

    if alias_name:
        resource_policy['allOf'][1]['properties'][
            'resource']['enum'].append(alias_name)

    if type_name == 'ec2':
        resource_policy['allOf'][1]['properties']['query'] = {}

    r['policy'] = resource_policy
    return {'$ref': '#/definitions/resources/%s/policy' % type_name}


def resource_vocabulary(cloud_name=None, qualify_name=True):
    vocabulary = {}
    resources = {}

    for cname, ctype in clouds.items():
        if cloud_name is not None and cloud_name != cname:
            continue
        for rname, rtype in ctype.resources.items():
            if qualify_name:
                resources['%s.%s' % (cname, rname)] = rtype
            else:
                resources[rname] = rtype

    for type_name, resource_type in resources.items():
        classes = {'actions': {}, 'filters': {}, 'resource': resource_type}
        actions = []
        for action_name, cls in resource_type.action_registry.items():
            actions.append(action_name)
            classes['actions'][action_name] = cls

        filters = []
        for filter_name, cls in resource_type.filter_registry.items():
            filters.append(filter_name)
            classes['filters'][filter_name] = cls

        vocabulary[type_name] = {
            'filters': sorted(filters),
            'actions': sorted(actions),
            'classes': classes,
        }

    vocabulary["mode"] = {}
    for mode_name, cls in execution.items():
        vocabulary["mode"][mode_name] = cls

    return vocabulary


def summary(vocabulary):
    providers = {}
    non_providers = {}

    for type_name, rv in vocabulary.items():
        if '.' not in type_name:
            non_providers[type_name] = len(rv)
        else:
            provider, name = type_name.split('.', 1)
            stats = providers.setdefault(provider, {
                'resources': 0, 'actions': Counter(), 'filters': Counter()})
            stats['resources'] += 1
            for a in rv.get('actions'):
                stats['actions'][a] += 1
            for f in rv.get('filters'):
                stats['filters'][f] += 1

    for provider, stats in providers.items():
        print("%s:" % provider)
        print(" resource count: %d" % stats['resources'])
        print(" actions: %d" % len(stats['actions']))
        print(" filters: %d" % len(stats['filters']))

    for non_providers_type, length in non_providers.items():
        print("%s:" % non_providers_type)
        print(" count: %d" % length)


def json_dump(resource=None):
    load_resources()
    print(json.dumps(generate(resource), indent=2))


if __name__ == '__main__':
    json_dump()
