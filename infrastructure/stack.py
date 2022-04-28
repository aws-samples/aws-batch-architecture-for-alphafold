from constructs import Construct
from aws_cdk import Aws, Stack, CfnParameter
from aws_cdk import (
    aws_logs as logs,
    aws_s3 as s3,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_fsx as fsx,
    aws_codecommit as codecommit,
    aws_ecr as ecr,
    aws_kms as kms,
    aws_codebuild as codebuild,
    aws_codepipeline as codepipeline,
    aws_batch as batch,
    aws_sagemaker as sagemaker,
)


class LokaFoldBasic(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Parameters
        az = CfnParameter(
            self,
            "StackAvailabilityZone",
            description="Availability zone to deploy stack resources",
        )

        launch_sagemaker = CfnParameter(
            self,
            "LaunchSageMakerNotebook",
            description="Create a SageMaker Notebook Instance",
            default="Y",
            allowed_values=["Y", "N"],
        )

        fsx_capacity = CfnParameter(
            self,
            "FSXForLustreStorageCapacity",
            description="Storage capacity in GB, 1200 or increments of 2400",
            default="1200",
            allowed_values=["1200", "2400", "4800", "7200"],
            type="Number",
        )

        fsx_throughput = CfnParameter(
            self,
            "FSxForLustreThroughput",
            description="Throughput for unit storage (MB/s/TB) to provision for FSx for Lustre file system",
            default="500",
            allowed_values=["125", "250", "500", "1000"],
            type="Number",
        )

        alphafold_version = CfnParameter(
            self,
            "AlphaFoldVersion",
            description="AlphaFold release to include as part of the job container",
            default="v2.1.2",
            allowed_values=["v2.1.2"],
        )

        # KMS

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
                principals=[iam.AnyPrincipal()],
            ),
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
                principals=[iam.AnyPrincipal()],
            ),
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
                principals=[iam.AnyPrincipal()],
            ),
        )

        # Network Configuration
        vpc = ec2.Vpc(self, "VPC", cidr="10.0.0.0/16")

        vpc_flow_role = iam.Role(
            self,
            "VPCFlowLogRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )

        vpc_flow_role.attach_inline_policy(
            iam.Policy(
                self,
                "vpc_flow_policy",
                statements=[
                    iam.PolicyStatement(
                        actions=[
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents",
                            "logs:DescribeLogGroups",
                            "logs:DescribeLogStreams",
                        ],
                        resources=[
                            f"arn:{Aws.PARTITION}:ec2:{Aws.REGION}:{Aws.ACCOUNT_ID}:vpc-flow-log/*"
                        ],
                    )
                ],
            )
        )

        vpc_flow_logs_group = logs.CfnLogGroup(
            self,
            "VPCFlowLogsGroup",
            kms_key_id=key.key_arn,
            retention_in_days=120,
        )

        vpc_flow_log = ec2.CfnFlowLog(
            self,
            "VPCFlowLog",
            deliver_logs_permission_arn=vpc_flow_role.role_arn,
            log_group_name=vpc_flow_logs_group.log_group_name,
            resource_id=vpc.vpc_id,
            resource_type="VPC",
            traffic_type="ALL",
        )

        public_subnet = ec2.CfnSubnet(
            self,
            "PublicSubnet0",
            vpc_id=vpc.vpc_id,
            availability_zone=az.to_string(),
            cidr_block=vpc.vpc_cidr_block,
        )

        private_subnet = ec2.CfnSubnet(
            self,
            "PrivateSubnet0",
            vpc_id=vpc.vpc_id,
            availability_zone=az.to_string(),
            map_public_ip_on_launch=False,
            cidr_block=vpc.vpc_cidr_block,
        )

        internet_gateway = ec2.CfnInternetGateway(self, "InternetGateway")

        gateway_to_internet = ec2.CfnVPCGatewayAttachment(
            self,
            "GatewayToInternet",
            vpc_id=vpc.vpc_id,
            internet_gateway_id=internet_gateway.attr_internet_gateway_id,
        )

        public_route_table = ec2.CfnRouteTable(
            self, "PublicRouteTable", vpc_id=vpc.vpc_id
        )

        public_route = ec2.CfnRoute(
            self,
            "PublicRoute",
            route_table_id=public_route_table.attr_route_table_id,
            destination_cidr_block="0.0.0.0/0",
            gateway_id=internet_gateway.attr_internet_gateway_id,
        )

        public_subnet_route_association = ec2.CfnSubnetRouteTableAssociation(
            self,
            "PublicSubnetRouteTableAssociation0",
            subnet_id=public_subnet.attr_subnet_id,
            route_table_id=public_route_table.attr_route_table_id,
        )

        elastic_ip = ec2.CfnEIP(
            self,
            "ElasticIP0",
            domain="vpc",
        )

        nat_gateway = ec2.CfnNatGateway(
            self,
            "NATGateway0",
            allocation_id=elastic_ip.attr_allocation_id,
            subnet_id=public_subnet.attr_subnet_id,
        )

        private_route_table = ec2.CfnRouteTable(
            self,
            "PrivateRouteTable0",
            vpc_id=vpc.vpc_id,
        )

        private_route_to_internet = ec2.CfnRoute(
            self,
            "PrivateRouteToInternet0",
            route_table_id=private_route_table.attr_route_table_id,
            destination_cidr_block="0.0.0.0/0",
            nat_gateway_id=nat_gateway.allocation_id,
        )

        private_subnet_route_association = ec2.CfnSubnetRouteTableAssociation(
            self,
            "PrivateSubnetRouteTableAssociation0",
            subnet_id=private_subnet.attr_subnet_id,
            route_table_id=private_route_table.attr_route_table_id,
        )

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

        endpoint = vpc.add_gateway_endpoint(
            "S3Endpoint", service=ec2.GatewayVpcEndpointAwsService.S3
        )

        # FSx

        lustre = fsx.LustreFileSystem(
            self,
            "FSX",
            lustre_configuration=fsx.LustreConfiguration(
                deployment_type=fsx.LustreDeploymentType.PERSISTENT_2,
                per_unit_storage_throughput=125,  # fsx_throughput.value_as_number, WIP
            ),
            vpc_subnet=private_subnet,
            storage_capacity_gib=1200,  # fsx_capacity.value_as_number, WIP
            vpc=vpc,
        )

        # EC2 Launch Template

        ec2_role = iam.Role(
            self,
            "EC2InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )

        ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_arn(
                self,
                "ecr_policy",
                "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
            )
        )
        ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_arn(
                self,
                "ecr_service",
                "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role",
            )
        )
        ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_managed_policy_arn(
                self, "s3_access_policy", "arn:aws:iam::aws:policy/AmazonS3FullAccess"
            )
        )

        instance_profile = iam.CfnInstanceProfile(
            self, "InstanceProfile", roles=[ec2_role.role_name]
        )

        user_data = ec2.UserData.for_linux()

        user_data.add_commands(
            f'MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="==MYBOUNDARY=="\n\n--==MYBOUNDARY==\nContent-Type: text/cloud-config; charset="us-ascii"\n\nruncmd:\n- file_system_id_01={lustre.file_system_id}\n- region={Aws.REGION}\n- fsx_directory=/fsx\n- fsx_mount_name={lustre.mount_name}\n- amazon-linux-extras install -y lustre2.10\n'
            + "- mkdir -p ${fsx_directory}\n- mount -t lustre ${file_system_id_01}.fsx.${region}.amazonaws.com@tcp:/${fsx_mount_name} ${fsx_directory}\n\n--==MYBOUNDARY==--"
        )

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

        repo = codecommit.CfnRepository(
            self,
            "CodeRepository",
            repository_name="LokaFold-code-repo",
            code=codecommit.CfnRepository.CodeProperty(
                branch_name="main",
                s3=codecommit.CfnRepository.S3Property(
                    bucket="aws-hcls-ml",
                    key="blog_post_support_materials/aws-alphafold/main/aws-alphafold.zip",
                ),
            ),
        )

        folding_container = ecr.CfnRepository(
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

        download_container = ecr.CfnRepository(
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

        codebuild_role = iam.Role(
            self, "CodeBuildRole", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com")
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
                            f"arn:aws:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/codebuild/AWS-Alphafold*"
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
                            f"arn:aws:codecommit:{Aws.REGION}:{Aws.ACCOUNT_ID}:{repo.repository_name}"
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
            artifacts=codebuild.CfnProject.ArtifactsProperty(type="NO-ARTIFACTS"),
            encryption_key=key.key_id,
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
                location=repo.attr_clone_url_http,
            ),
            source_version="refs/heads/main",
        )

        codepipeline_role = iam.Role(
            self,
            "CodePipelineRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )

        codepipeline_role.attach_inline_policy(
            iam.Policy(
                self,
                "codepipeline_role",
                statements=[
                    iam.PolicyStatement(
                        actions=[
                            "codecommit:CancelUploadArchive",
                            "codecommit:GetBranch",
                            "codecommit:GetCommit",
                            "codecommit:GetRepository",
                            "codecommit:GetUploadArchiveStatus",
                            "codecommit:UploadArchive",
                        ],
                        resources=[repo.attr_arn],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "s3:PutObject",
                            "s3:GetObject",
                            "s3:GetObjectVersion",
                        ],
                        resources=[f"arn:aws:s3:::{bucket.bucket_name}/*"],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "s3:GetBucketAcl",
                            "s3:GetBucketLocation",
                        ],
                        resources=[bucket.bucket_arn],
                    ),
                    iam.PolicyStatement(
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
        )

        configuration = {
            "Configuration": [
                {"RepositoryName": repo.repository_name},
                {"BranchName": "main"},
                {"PollForSourceChanges": "false"},
                # {"ActionMode": "CREATE_UPDATE"}, WIP
            ]
        }

        pipeline = codepipeline.CfnPipeline(
            self,
            "CodePipeline",
            artifact_store=codepipeline.CfnPipeline.ArtifactStoreProperty(
                location=bucket.bucket_arn, type="S3"
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
                                version="1",
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
                instance_role=ec2_role.role_arn,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template.launch_template_id,
                    version="$Latest",
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[vpc.vpc_default_security_group],
                subnets=[private_subnet.attr_subnet_id],
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
                instance_role=ec2_role.role_arn,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template.launch_template_id,
                    version="$Latest",
                ),
                maxv_cpus=256,
                minv_cpus=0,
                subnets=[private_subnet.attr_subnet_id],
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
                instance_role=ec2_role.role_arn,
                instance_types=["g4dn"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template.launch_template_id,
                    version="$Latest",
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[vpc.vpc_default_security_group],
                subnets=[private_subnet.attr_subnet_id],
                type="EC2",
            ),
            state="ENABLED",
            type="MANAGED",
        )

        private_cpu_queue = batch.CfnJobQueue(
            self,
            "PrivateCPUJobQueue",
            compute_environment_order=[
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=private_compute_environment.attr_compute_environment_arn,
                    order=1,
                ),
            ],
            priority=10,
            state="ENABLED",
        )

        public_cpu_queue = batch.CfnJobQueue(
            self,
            "PublicCPUJobQueue",
            compute_environment_order=[
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=public_compute_environment.attr_compute_environment_arn,
                    order=1,
                ),
            ],
            priority=10,
            state="Enabled",
        )

        gpu_job_queue = batch.CfnJobQueue(
            self,
            "PrivateGPUJobQueue",
            compute_environment_order=[
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=gpu_compute_environment.attr_compute_environment_arn,
                    order=1,
                ),
            ],
            priority=10,
            state="ENABLED",
        )

        cpu_folding_job = batch.CfnJobDefinition(
            self,
            "CPUFoldingJobDefinition",
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                command=["-c echo hello, world"],
                image=folding_container.attr_repository_uri,
                log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                    log_driver="awslogs"
                ),
                mount_points=[
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/bfd_database_path",
                        read_only=True,
                        source_volume="bfd",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/mgnify_database_path",
                        read_only=True,
                        source_volume="mgnify",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/pdb70_database_path",
                        read_only=True,
                        source_volume="pdb70",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/template_mmcif_database_path",
                        read_only=True,
                        source_volume="pdb_mmcif",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/obsolete_pdbs_database_path",
                        read_only=True,
                        source_volume="pdb_mmcif",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/pdb_seqres_database_path",
                        read_only=True,
                        source_volume="pdb_seqres",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/small_bfd_database_path",
                        read_only=True,
                        source_volume="small_bfd",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/uniclust30_database_path",
                        read_only=True,
                        source_volume="uniclust30",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/uniprot_database_path",
                        read_only=True,
                        source_volume="uniprot",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/uniref90_database_path",
                        read_only=True,
                        source_volume="uniref90",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/data_dir",
                        read_only=True,
                        source_volume="data",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/output",
                        read_only=True,
                        source_volume="output",
                    ),
                ],
                resource_requirements=[
                    batch.CfnJobDefinition.ResourceRequirementProperty(
                        type="VCPU", value="8"
                    ),
                    batch.CfnJobDefinition.ResourceRequirementProperty(
                        type="MEMORY", value="16000"
                    ),
                ],
                volumes=[
                    batch.CfnJobDefinition.VolumesProperty(
                        name="bfd",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/bfd"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="mgnify",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/mgnify"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="pdb70",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/pdb70"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="pdb_mmcif",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/pdb_mmcif"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="pdb_sqres",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/pdb_seqres"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="small_bfd",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/small_bfd"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="uniclust30",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/uniclust30"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="uniprot",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/uniprot"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="uniref90",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/uniref90"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="data",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="output",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/tmp/alphafold"
                        ),
                    ),
                ],
            ),
            platform_capabilities=["EC2"],
            propagate_tags=True,
            retry_strategy=batch.CfnJobDefinition.RetryStrategyProperty(attempts=3),
            type="container",
        )

        gpu_folding_job = batch.CfnJobDefinition(
            self,
            "GPUFoldingJob",
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                command=["nvidia-smi"],
                environment=[
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="TF_FORCE_UNIFIED_MEMORY", value="1"
                    ),
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="XLA_PYTHON_CLIENT_MEM_FRACTION", value="4.0"
                    ),
                ],
                image=folding_container.attr_repository_uri,
                log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                    log_driver="awslogs"
                ),
                mount_points=[
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/bfd_database_path",
                        read_only=True,
                        source_volume="bfd",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/mgnify_database_path",
                        read_only=True,
                        source_volume="mgnify",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/pdb70_database_path",
                        read_only=True,
                        source_volume="pdb70",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/template_mmcif_database_path",
                        read_only=True,
                        source_volume="pdb_mmcif",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/obsolete_pdbs_database_path",
                        read_only=True,
                        source_volume="pdb_mmcif",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/pdb_seqres_database_path",
                        read_only=True,
                        source_volume="pdb_seqres",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/small_bfd_database_path",
                        read_only=True,
                        source_volume="small_bfd",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/uniclust30_database_path",
                        read_only=True,
                        source_volume="uniclust30",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/uniprot_database_path",
                        read_only=True,
                        source_volume="uniprot",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/uniref90_database_path",
                        read_only=True,
                        source_volume="uniref90",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/data_dir",
                        read_only=True,
                        source_volume="data",
                    ),
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/mnt/output",
                        read_only=True,
                        source_volume="output",
                    ),
                ],
                resource_requirements=[
                    batch.CfnJobDefinition.ResourceRequirementProperty(
                        type="VCPU", value="8"
                    ),
                    batch.CfnJobDefinition.ResourceRequirementProperty(
                        type="MEMORY", value="16000"
                    ),
                    batch.CfnJobDefinition.ResourceRequirementProperty(
                        type="GPU", value="1"
                    ),
                ],
                volumes=[
                    batch.CfnJobDefinition.VolumesProperty(
                        name="bfd",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/bfd"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="mgnify",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/mgnify"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="pdb70",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/pdb70"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="pdb_mmcif",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/pdb_mmcif"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="pdb_sqres",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/pdb_seqres"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="small_bfd",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/small_bfd"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="uniclust30",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/uniclust30"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="uniprot",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/uniprot"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="uniref90",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx/uniref90"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="data",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/"
                        ),
                    ),
                    batch.CfnJobDefinition.VolumesProperty(
                        name="output",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/tmp/alphafold"
                        ),
                    ),
                ],
            ),
            platform_capabilities=["EC2"],
            propagate_tags=True,
            retry_strategy=batch.CfnJobDefinition.RetryStrategyProperty(attempts=3),
            type="container",
        )

        download_job = batch.CfnJobDefinition(
            self,
            "CPUDownloadJobDefinition",
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                command=["-c echo hello, world"],
                image=download_container.attr_repository_uri,
                log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                    log_driver="awslogs"
                ),
                mount_points=[
                    batch.CfnJobDefinition.MountPointsProperty(
                        container_path="/fsx", read_only=False, source_volume="fsx"
                    )
                ],
                privileged=False,
                resource_requirements=[
                    batch.CfnJobDefinition.ResourceRequirementProperty(
                        type="VCPU", value="4"
                    ),
                    batch.CfnJobDefinition.ResourceRequirementProperty(
                        type="MEMORY", value="16000"
                    ),
                ],
                volumes=[
                    batch.CfnJobDefinition.VolumesProperty(
                        name="fsx",
                        host=batch.CfnJobDefinition.VolumesHostProperty(
                            source_path="/fsx"
                        ),
                    )
                ],
            ),
            platform_capabilities=["EC2"],
            propagate_tags=True,
            retry_strategy=batch.CfnJobDefinition.RetryStrategyProperty(attempts=3),
            type="container",
        )

        # SageMaker

        notebook_role = iam.Role(
            self,
            "SageMakerNotebookExecutionRole",
            path="/",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
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
            "AlphafoldNotebookInstance",
            direct_internet_access="Enabled",
            instance_type="ml.c4.2xlarge",
            default_code_repository=repo.attr_clone_url_http,
            kms_key_id=key.key_arn,
            role_arn=notebook_role.role_arn,
            subnet_id=private_subnet.attr_subnet_id,
            security_group_ids=[vpc.vpc_default_security_group],
        )
