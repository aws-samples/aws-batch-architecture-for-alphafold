from constructs import Construct
from aws_cdk import Aws, Stack, CfnParameter, RemovalPolicy
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
    aws_sagemaker as sagemaker
)


class LokaFoldVPC(Stack):
    def __init__(self, scope: Construct, id: str, vpc_id: str, az: str, default_vpc_sg: str, public_subnet_0: str,
                 private_subnet_0: str, public_route_table: str, private_route_table: str, internet_gateway: str,
                 launch_sagemaker: str, fsx_capacity: str, fsx_throughput: str, alphafold_version, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # KMS



        # Network Configuration
        #vpc = ec2.Vpc(self, "VPC", cidr="10.0.0.0/16", max_azs=1)
        print(vpc_id)
        #vpc = ec2.Vpc.from_lookup(self, 'Alphafold2VPC', vpc_id=vpc_id)
        vpc =ec2.Vpc.from_vpc_attributes(
            self,
            "Alphafold2VPC",
            vpc_id=vpc_id,
            availability_zones=[az],
            public_subnet_ids=[public_subnet_0],
            private_subnet_ids=[private_subnet_0],
            public_subnet_route_table_ids=[public_route_table],
            private_subnet_route_table_ids=[private_route_table]
        )
        # vpc_flow_role = iam.Role(
        #     self,
        #     "VPCFlowLogRole",
        #     assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        # )

        # vpc_flow_role.attach_inline_policy(
        #     iam.Policy(
        #         self,
        #         "vpc_flow_policy",
        #         statements=[
        #             iam.PolicyStatement(
        #                 actions=[
        #                     "logs:CreateLogGroup",
        #                     "logs:CreateLogStream",
        #                     "logs:PutLogEvents",
        #                     "logs:DescribeLogGroups",
        #                     "logs:DescribeLogStreams",
        #                 ],
        #                 resources=[
        #                     f"arn:{Aws.PARTITION}:ec2:{Aws.REGION}:{Aws.ACCOUNT_ID}:vpc-flow-log/*"
        #                 ],
        #             )
        #         ],
        #     )
        # )

        # vpc_flow_logs_group = logs.CfnLogGroup(
        #     self,
        #     "VPCFlowLogsGroup",
        #     kms_key_id=key.key_arn,
        #     retention_in_days=120,
        # )

        # vpc_flow_log = ec2.CfnFlowLog(
        #     self,
        #     "VPCFlowLog",
        #     deliver_logs_permission_arn=vpc_flow_role.role_arn,
        #     log_group_name=vpc_flow_logs_group.log_group_name,
        #     resource_id=vpc.vpc_id,
        #     resource_type="VPC",
        #     traffic_type="ALL",
        # )

        # public_subnet = ec2.CfnSubnet(
        #     self,
        #     "PublicSubnet0",
        #     vpc_id=vpc.vpc_id,
        #     availability_zone=az.to_string(),
        #     cidr_block=vpc.vpc_cidr_block,
        # )

        print(vpc.public_subnets, vpc.private_subnets)
        public_subnet = vpc.public_subnets[0]


        # private_subnet = ec2.CfnSubnet(
        #     self,
        #     "PrivateSubnet0",
        #     vpc_id=vpc.vpc_id,
        #     availability_zone=az.to_string(),
        #     map_public_ip_on_launch=False,
        #     cidr_block=vpc.vpc_cidr_block,
        # )
        private_subnet = vpc.private_subnets[0]

        # internet_gateway = ec2.CfnInternetGateway(self, "InternetGateway")

        # gateway_to_internet = ec2.CfnVPCGatewayAttachment(
        #     self,
        #     "GatewayToInternet",
        #     vpc_id=vpc.vpc_id,
        #     internet_gateway_id=internet_gateway.attr_internet_gateway_id,
        # )

        # public_route_table = ec2.CfnRouteTable(
        #     self, "PublicRouteTable", vpc_id=vpc.vpc_id
        # )

        # public_route = ec2.CfnRoute(
        #     self,
        #     "PublicRoute",
        #     route_table_id=public_route_table.attr_route_table_id,
        #     destination_cidr_block="0.0.0.0/0",
        #     gateway_id=internet_gateway.attr_internet_gateway_id,
        # )

        # public_subnet_route_association = ec2.CfnSubnetRouteTableAssociation(
        #     self,
        #     "PublicSubnetRouteTableAssociation0",
        #     subnet_id=public_subnet.subnet_id,
        #     route_table_id=public_route_table.attr_route_table_id,
        # )

        # elastic_ip = ec2.CfnEIP(
        #     self,
        #     "ElasticIP0",
        #     domain="vpc",
        # )

        # nat_gateway = ec2.CfnNatGateway(
        #     self,
        #     "NATGateway0",
        #     allocation_id=elastic_ip.attr_allocation_id,
        #     subnet_id=public_subnet.subnet_id,
        # )

        # private_route_table = ec2.CfnRouteTable(
        #     self,
        #     "PrivateRouteTable0",
        #     vpc_id=vpc.vpc_id,
        # )

        # private_route_to_internet = ec2.CfnRoute(
        #     self,
        #     "PrivateRouteToInternet0",
        #     route_table_id=private_route_table.attr_route_table_id,
        #     destination_cidr_block="0.0.0.0/0",
        #     nat_gateway_id=nat_gateway.allocation_id,
        # )

        # private_subnet_route_association = ec2.CfnSubnetRouteTableAssociation(
        #     self,
        #     "PrivateSubnetRouteTableAssociation0",
        #     subnet_id=private_subnet.subnet_id,
        #     route_table_id=private_route_table.attr_route_table_id,
        # )

        # S3


        endpoint = vpc.add_gateway_endpoint(
            "S3Endpoint", service=ec2.GatewayVpcEndpointAwsService.S3
        )

        # FSx

        # lustre = fsx.LustreFileSystem(
        #     self,
        #     "FSX",
        #     lustre_configuration=fsx.LustreConfiguration(
        #         deployment_type=fsx.LustreDeploymentType.PERSISTENT_2,
        #         per_unit_storage_throughput=125,  # fsx_throughput.value_as_number, WIP
        #     ),
        #     vpc_subnet=ec2.Subnet.from_subnet_id(self, "subnet", private_subnet_0),
        #     storage_capacity_gib=1200,  # fsx_capacity.value_as_number, WIP
        #     removal_policy=RemovalPolicy.DESTROY,
        #     vpc=vpc
        # )

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

        # user_data.add_commands(
        #     f'MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="==MYBOUNDARY=="\n\n--==MYBOUNDARY==\nContent-Type: text/cloud-config; charset="us-ascii"\n\nruncmd:\n- file_system_id_01={lustre.file_system_id}\n- region={Aws.REGION}\n- fsx_directory=/fsx\n- fsx_mount_name={lustre.mount_name}\n- amazon-linux-extras install -y lustre2.10\n'
        #     + "- mkdir -p ${fsx_directory}\n- mount -t lustre ${file_system_id_01}.fsx.${region}.amazonaws.com@tcp:/${fsx_mount_name} ${fsx_directory}\n\n--==MYBOUNDARY==--"
        # )

        launch_template = ec2.LaunchTemplate(
            self,
            "InstanceLaunchTemplate",
            launch_template_name="LokaFold-launch-template",
            user_data=user_data,
        )

        private_compute_environment = batch.CfnComputeEnvironment(
            self,
            "PrivateCPUComputeEnvironment",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                allocation_strategy="BEST_FIT_PROGRESSIVE",
                instance_role=instance_profile.attr_arn,
                instance_types=["m5", "r5", "c5"],
                launch_template=batch.CfnComputeEnvironment.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template.launch_template_id,
                    version=launch_template.latest_version_number
                ),
                maxv_cpus=256,
                minv_cpus=0,
                security_group_ids=[default_vpc_sg],
                subnets=[private_subnet_0],
                type="EC2",
            ),
            state="ENABLED",
            type="MANAGED",
        )

        # Batch Environment

        # private_compute_environment = batch.CFnComputeEnvironment(
        #     self, "PrivateCPUComputeEnvironment",
        #     compute_resources={
        #         "allocation_strategy": "BEST_FIT_PROGRESSIVE",
        #         "type": "EC2",
        #         "vpc": vpc,
        #         "minv_cpus": 0,
        #         "desiredv_cpus": 0,
        #         "maxv_cpus": 256,
        #         "instance_types": [ec2.InstanceType("m5"), ec2.InstanceType("r5"), ec2.InstanceType("c5")],
        #         "launch_template": {
        #             "launch_template_name": "LokaFold-launch-template",
        #             "version": launch_template.latest_version_number
        #         },
        #         "security_groups": [
        #             security_group,
        #         ]
        #     }
        # )



