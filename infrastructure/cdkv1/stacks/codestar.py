import os
from aws_cdk import core as cdk
from aws_cdk.core import (
    Construct
)
import aws_cdk.aws_codestarconnections as codestarconnections

class CodeStarStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        self.github_connection = codestarconnections.CfnConnection(
            self, 
            "LokaFoldCodeStarGithubConnection",
            connection_name="github-connection",
            provider_type="GitHub"
        )
