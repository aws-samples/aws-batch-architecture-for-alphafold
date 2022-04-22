from aws_cdk import Aws, core
from aws_cdk import (
    aws_s3 as s3,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_fsx as fsx,
    aws_codecommit as codecommit,
    aws_kms as kms,
    aws_codebuild as codebuild,
    aws_codepipeline as codepipeline,
    aws_batch as batch,
)


class LokaFoldBasic(core.Stack):
    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Parameters
        az = core.CfnParameter(
            self,
            "StackAvailabilityZone",
            description="Availability zone to deploy stack resources",
        )

        launch_sagemaker = core.CfnParameter(
            self,
            "LaunchSageMakerNotebook",
            description="Create a SageMaker Notebook Instance",
            default="Y",
            allowed_values=["Y", "N"],
        )

        fsx_capacity = core.CfnParameter(
            self,
            "FSXForLustreStorageCapacity",
            description="Storage capacity in GB, 1200 or increments of 2400",
            default="1200",
            allowed_values=["1200", "2400", "4800", "7200"],
        )

        fsx_throughput = core.CfnParameter(
            self,
            "FSxForLustreThroughput",
            description="Throughput for unit storage (MB/s/TB) to provision for FSx for Lustre file system",
            default="500",
            allowed_values=["125", "250", "500", "1000"],
        )

        alphafold_version = core.CfnParameter(
            self,
            "AlphaFoldVersion",
            description="AlphaFold release to include as part of the job container",
            default="v2.1.2",
            allowed_values=["v2.1.2"],
        )

        # Network Configuration
        vpc = ec2.Vpc(self, "VPC", cidr="10.0.0.0/16")

        # WIP...

        # S3

        bucket = s3.Bucket(
            self,
            "CodePipelineS3Bucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=False,
        )

        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:GetObjectVersion",
                ],
                resources=bucket.arn_for_objects("*"),
                principals=[iam.AnyPrincipal()],
            )
        )
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetBucketAcl",
                    "s3:GetBucketLocation",
                    "s3:PutBucketPolicy",
                ],
                resources=bucket.bucket_arn,
                principals=[iam.AnyPrincipal],
            )
        )

        # endpoint = vpc.add_gateway_endpoint("S3Endpoint", f"com.amazonaws.{region}.s3")

        # FSx

        lustre = fsx.LustreFileSystem(
            self,
            "FSX",
            lustre_configuration=fsx.LustreConfiguration(
                deployment_type="PERSISTENT_2",
                per_unit_storage_throughput=througput,
            ),
            vpc_subnet=vpc.private_subnets[0],
        )

        # EC2 Launch Template

        ec2_role = iam.Role(
            self,
            "EC2InstanceRole",
        )

        ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_arn(
                "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
            )
        )
        ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_arn(
                "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
            )
        )
        ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_arn(
                "arn:aws:iam::aws:policy/AmazonS3FullAccess"
            )
        )

        instance_profile = iam.CfnInstanceProfile(
            self, "InstanceProfile", roles=ec2_role
        )

        user_data = None  # WIP

        launch_template = ec2.LaunchTemplate(
            self,
            "InstanceLaunchTemplate",
            launch_template_name="LokaFold-launch-template",
            user_data=user_data,
        )

        public_launch_template = ec2.LaunchTemplate(
            self,
            "PublicInstanceLaunchTemplate",
            launch_template_name="LokaFold-launch-template",
            user_data=user_data,
        )

        # Container Services

        properties = None  # WIP

        repo = codecommit.Repository(
            self,
            "CodeRepository",
            repository_name="LokaFold-code-repo",
            properties=properties,
        )

        folding_container = codecommit.Repository(
            self, "FoldingContainerRegistry", properties=properties
        )

        download_container = codecommit.Repository(
            self, "DownloadContainerRegistry", properties=properties
        )

        codebuild_role = iam.Role(self, "CodeBuildRole")

        codebuild_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_arn(
                "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess"
            )
        )
        codebuild_role.attach_inline_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[
                    f"arn:aws:logs={Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/codebuild/AWS-Alphafold*"
                ],
            )
        )
        codebuild_role.attach_inline_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:GetBucketAcl",
                    "s3:GetBucketLocation",
                ],
                resources=[f"arn:aws:s3:::codepipeline-{Aws.REGION}-*"],
            )
        )
        codebuild_role.attach_inline_policy(
            iam.PolicyStatement(
                actions=["codecommit:GitPull"],
                resources=[
                    f"arn:aws:codecommit:{Aws.REGION}:{Aws.ACCOUNT_ID}:{repo.repository_name}"
                ],
            )
        )
        codebuild_role.attach_inline_policy(
            iam.PolicyStatement(
                actions=[
                    "codebuild:CreateReportGroup",
                    "codebuild:CreateReport",
                    "codebuild:UpdateReport",
                    "codebuild:BatchPutTestCases",
                    "codebuild:BatchPutCodeCoverages",
                ],
                resources=[
                    f"arn:aws:s3:::codebuild:{Aws.REGION}:{Aws.ACCOUNT_ID}:report-group/AWS-Alphafold*"
                ],
            )
        )

        key = kms.Key(self, "EncryptionKey", enable_key_rotation=True)

        key.add_to_resource_policy(
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
            )
        )
        key.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                resources=["*"],
            )
        )
        key.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                resources=["*"],
            )
        )

        codebuild_project = codebuild.CfnProject(
            self,
            "CodeBuildProject",
            artifacts=codebuild.CfnProject.ArtifactsProperty(type="NO-ARTIFACTS"),
            encryption_key=key,
            environment=codebuild.CfnProject.EnvironmentProperty(
                compute_type="BUILD_GENERAL1_MEDIUM",
                environment_variables=[
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="FOLDING_IMAGE_TAG", value="latest"
                    ),
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="FOLDING_IMAGE_REPO_NAME",
                        value=folding_container.repository_name,
                    ),
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="AF_VERSION", value=alphafold_version.to_string()
                    ),
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="DOWNLOAD_IMAGE_TAG", value="latest"
                    ),
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="DOWNLOAD_IMAGE_REPO_NAME",
                        value=download_container.repository_name,
                    ),
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="ACCOUNT_ID", value=Aws.ACCOUNT_ID
                    ),
                ],
                image="aws/codebuild/standard:4.0",
                image_pull_credentials_type="CODEBUILD",
                privileged_mode=True,
                type="LINUX_CONTAINER",
            ),
            name="LokaFold-codebuild-project",
            resource_access_role=codebuild_role.role_arn,
            service_role=codebuild_role.role_arn,
            source=codebuild.CfnProject.SourceProperty(
                type="CODECOMMIT",
                build_spec="infrastructure.buildspec.yaml",
                git_clone_depth=1,
                location=repo.repository_clone_url_http,
            ),
            source_version="refs/heads/main",
        )

        codepipeline_role = iam.Role(self, "CodePipelineRole")

        codepipeline_role.attach_inline_policy(
            iam.PolicyStatement(
                actions=[
                    "codecommit:CancelUploadArchive",
                    "codecommit:GetBranch",
                    "codecommit:GetCommit",
                    "codecommit:GetRepository",
                    "codecommit:GetUploadArchiveStatus",
                    "codecommit:UploadArchive",
                ],
                resources=[repo.repository_arn],
            )
        )

        codepipeline_role.attach_inline_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                ],
                resources=[f"arn:aws:s3:::{bucket.bucket_name}/*"],
            )
        )

        codepipeline_role.attach_inline_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetBucketAcl",
                    "s3:GetBucketLocation",
                ],
                resources=[bucket.bucket_arn],
            )
        )

        codepipeline_role.attach_inline_policy(
            iam.PolicyStatement(
                actions=[
                    "codebuild:BatchGetBuilds",
                    "codebuild:StartBuild",
                    "codebuild:BatchGetBuildBatches",
                    "codebuild:StartBuildBatch",
                ],
                resources=[codebuild_project.attr_arn],
            )
        )

        configuration = None  # WIP

        pipeline = codepipeline.CfnPipeline(
            artifact_store=codepipeline.CfnPipeline.ArtifactStoreProperty(
                location=bucket, type="S3"
            ),
            name="Lokafold-codepipeline",
            restart_execution_on_update=True,
            role_arn=codepipeline_role.role_arn,
            stages=[
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    name="Source",
                    actions=[
                        codepipeline.CfnPipeline.ActionDeclarationProperty(
                            name="Source",
                            action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                                category="Source",
                                owner="AWS",
                                provider="CodeCommit",
                                version=1,
                            ),
                            configuration=configuration,
                            namespace="SourceVariables",
                            output_artifacts=[
                                codepipeline.CfnPipeline.OutputArtifactProperty(
                                    name="SourceArtifact"
                                )
                            ],
                            region=Aws.REGION,
                            run_order=1,
                        )
                    ],
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    name="Build",
                    actions=[
                        codepipeline.CfnPipeline.ActionDeclarationProperty(
                            name="Build",
                            action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                                category="Build",
                                owner="AWS",
                                provider="CodeBuild",
                                version=1,
                            ),
                            configuration=configuration,
                            namespace="BuildVariables",
                            input_artifacts=[
                                codepipeline.CfnPipeline.InputArtifactProperty(
                                    name="SourceArtifact"
                                )
                            ],
                            output_artifacts=[
                                codepipeline.CfnPipeline.OutputArtifactProperty(
                                    name="BuildArtifact"
                                )
                            ],
                            region=Aws.REGION,
                            run_order=2,
                        )
                    ],
                ),
            ],
        )

        # Batch Environment

        private_compute_environment = batch.CfnComputeEnvironment(
            self,
            "PrivateCPUComputeEnvironment",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                allocation_strategy="BEST_FIT_PROGRESSIVE",
                instance_role=ec2_role,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template, version="$Latest"
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[vpc.vpc_default_security_group],
                subnets=[vpc.private_subnets[0]],
                type="EC2",
            ),
            state="ENABLED",
            type="MANAGED",
        )

        public_compute_environment = batch.CfnComputeEnvironment(
            self,
            "PublicCPUComputeEnvironment",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                allocation_strategy="BEST_FIT_PROGRESSIVE",
                instance_role=ec2_role,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template, version="$Latest"
                ),
                maxv_cpus=256,
                minv_cpus=0,
                subnets=[vpc.private_subnets[0]],
                type="EC2",
            ),
            state="ENABLED",
            type="MANAGED",
        )

        gpu_compute_environment = batch.CfnComputeEnvironment(
            self,
            "PrivateGPUComputeEnvironment",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                allocation_strategy="BEST_FIT_PROGRESSIVE",
                instance_role=ec2_role,
                instance_types=["g4dn"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template, version="$Latest"
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[vpc.vpc_default_security_group],
                subnets=[vpc.private_subnets[0]],
                type="EC2",
            ),
            state="ENABLED",
            type="MANAGED",
        )
