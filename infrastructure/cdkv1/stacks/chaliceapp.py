import os
from aws_cdk.core import (
    Construct,
)
from aws_cdk import core as cdk
from chalice.cdk import Chalice
import aws_cdk.aws_s3 as s3

RUNTIME_SOURCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 
    "lokafold-app"
)

class ChaliceApp(cdk.Stack):
    def __init__(self, scope: Construct, id: str, bucket: s3.Bucket, **kwargs):
        super().__init__(scope, id, **kwargs)
        
        self.chalice = Chalice(
            self, 
            "ChaliceApp",
            source_dir=RUNTIME_SOURCE_DIR,
            stage_config={
                "api_gateway_stage": "dev",
                "lambda_timeout": 60,
                "tags": {
                    "project": "lokafold"
                },
                "lambda_memory_size": 128,
                "manage_iam_role": True,
                "autogen_policy": False,
                "iam_policy_file": "policy.json",
                "environment_variables": {
                    "FASTA_BUCKET": bucket.bucket_name
                }
            }
        )
        