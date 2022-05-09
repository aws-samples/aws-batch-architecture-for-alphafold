import os
from aws_cdk import core as cdk
from aws_cdk.core import (
    Construct,
    CfnParameter,
)
import aws_cdk.aws_iam as iam
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_batch as batch
import aws_cdk.aws_kms as kms

class VpcStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # KMS
        self.key = kms.Key(self, "EncryptionKey", enable_key_rotation=True)

        self.key.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Create*",
                    "kms:Describe*",
                    "kms:Enable*",
                    "kms:List*",
                    "kms:Put*",
                    "kms:Update*",
                    "kms:Revoke*",
                    "kms:Disable*",
                    "kms:Get*",
                    "kms:Delete*",
                    "kms:TagResource",
                    "kms:UntagResource",
                    "kms:ScheduleKeyDeletion",
                    "kms:CancelKeyDeletion",
                ],
                resources=["*"],
                principals=[iam.AnyPrincipal()],
            ),
        )

        self.key.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                resources=["*"],
                principals=[iam.AnyPrincipal()],
            ),
        )
        self.key.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                resources=["*"],
                principals=[iam.AnyPrincipal()],
            ),
        )
        
        # Network Configuration
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            vpc_name="LokaFoldVpc", 
            cidr="10.0.0.0/16", 
            max_azs=1
        )