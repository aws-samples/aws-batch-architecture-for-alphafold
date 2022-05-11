import os
from aws_cdk import core
from dotenv import load_dotenv

from stacks.vpc import VpcStack
from stacks.codepipeline import CodePipelineStack
from stacks.sagemaker import SageMakerStack
from stacks.batch import BatchStack
from stacks.chaliceapp import ChaliceApp

load_dotenv()
app = core.App()

environment = core.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"])

vpc_stack = VpcStack(app, "LokaFoldVpcStack", env=environment)

codepipeline_stack = CodePipelineStack(
    app, 
    "LokaFoldCodePipelineStack", 
    vpc_stack.key, 
    vpc_stack.vpc,
    env=environment
)
batch_stack = BatchStack(
    app, 
    "LokaFoldBatchStack",
    vpc_stack.vpc,
    vpc_stack.sg,
    codepipeline_stack.folding_container,
    codepipeline_stack.download_container,
    env=environment
)
sagemaker_stack = SageMakerStack(
    app, 
    "LokaFoldSagemakerStack",
    vpc_stack.vpc,
    vpc_stack.sg,
    codepipeline_stack.repo,
    vpc_stack.key,
    os.environ.get("launch_sagemaker", True),
    env=environment
)
# TODO: add vpc to lambda
chalice_stack = ChaliceApp(
    app, 
    "LokaFoldChaliceStack",
    env=environment
)
app.synth()
