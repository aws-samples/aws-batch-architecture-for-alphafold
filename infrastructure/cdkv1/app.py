import os
from aws_cdk import core
from dotenv import load_dotenv

from stacks.vpc import VpcStack
from stacks.fsx import FileSystemStack
from stacks.codepipeline import CodePipelineStack
from stacks.sagemaker import SageMakerStack
from stacks.batch import BatchStack
from stacks.chaliceapp import ChaliceApp

load_dotenv()
app = core.App()

environment = core.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"]
)

vpc_stack = VpcStack(
    app, 
    "LokaFoldVpcStack",
    env=environment
)
file_system_stack = FileSystemStack(
    app, 
    "LokaFoldFileSystemStack",
    vpc_stack.vpc,
    vpc_stack.sg,
    env=environment
)
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
    file_system_stack.lustre_file_system,
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
chalice_stack = ChaliceApp(
    app, 
    "LokaFoldChaliceStack",
    env=environment
)
app.synth()
