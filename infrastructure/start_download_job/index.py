import boto3
import cfnresponse
import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

boto_session = boto3.session.Session()
region = boto_session.region_name
batch = boto_session.client("batch", region_name=region)

def lambda_handler(event, context):
    try:
        LOGGER.info("REQUEST RECEIVED:\n %s", event)
        LOGGER.info("REQUEST RECEIVED:\n %s", context)
        if event["RequestType"] == "Create":
            LOGGER.info("CREATE!")
            all_scripts = [
                "download_alphafold_params_s3.sh",
                "download_bfd_s3.sh",
                "download_mgnify_s3.sh",
                "download_pdb70_s3.sh",
                "download_pdb_mmcif_s3.sh",
                "download_pdb_seqres_s3.sh",
                "download_small_bfd_s3.sh",
                "download_uniclust30_s3.sh",
                "download_uniprot.sh",
                "download_uniref90.sh",
            ]
            responses = []
            for script in all_scripts:
                LOGGER.info(script)
                script_response = submit_download_data_job(
                    job_queue=event["ResourceProperties"]["JobQueue"],
                    job_definition=event["ResourceProperties"]["JobDefinition"],
                    job_name="download_job",
                    script=script,
                    cpu=4,
                    memory=16,
                    download_dir="/fsx",
                )
                responses.append(script_response)
            response = str(responses)
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, {"response": "Resource creation successful!"}
            )

        elif event["RequestType"] == "Update":
            LOGGER.info("UPDATE!")
            cfnresponse.send(
                event,
                context,
                cfnresponse.SUCCESS,
                {"response": "Resource update successful!"},
            )

        elif event["RequestType"] == "Delete":
            LOGGER.info("DELETE!")
            cfnresponse.send(
                event,
                context,
                cfnresponse.SUCCESS,
                {"response": "Resource deletion successful!"},
            )

        else:
            LOGGER.info("FAILED!")
            cfnresponse.send(
                event,
                context,
                cfnresponse.FAILED,
                {"response": "Unexpected event received from CloudFormation"},
            )

    except:
        LOGGER.info("FAILED!")
        cfnresponse.send(
            event,
            context,
            cfnresponse.FAILED,
            {"response": "Exception during processing"},
        )


def submit_download_data_job(
    job_definition,
    job_queue,
    job_name="download_job",
    script="all",
    cpu=4,
    memory=16,
    download_dir="/fsx",
):

    container_overrides = {
        "command": [script, download_dir],
        "resourceRequirements": [
            {"value": str(cpu), "type": "VCPU"},
            {"value": str(memory * 1000), "type": "MEMORY"},
        ],
    }

    LOGGER.info(f"Job definition is {job_definition}")
    LOGGER.info(f"Job name is {job_name}")
    LOGGER.info(f"Job queue is {job_queue}")
    LOGGER.info(f"Container overrides are {container_overrides}")
    response = batch.submit_job(
        jobDefinition=job_definition,
        jobName=job_name,
        jobQueue=job_queue,
        containerOverrides=container_overrides,
    )
    LOGGER.info(f"Response is {response}")
    return response