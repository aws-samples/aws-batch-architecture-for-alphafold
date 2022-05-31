import os
import boto3
from dotenv import load_dotenv
load_dotenv()

session = boto3.session.Session(profile_name=os.environ.get("aws_named_profile"))
cloudformation = session.client("cloudformation")

def get_all_stacks_names():
    response = cloudformation.list_stacks(
        StackStatusFilter=[
            "CREATE_COMPLETE",
        ]
    )
    stacks_names = [stack["StackName"] for stack in response['StackSummaries']]
    if response.get("NextToken"):
        token = response["NextToken"]
        response = cloudformation.list_stacks(
            StackStatusFilter=[
                "CREATE_COMPLETE",
            ],
            NextToken=token,
        )
        stacks_names += [stack["StackName"] for stack in response['StackSummaries']]
    return stacks_names
