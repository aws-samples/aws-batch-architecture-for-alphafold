import os
from aws_cdk import core as cdk
from aws_cdk.core import (
    Construct,
    CfnParameter,
)
import aws_cdk.aws_iam as iam
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_batch as batch
import aws_cdk.aws_fsx as fsx

class BatchStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, vpc, folding_container, download_container, **kwargs) -> None:
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
            allowed_values=["v2.1.2", "v2.2.2"],
        )
        
        # Network
        public_subnet = vpc.public_subnets[0]
        private_subnet = vpc.private_subnets[0]
        
        
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
            self, "InstanceProfile", roles=[ec2_role.role_name], instance_profile_name="InstanceProfile"
        )
        
        lustre = fsx.CfnFileSystem(
            self,
            "FSX",
            file_system_type="LUSTRE",
            file_system_type_version="2.12",

            lustre_configuration=fsx.CfnFileSystem.LustreConfigurationProperty(
                data_compression_type="LZ4",
                deployment_type="PERSISTENT_2",
                per_unit_storage_throughput=125,  # fsx_throughput.value_as_number, WIP
            ),
            
            security_group_ids=[vpc.vpc_default_security_group],
            storage_capacity=1200,  # WIP
            storage_type="SSD",
            subnet_ids=[private_subnet.subnet_id],
        )
        
        # user_data = ec2.UserData.for_linux() # WIP
        
        # user_data.add_commands(
        #     f'MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="==MYBOUNDARY=="\n\n--==MYBOUNDARY==\nContent-Type: text/cloud-config; charset="us-ascii"\n\nruncmd:\n- file_system_id_01={lustre.file_system_id}\n- region={Aws.REGION}\n- fsx_directory=/fsx\n- fsx_mount_name={lustre.mount_name}\n- amazon-linux-extras install -y lustre2.10\n'
        #     + "- mkdir -p ${fsx_directory}\n- mount -t lustre ${file_system_id_01}.fsx.${region}.amazonaws.com@tcp:/${fsx_mount_name} ${fsx_directory}\n\n--==MYBOUNDARY==--"
        # )
        
        launch_template = ec2.CfnLaunchTemplate(
            self,
            "InstanceLaunchTemplate",
            launch_template_name="LokaFold-launch-template",
            launch_template_data=ec2.CfnLaunchTemplate.LaunchTemplateDataProperty(
                block_device_mappings=[
                    ec2.CfnLaunchTemplate.BlockDeviceMappingProperty(
                        device_name="/dev/xvda",
                        ebs=ec2.CfnLaunchTemplate.EbsProperty(
                            delete_on_termination=True,
                            encrypted=True,
                            volume_size=50,
                            volume_type="gp2",
                        ),
                    )
                ],
                iam_instance_profile=ec2.CfnLaunchTemplate.IamInstanceProfileProperty(
                    name=instance_profile.instance_profile_name
                ),
                # user_data=user_data.render(),
            ),
        )
        
        public_launch_template = ec2.CfnLaunchTemplate(
            self,
            "PublicInstanceLaunchTemplate",
            launch_template_name="LokaFold-public-launch-template",
            launch_template_data=ec2.CfnLaunchTemplate.LaunchTemplateDataProperty(
                block_device_mappings=[
                    ec2.CfnLaunchTemplate.BlockDeviceMappingProperty(
                        device_name="/dev/xvda",
                        ebs=ec2.CfnLaunchTemplate.EbsProperty(
                            delete_on_termination=True,
                            encrypted=True,
                            volume_size=50,
                            volume_type="gp2",
                        ),
                    )
                ],
                iam_instance_profile=ec2.CfnLaunchTemplate.IamInstanceProfileProperty(
                    name=instance_profile.instance_profile_name
                ),
                network_interfaces=[
                    ec2.CfnLaunchTemplate.NetworkInterfaceProperty(
                        associate_public_ip_address=True,
                        device_index=0,
                        groups=[vpc.vpc_default_security_group],
                        subnet_id=public_subnet.subnet_id,
                    )
                ],
                # user_data=user_data.render(),
            ),
        )
        
        # Batch Compute environments
        
        private_compute_environment = batch.CfnComputeEnvironment(
            self,
            "PrivateCPUComputeEnvironment",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                allocation_strategy="BEST_FIT_PROGRESSIVE",
                instance_role=instance_profile.attr_arn,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template.logical_id,
                    version=launch_template.attr_latest_version_number,
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[vpc.vpc_default_security_group],
                subnets=[private_subnet.subnet_id],
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
                instance_role=instance_profile.attr_arn,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=public_launch_template.logical_id,
                    version=public_launch_template.attr_latest_version_number,
                ),
                maxv_cpus=256,
                minv_cpus=0,
                subnets=[public_subnet.subnet_id],
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
                instance_role=instance_profile.attr_arn,
                instance_types=["g4dn"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template.logical_id,
                    version=launch_template.attr_latest_version_number,
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[vpc.vpc_default_security_group],
                subnets=[private_subnet.subnet_id],
                type="EC2",
            ),
            state="ENABLED",
            type="MANAGED",
        )
        
        # Batch Queues
        
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
        
        # Batch Job Definitions
        
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