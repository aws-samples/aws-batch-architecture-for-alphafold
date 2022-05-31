import os
from aws_cdk import core as cdk
from aws_cdk.core import (
    Aws,
    Construct,
)
import aws_cdk.aws_iam as iam
import aws_cdk.aws_sagemaker as sagemaker
import aws_cdk.aws_kms as kms
import aws_cdk.aws_codecommit as codecommit
import aws_cdk.aws_ec2 as ec2

class SageMakerStack(cdk.Stack):
    def __init__(self, 
                 scope: Construct, 
                 id: str, 
                 vpc: ec2.Vpc, 
                 sg: str, 
                 key: kms.Key, 
                 launch_sagemaker: bool,
                 **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        if launch_sagemaker:
            # vpc
            private_subnet = vpc.private_subnets[0]
            notebook_role = iam.Role(
                self,
                "SageMakerNotebookExecutionRole",
                path="/",
                assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            )

            notebook_role.add_managed_policy(
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    "notebook_sagemaker_policy",
                    f"arn:{Aws.PARTITION}:iam::aws:policy/AmazonSageMakerFullAccess",
                )
            )

            notebook_role.add_managed_policy(
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    "notebook_codecommit_policy",
                    f"arn:{Aws.PARTITION}:iam::aws:policy/AWSCodeCommitReadOnly",
                )
            )
            notebook_role.add_managed_policy(
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    "notebook_cloudformation_policy",
                    f"arn:{Aws.PARTITION}:iam::aws:policy/AWSCloudFormationReadOnlyAccess",
                )
            )
            notebook_role.add_managed_policy(
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    "notebook_batch_policy",
                    f"arn:{Aws.PARTITION}:iam::aws:policy/AWSBatchFullAccess",
                )
            )

            notebook_instance = sagemaker.CfnNotebookInstance(
                self,
                "LokaFoldNotebookInstance",
                direct_internet_access="Enabled",
                instance_type="ml.c4.2xlarge",
                default_code_repository=os.environ.get("code_repo"),
                kms_key_id=key.key_arn,
                role_arn=notebook_role.role_arn,
                subnet_id=private_subnet.subnet_id,
                security_group_ids=[sg],
            )
