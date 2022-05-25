import os
from aws_cdk import core as cdk
from aws_cdk.core import (
    Construct,
)
import aws_cdk.aws_iam as iam
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_batch as batch
import aws_cdk.aws_ecr as ecr
import aws_cdk.aws_fsx as fsx

mount_path = "/fsx" # do not touch
region_name = cdk.Aws.REGION

class BatchStack(cdk.Stack):
    def __init__(
            self, 
            scope: Construct, 
            id: str, 
            vpc: ec2.Vpc, 
            sg: str, 
            folding_container: ecr.CfnRepository, 
            download_container: ecr.CfnRepository, 
            lustre_file_system: fsx.CfnFileSystem, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        public_subnet = None
        private_subnet = None

        try:
            public_subnet = vpc.public_subnets[0]
            private_subnet = vpc.private_subnets[0]
        except IndexError:
            raise Exception(f"Be sure that you have a Public Subnet and a Private subnet in the vpc with id {os.environ.get('vpc_id')}")

        sg = ec2.SecurityGroup.from_security_group_id(self, "SG", sg, mutable=True)
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
        
        mount_name = lustre_file_system.attr_lustre_mount_name
        file_system_id = lustre_file_system.ref
        
        user_data = ec2.MultipartUserData()
        user_data.add_part(
            ec2.MultipartBody.from_user_data(
                ec2.UserData.custom(
                    "amazon-linux-extras install -y lustre2.10\n"
                    f"mkdir -p {mount_path}\n"
                    f"mount -t lustre -o noatime,flock {file_system_id}.fsx.{region_name}.amazonaws.com@tcp:/{mount_name} {mount_path}\n"
                    f"echo '{file_system_id}.fsx.{region_name}.amazonaws.com@tcp:/{mount_name} {mount_path} lustre defaults,noatime,flock,_netdev 0 0' >> /etc/fstab \n"
                    "mkdir -p /tmp/alphafold"
                    )
                ),
            )
                
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
                user_data=cdk.Fn.base64(user_data.render()),
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
                        groups=[sg.security_group_id],
                        subnet_id=public_subnet.subnet_id,
                    )
                ],
                user_data=cdk.Fn.base64(user_data.render()),
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
                    launch_template_name=launch_template.launch_template_name,
                    version=launch_template.attr_latest_version_number,
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[sg.security_group_id],
                subnets=[private_subnet.subnet_id],
                type="EC2",
            ),
            state="ENABLED",
            type="MANAGED",
        )
        private_compute_environment.add_depends_on(launch_template)
        
        private_spot_compute_environment = batch.CfnComputeEnvironment(
            self,
            "PrivateSpotCPUComputeEnvironment",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                allocation_strategy="SPOT_CAPACITY_OPTIMIZED",
                instance_role=instance_profile.attr_arn,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_name=launch_template.launch_template_name,
                    version=launch_template.attr_latest_version_number,
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[sg.security_group_id],
                subnets=[private_subnet.subnet_id],
                type="SPOT",
            ),
            state="ENABLED",
            type="MANAGED",
        )
        private_spot_compute_environment.add_depends_on(launch_template)
        
        public_compute_environment = batch.CfnComputeEnvironment(
            self,
            "PublicCPUComputeEnvironment",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                allocation_strategy="BEST_FIT_PROGRESSIVE",
                instance_role=instance_profile.attr_arn,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_name=public_launch_template.launch_template_name,
                    version=public_launch_template.attr_latest_version_number,
                ),
                maxv_cpus=256,
                minv_cpus=0,
                # security_group_ids=[sg.security_group_id],
                subnets=[public_subnet.subnet_id],
                type="EC2",
            ),
            state="ENABLED",
            type="MANAGED",
        )
        public_compute_environment.add_depends_on(public_launch_template)
        
        public_spot_compute_environment = batch.CfnComputeEnvironment(
            self,
            "PublicSpotCPUComputeEnvironment",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                allocation_strategy="SPOT_CAPACITY_OPTIMIZED",
                instance_role=instance_profile.attr_arn,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_name=public_launch_template.launch_template_name,
                    version=public_launch_template.attr_latest_version_number,
                ),
                maxv_cpus=256,
                minv_cpus=0,
                # security_group_ids=[sg.security_group_id],
                subnets=[public_subnet.subnet_id],
                type="SPOT",
            ),
            state="ENABLED",
            type="MANAGED",
        )
        public_spot_compute_environment.add_depends_on(public_launch_template)
        
        gpu_compute_environment = batch.CfnComputeEnvironment(
            self,
            "PrivateGPUComputeEnvironment",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                allocation_strategy="BEST_FIT_PROGRESSIVE",
                instance_role=instance_profile.attr_arn,
                instance_types=["g5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_name=launch_template.launch_template_name,
                    version=launch_template.attr_latest_version_number,
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[sg.security_group_id],
                subnets=[private_subnet.subnet_id],
                type="EC2",
            ),
            state="ENABLED",
            type="MANAGED",
        )
        gpu_compute_environment.add_depends_on(launch_template)
        
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
        
        private_spot_cpu_queue = batch.CfnJobQueue(
            self,
            "PrivateSpotCPUJobQueue",
            compute_environment_order=[
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=private_spot_compute_environment.attr_compute_environment_arn,
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
            state="ENABLED",
        )

        public_spot_cpu_queue = batch.CfnJobQueue(
            self,
            "PublicSpotCPUJobQueue",
            compute_environment_order=[
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=public_spot_compute_environment.attr_compute_environment_arn,
                    order=1,
                ),
            ],
            priority=10,
            state="ENABLED",
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
                        name="pdb_seqres",
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
            "GPUFoldingJobDefinition",
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
                        name="pdb_seqres",
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
