Capabilities
------------

LZ Watch Dog uses a flexible query language for filtering resources to a
particular subset that allows for compound querying. This essentially allows you
to filter for things like instances with EBS volumes that are not set to delete
on instance termination or stopped instances. This filtering can take into
account external data sources. It also provides for resource specific actions
around deletion, stopping, starting, encryption, tagging, etc.

The stateless design of LZ Watch Dog greatly simplifies feature development
and operations. It also provides flexibility around execution environment (local cli,
server, lambda).

When a user runs LZ Watch Dog, it will run the specified policy against the account
and region specified by the user. LZ Watch Dog will iterate over all resources
defined in the policy. In the CLI, users specify the account and region they want
to target.

During the run, each policy in the config will generate metrics that can be sent to
the cloud provider's built-in metrics service (CloudWatch, Application Insights, Stackdriver)
in the account or subscription that is targeted. The run will also generate structured record
output and logs that can be sent to the cloud provider's blob storage service (S3,
Azure Storage Accounts, Google Cloud Storage Bucket) or logging service (CloudWatch
Logs, Azure Application Insights Logs, Stackdriver logs) in the account LZ Watch Dog was
run from.

LZ Watch Dog currently provides policy definition around AWS, Azure, and Google Cloud
Platform resources:

AWS
---

- :ref:`ami`
- :ref:`asg`
- :ref:`cfn`
- :ref:`ebs`
- :ref:`ec2`
- :ref:`elb`
- :ref:`kms`
- :ref:`rds`
- :ref:`redshift`
- :ref:`s3`

Azure
-----
- :ref:`azure_vm`
- :ref:`azure_disk`
- :ref:`azure_storage`
- :ref:`azure_vnet`
- :ref:`azure_resourcegroup`
- :ref:`azure_keyvault`
- :ref:`azure_sqlserver`

GCP
---
- tbd
