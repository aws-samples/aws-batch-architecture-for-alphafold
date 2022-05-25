import os
from aws_cdk import core as cdk
from aws_cdk.core import (
    Construct,
)
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_s3_deployment as s3_deploy
import aws_cdk.aws_s3_assets as s3_assets

region_name = cdk.Aws.REGION

class StorageStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # S3 bucket for fasta files
        self.input_bucket = s3.Bucket(
            self,
            "LokaFoldInputBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            versioned=False,
        )
        self.code_asset = s3_assets.Asset(
            self, 
            "LokaFoldCodeAsset",
            path=os.environ.get("code_artifact_zip")
        )
        self.code_bucket = self.code_asset.bucket
        
