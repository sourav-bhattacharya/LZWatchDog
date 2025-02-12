# Copyright 2018 Sourav Bhattacharya, Specialist - AWS & Azure Platform Enablement @Rio Tinto, Montreal, QC, Canada 
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

from .common import BaseTest


class TestStepFunction(BaseTest):
    def test_sfn_resource(self):
        session_factory = self.replay_flight_data('test_sfn_resource')
        p = self.load_policy(
            {
                'name': 'test-sfn',
                'resource': 'step-machine',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'name',
                        'value': 'test'
                    }
                ]
            },
            config={'account_id': '101010101111'},
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources), 1)
        self.assertTrue(resources[0]['name'], 'test')

    def test_sfn_tag_resource(self):
        session_factory = self.replay_flight_data('test_sfn_tag_resource')
        p = self.load_policy(
            {
                'name': 'test-tag-sfn',
                'resource': 'step-machine',
                'actions': [
                    {
                        'type': 'tag',
                        'key': 'test',
                        'value': 'test-value'
                    }
                ]
            },
            config={'account_id': '101010101111'},
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('stepfunctions')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['stateMachineArn'])
        self.assertTrue([t for t in tags['tags'] if t['key'] == 'test'])

    def test_sfn_untag_resource(self):
        session_factory = self.replay_flight_data('test_sfn_untag_resource')
        p = self.load_policy(
            {
                'name': 'test-untag-sfn',
                'resource': 'step-machine',
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': [
                            'test'
                        ]
                    }
                ]
            },
            config={'account_id': '101010101111'},
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('stepfunctions')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['stateMachineArn'])
        self.assertTrue([t for t in tags['tags'] if t['key'] != 'test'])
