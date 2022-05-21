import os
from aws_cdk import core as cdk
from aws_cdk.core import (
    Construct,
)
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_fsx as fsx
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_s3_deployment as s3_deploy

mount_path = "/fsx" # do not touch
region_name = cdk.Aws.REGION

class FileSystemStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, vpc: ec2.Vpc, sg: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        private_subnet = None

        try:
            private_subnet = vpc.private_subnets[0]
        except IndexError:
            raise Exception(f"Be sure that you have a Public Subnet and a Private subnet in the vpc with id {os.environ.get('vpc_id')}")

        sg = ec2.SecurityGroup.from_security_group_id(self, "SG", sg, mutable=True)

        self.lustre_file_system = fsx.CfnFileSystem(
            self,
            "FSX",
            file_system_type="LUSTRE",
            lustre_configuration=fsx.CfnFileSystem.LustreConfigurationProperty(
                data_compression_type="LZ4",
                deployment_type="PERSISTENT_2",
                per_unit_storage_throughput=int(os.environ.get("fsx_throughput", 500)),
            ),
            security_group_ids=[sg.security_group_id],
            storage_capacity=int(os.environ.get("fsx_capacity", 1200)),
            storage_type="SSD",
            subnet_ids=[private_subnet.subnet_id],
        )