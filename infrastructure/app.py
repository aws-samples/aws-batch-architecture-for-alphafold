from aws_cdk import App, Aws
import os
from dotenv import load_dotenv
from stack import LokaFoldBasic
from stackvpc import LokaFoldVPC

load_dotenv()
parameters = {
    "vpc_id": os.environ.get("vpc_id"),
    "az": os.environ.get("az"),
    "default_vpc_sg": os.environ.get("default_vpc_sg"),
    "public_subnet_0": os.environ.get("public_subnet_0"),
    "private_subnet_0": os.environ.get("private_subnet_0"),
    "public_route_table": os.environ.get("public_route_table"),
    "private_route_table": os.environ.get("private_route_table"),
    "internet_gateway": os.environ.get("internet_gateway"),
    "launch_sagemaker": os.environ.get("launch_sagemaker"),
    "fsx_capacity": os.environ.get("fsx_capacity"),
    "fsx_throughput": os.environ.get("fsx_throughput"),
    "alphafold_version": os.environ.get("alphafold_version")
}

app = App()
LokaFoldVPC(app, "LokaFoldVPC", **parameters, env={
    'account': os.environ['CDK_DEFAULT_ACCOUNT'],
    'region': os.environ['CDK_DEFAULT_REGION']
  })
app.synth()
