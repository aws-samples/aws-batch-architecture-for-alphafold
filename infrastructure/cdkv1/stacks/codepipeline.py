import os
from aws_cdk import core as cdk
from aws_cdk.core import (
    Aws,
    Construct
)
import aws_cdk.aws_iam as iam
import aws_cdk.aws_ecr as ecr
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_codecommit as codecommit
import aws_cdk.aws_codebuild as codebuild
import aws_cdk.aws_codepipeline as codepipeline



class CodePipelineStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, key, vpc, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # TODO: move to .env        
        codebuild_project_name = "LokaFold-codebuild-project"

        bucket = s3.Bucket(
            self,
            "CodePipelineS3Bucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            # access_control=s3.BucketAccessControl.PRIVATE,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            versioned=False,
        )

        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:GetObjectVersion",
                ],
                resources=[bucket.arn_for_objects("*")],
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
                resources=[bucket.bucket_arn],
                principals=[iam.AnyPrincipal()],
            ),
        )

        # Container Services
        self.repo = codecommit.CfnRepository(
            self,
            "CodeRepository",
            repository_name="LokaFold-code-repo",
            code=codecommit.CfnRepository.CodeProperty(
                branch_name="main",
                s3=codecommit.CfnRepository.S3Property(
                    bucket="cfn-without-vpc",
                    key="lokafold-v2.2.0.zip",
                ),
            ),
        )
        
        self.folding_container = ecr.CfnRepository(
            self,
            "FoldingContainerRegistry",
            encryption_configuration=ecr.CfnRepository.EncryptionConfigurationProperty(
                encryption_type="AES256"
            ),
            image_scanning_configuration=ecr.CfnRepository.ImageScanningConfigurationProperty(
                scan_on_push=True
            ),
            repository_name="lokafold-folding-container-repo",
        )
        # this will cause stack to fail if it's already created
        self.folding_container.apply_removal_policy(cdk.RemovalPolicy.RETAIN)
        
        self.download_container = ecr.CfnRepository(
            self,
            "DownloadContainerRegistry",
            encryption_configuration=ecr.CfnRepository.EncryptionConfigurationProperty(
                encryption_type="AES256"
            ),
            image_scanning_configuration=ecr.CfnRepository.ImageScanningConfigurationProperty(
                scan_on_push=True
            ),
            repository_name="lokafold_download_container_repo",
        )
        self.download_container.apply_removal_policy(cdk.RemovalPolicy.RETAIN)

        codebuild_role = iam.Role(
            self,
            "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
        )
        codebuild_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_arn(
                self,
                "codebuild_ecr_policy",
                "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess",
            )
        )
        codebuild_role.attach_inline_policy(
            iam.Policy(
                self,
                "codebuild_role_policy",
                statements=[
                    iam.PolicyStatement(
                        actions=[
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents",
                        ],
                        resources=[
                            f"arn:aws:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/codebuild/{codebuild_project_name}:log-stream:*"
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "s3:PutObject",
                            "s3:GetObject",
                            "s3:GetObjectVersion",
                            "s3:GetBucketAcl",
                            "s3:GetBucketLocation",
                        ],
                        resources=[f"arn:aws:s3:::codepipeline-{Aws.REGION}-*"],
                    ),
                    iam.PolicyStatement(
                        actions=["codecommit:GitPull"],
                        resources=[
                            f"arn:aws:codecommit:{Aws.REGION}:{Aws.ACCOUNT_ID}:{self.repo.repository_name}"
                        ],
                    ),
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
                    ),
                ],
            )
        )
        
        codebuild_project = codebuild.CfnProject(
            self,
            "CodeBuildProject",
            artifacts=codebuild.CfnProject.ArtifactsProperty(type="NO_ARTIFACTS"),
            encryption_key=key.key_id,
            cache=codebuild.CfnProject.ProjectCacheProperty(
                type="LOCAL",
                modes=["LOCAL_DOCKER_LAYER_CACHE"],
            ),
            environment=codebuild.CfnProject.EnvironmentProperty(
                compute_type="BUILD_GENERAL1_MEDIUM",
                environment_variables=[
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="FOLDING_IMAGE_TAG", value="latest"
                    ),
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="FOLDING_IMAGE_REPO_NAME",
                        value=self.folding_container.repository_name,
                    ),
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="AF_VERSION", value=os.environ.get("AF_VERSION", "v2.1.2")
                    ),
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="DOWNLOAD_IMAGE_TAG", value="latest"
                    ),
                    codebuild.CfnProject.EnvironmentVariableProperty(
                        name="DOWNLOAD_IMAGE_REPO_NAME",
                        value=self.download_container.repository_name,
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
            name=codebuild_project_name,
            resource_access_role=codebuild_role.role_arn,
            service_role=codebuild_role.role_arn,
            source=codebuild.CfnProject.SourceProperty(
                type="CODECOMMIT",
                build_spec="infrastructure/buildspec.yaml",
                git_clone_depth=1,
                location=self.repo.attr_clone_url_http,
            ),
            source_version="refs/heads/main",
        )
        
        codepipeline_role = iam.Role(
            self,
            "CodePipelineRole",
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
            inline_policies=[
                iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "codecommit:CancelUploadArchive",
                                "codecommit:GetBranch",
                                "codecommit:GetCommit",
                                "codecommit:GetRepository",
                                "codecommit:GetUploadArchiveStatus",
                                "codecommit:UploadArchive",
                            ],
                            resources=["*"],
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:PutObject",
                                "s3:GetObject",
                                "s3:GetObjectVersion",
                            ],
                            resources=[f"arn:aws:s3:::{bucket.bucket_name}/*"],
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetBucketAcl",
                                "s3:GetBucketLocation",
                            ],
                            resources=[bucket.bucket_arn],
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "codebuild:BatchGetBuilds",
                                "codebuild:StartBuild",
                                "codebuild:BatchGetBuildBatches",
                                "codebuild:StartBuildBatch",
                            ],
                            resources=[codebuild_project.attr_arn],
                        ),
                    ],
                )
            ]
        )

        source_configuration = {
            "RepositoryName": self.repo.repository_name,
            "BranchName": "main",
            "PollForSourceChanges": "false",
        }
        build_configuration = {"ProjectName": codebuild_project.name}
        
        self.pipeline = codepipeline.CfnPipeline(
            self,
            "CodePipeline",
            artifact_store=codepipeline.CfnPipeline.ArtifactStoreProperty(
                location=bucket.bucket_name, type="S3"
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
                                version="1",
                            ),
                            configuration=source_configuration,
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
                                version="1",
                            ),
                            configuration=build_configuration,
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