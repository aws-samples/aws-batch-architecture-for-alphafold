from aws_cdk import core
from stacks.vpc import VpcStack
from stacks.codepipeline import CodePipelineStack
from stacks.sagemaker import SageMakerStack
from stacks.batch import BatchStack


app = core.App()

vpc_stack = VpcStack(app, "LokaFoldVpcStack")
codepipeline_stack = CodePipelineStack(
    app, 
    "LokaFoldCodePipelineStack", 
    vpc_stack.key, 
    vpc_stack.vpc
)
batch_stack = BatchStack(
    app, 
    "LokaFoldBatchStack",
    vpc_stack.vpc,
    codepipeline_stack.folding_container,
    codepipeline_stack.download_container
)
sagemaker_stack = SageMakerStack(
    app, 
    "LokaFoldSagemakerStack",
    vpc_stack.vpc,
    codepipeline_stack.repo,
    vpc_stack.key
)
app.synth()
