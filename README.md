LZ Watch Dog
--------

LZ Watch Dog is a rules engine for managing public cloud accounts and
resources. It allows users to define policies to enable a well managed
cloud infrastructure, that\'s both secure and cost optimized. It
consolidates many of the adhoc scripts organizations have into a
lightweight and flexible tool, with unified metrics and reporting.

LZ Watch Dog can be used to manage AWS, Azure, and GCP environments by
ensuring real time compliance to security policies (like encryption and
access requirements), tag policies, and cost management via garbage
collection of unused resources and off-hours resource management.

LZ Watch Dog policies are written in simple YAML configuration files that
enable users to specify policies on a resource type (EC2, ASG, Redshift,
CosmosDB, PubSub Topic) and are constructed from a vocabulary of filters
and actions.

It integrates with the cloud native serverless capabilities of each
provider to provide for real time enforcement of policies with builtin
provisioning. Or it can be run as a simple cron job on a server to
execute against large existing fleets.

"[Engineering the Next Generation of Cloud
Governance](https://cloudrumblings.io/cloud-adoption-engineering-the-next-generation-of-cloud-governance-21fb1a2eff60)"
by \@drewfirment

Features
--------

-   Comprehensive support for public cloud services and resources with a
    rich library of actions and filters to build policies with.
-   Supports arbitrary filtering on resources with nested boolean
    conditions.
-   Dry run any policy to see what it would do.
-   Automatically provisions serverless functions and event sources (
    AWS CloudWatchEvents, AWS Config Rules, Azure EventGrid, GCP
    AuditLog & Pub/Sub, etc)
-   Cloud provider native metrics outputs on resources that matched a
    policy
-   Structured outputs into cloud native object storage of which
    resources matched a policy.
-   Intelligent cache usage to minimize api calls.
-   Supports multi-account/subscription/project usage.

Quick Install
-------------

```
$ python3 -m venv custodian
$ source custodian/bin/activate
(custodian) $ pip install c7n
```


Usage
-----

First a role must be created with the appropriate permissions for
LZ Watch Dog to act on the resources described in the policies yaml given
as an example below. For convenience, an _example policy_ is provided for this
quick start guide. Customized AWS IAM policies will be necessary for
your own LZ Watch Dog policies

To implement the policy:

1.  Open the AWS console
2.  Navigate to IAM -\> Policies
3.  Use the _json_ option to copy the example policy as a
    new AWS IAM Policy
4.  Name the IAM policy as something recognizable and save it.
5.  Navigate to IAM -\> Roles and create a role called
    _CloudCustodian-QuickStart_
6.  Assign the role the IAM policy created above.

Now with the pre-requisite completed; you are ready continue and run
custodian.

A LZ Watch Dog policy file needs to be created in YAML format, as an
example

```yaml
policies:
  - name: remediate-extant-keys
  description: |
    Scan through all s3 buckets in an account and ensure all objects
    are encrypted (default to AES256).
  resource: aws.s3
    actions:
      - encrypt-keys

- name: ec2-require-non-public-and-encrypted-volumes
  resource: aws.ec2
  description: |
    Provision a lambda and cloud watch event target
    that looks at all new instances and terminates those with
    unencrypted volumes.
  mode:
    type: cloudtrail
    role: CloudCustodian-QuickStart
    events:
      - RunInstances
  filters:
    - type: ebs
      key: Encrypted
      value: false
  actions:
    - terminate

- name: tag-compliance
  resource: aws.ec2
  description: |
    Schedule a resource that does not meet tag compliance policies
    to be stopped in four days.
  filters:
    - State.Name: running
    - "tag:Environment": absent
    - "tag:AppId": absent
    - or:
      - "tag:OwnerContact": absent
      - "tag:DeptID": absent
  actions:
    - type: mark-for-op
      op: stop
      days: 4
```

Given that, you can run LZ Watch Dog with

```
# Validate the configuration (note this happens by default on run)
$ custodian validate policy.yml

# Dryrun on the policies (no actions executed) to see what resources
# match each policy.
$ custodian run --dryrun -s out policy.yml

# Run the policy
$ custodian run -s out policy.yml
```

You can run it with Docker as well

```
# Download the image
$ docker pull cloudcustodian/c7n
$ mkdir output

# Run the policy
#
# This will run the policy using only the environment variables for authentication
$ docker run -it \
  -v $(pwd)/output:/home/custodian/output \
  -v $(pwd)/policy.yml:/home/custodian/policy.yml \
  --env-file <(env | grep "^AWS\|^AZURE\|^GOOGLE") \
  cloudcustodian/c7n run -v -s /home/custodian/output /home/custodian/policy.yml

# Run the policy (using AWS's generated credentials from STS)
#
# NOTE: We mount the ``.aws/credentials`` and ``.aws/config`` directories to
# the docker container to support authentication to AWS using the same credentials
# credentials that are available to the local user if authenticating with STS.
# This exposes your container to additional credentials than may be necessary,
# i.e. additional credentials may be available inside of the container than is
# minimally necessary.

$ docker run -it \
  -v $(pwd)/output:/home/custodian/output \
  -v $(pwd)/policy.yml:/home/custodian/policy.yml \
  -v $(cd ~ && pwd)/.aws/credentials/home/custodian/:.aws/credentials \
  -v $(cd ~ && pwd)/.aws/config:/home/custodian/.aws/config \
  --env-file <(env | grep "^AWS") \
  cloudcustodian/c7n run -v -s /home/custodian/output /home/custodian/policy.yml
```

LZ Watch Dog supports a few other useful subcommands and options, including
outputs to S3, Cloudwatch metrics, STS role assumption. Policies go
together like Lego bricks with actions and filters.
