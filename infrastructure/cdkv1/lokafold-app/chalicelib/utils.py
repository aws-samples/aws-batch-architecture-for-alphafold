# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Helper functions for the AWS-Alphafold API
"""
import logging
import sys
from datetime import datetime
import os
import uuid
import re
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

import boto3

boto_session = boto3.session.Session()
region = boto_session.region_name
s3 = boto_session.client("s3", region_name=region)
batch = boto_session.client("batch", region_name=region)
cfn = boto_session.client("cloudformation", region_name=region)
logs_client = boto_session.client("logs")

logging.basicConfig(
    format="%(asctime)s %(levelname)-s:%(name)s: %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

def upload_fasta_to_s3(
    sequences,
    ids,
    bucket,
    job_name=uuid.uuid4(),
):

    """
    Create a fasta file and upload it to S3.
    """

    file_out = "/tmp/_tmp.fasta"
    with open(file_out, "a") as f_out:
        for i, seq in enumerate(sequences):
            seq_record = SeqRecord(Seq(seq), id=ids[i])
            SeqIO.write(seq_record, f_out, "fasta")

    object_key = f"{job_name}/{job_name}.fasta"
    response = s3.upload_file(file_out, bucket, object_key)
    os.remove(file_out)
    s3_uri = f"s3://{bucket}/{object_key}"
    logger.info(f"Sequence file uploaded to {s3_uri}")
    return object_key

def create_job_name(suffix=None):

    """
    Define a simple job identifier
    """

    if suffix == None:
        return datetime.now().strftime("%Y%m%dT%H%M%S")
    else:
        ## Ensure that the suffix conforms to the Batch requirements, (only letters,
        ## numbers, hyphens, and underscores are allowed).
        suffix = re.sub("\W", "_", suffix)
        return datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + suffix

def validate_input(input_sequences):
    output = []
    for sequence in input_sequences:
        sequence = sequence.upper().strip()
        if re.search("[^ARNDCQEGHILKMFPSTWYV]", sequence):
            raise ValueError(
                f"Input sequence contains invalid amino acid symbols." f"{sequence}"
            )
        output.append(sequence)

    if len(output) == 1:
        logger.info("Using the monomer models.")
        model_preset = "monomer"
        return output, model_preset
    elif len(output) > 1:
        logger.info("Using the multimer models.")
        model_preset = "multimer"
        return output, model_preset
    else:
        raise ValueError("Please provide at least one input sequence.")

def get_batch_resources(stack_name):
    """
    Get the resource names of the Batch resources for running Alphafold jobs.
    """

    # stack_name = af_stacks[0]["StackName"]
    stack_resources = cfn.list_stack_resources(StackName=stack_name)
    for resource in stack_resources["StackResourceSummaries"]:
        if resource["LogicalResourceId"] == "GPUFoldingJobDefinition":
            gpu_job_definition = resource["PhysicalResourceId"]
        if resource["LogicalResourceId"] == "PrivateGPUJobQueue":
            gpu_job_queue = resource["PhysicalResourceId"]
        if resource["LogicalResourceId"] == "CPUFoldingJobDefinition":
            cpu_job_definition = resource["PhysicalResourceId"]
        if resource["LogicalResourceId"] == "PrivateCPUJobQueue":
            cpu_job_queue = resource["PhysicalResourceId"]
        if resource["LogicalResourceId"] == "PrivateSpotCPUJobQueue":
            cpu_spot_job_queue = resource["PhysicalResourceId"]
        if resource["LogicalResourceId"] == "CPUDownloadJobDefinition":
            download_job_definition = resource["PhysicalResourceId"]
        if resource["LogicalResourceId"] == "PublicCPUJobQueue":
            download_job_queue = resource["PhysicalResourceId"]
        if resource["LogicalResourceId"] == "PublicSpotCPUJobQueue":
            download_spot_job_queue = resource["PhysicalResourceId"]
    return {
        "gpu_job_definition": gpu_job_definition,
        "gpu_job_queue": gpu_job_queue,
        "cpu_job_definition": cpu_job_definition,
        "cpu_job_queue": cpu_job_queue,
        "download_job_definition": download_job_definition,
        "download_job_queue": download_job_queue,
        "cpu_spot_job_queue": cpu_spot_job_queue,
        "download_spot_job_queue": download_spot_job_queue,
    }

def list_alphafold_stacks():
    af_stacks = []
    for stack in cfn.list_stacks(
        StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE"]
    )["StackSummaries"]:
        if stack["StackName"] == "LokaFoldBatchStack":
            af_stacks.append(stack)
    return af_stacks

def get_batch_logs(logStreamName):
    """
    Retrieve and format logs for batch job.
    """
    try:
        response = logs_client.get_log_events(
            logGroupName="/aws/batch/job", 
            logStreamName=logStreamName,
            startFromHead=False,
            limit=20,
        )
    except logs_client.meta.client.exceptions.ResourceNotFoundException:
        return f"Log stream {logStreamName} does not exist. Please try again in a few minutes"

    messages = ''
    for event in (response)['events']:
        messages = messages+'\n'+(str(event['message']))
    return messages

def get_batch_job_info(jobId):

    """
    Retrieve and format information about a batch job.
    """

    job_description = batch.describe_jobs(jobs=[jobId])
        
    if len(job_description) == 0:
        raise "There is no jobs with that id. Please specify a valid job id."
    
    output = {
        "jobArn": job_description["jobs"][0]["jobArn"],
        "jobName": job_description["jobs"][0]["jobName"],
        "jobId": job_description["jobs"][0]["jobId"],
        "status": job_description["jobs"][0]["status"],
        "createdAt": datetime.utcfromtimestamp(
            job_description["jobs"][0]["createdAt"] / 1000
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dependsOn": job_description["jobs"][0]["dependsOn"],
        "tags": job_description["jobs"][0]["tags"],
    }

    if output["status"] == "SUCCEEDED":
        output["logStreamName"] = job_description["jobs"][0]["container"][
            "logStreamName"
        ]
        logs = get_batch_logs(output["logStreamName"])
        output["logs"] = logs
        output["statusReason"] = job_description['jobs'][0]['statusReason']
    elif output["status"] == "FAILED":
        try:
            output["logStreamName"] = job_description["jobs"][0]["container"][
                "logStreamName"
            ]
            logs = get_batch_logs(output["logStreamName"])
            output["logs"] = logs
        except Exception as e:
            logger.info("This failed job does not have logs yet.")
            return output
    else: # status = SUBMITTED/PENDING/RUNNABLE/STARTING/RUNNING
        output["logStreamName"] = job_description["jobs"][0]["container"][
            "logStreamName"
        ]
        logs = get_batch_logs(output["logStreamName"])
        output["logs"] = logs  
    
    return output

def submit_batch_alphafold_job(
    job_name,
    fasta_paths,
    s3_bucket,
    data_dir="/mnt/data_dir/fsx",
    output_dir="alphafold",
    bfd_database_path="/mnt/bfd_database_path/bfd_metaclust_clu_complete_id30_c90_final_seq.sorted_opt",
    mgnify_database_path="/mnt/mgnify_database_path/mgy_clusters_2018_12.fa",
    pdb70_database_path="/mnt/pdb70_database_path/pdb70",
    obsolete_pdbs_path="/mnt/obsolete_pdbs_database_path/obsolete.dat",
    template_mmcif_dir="/mnt/template_mmcif_database_path/mmcif_files",
    pdb_seqres_database_path="/mnt/pdb_seqres_database_path/pdb_seqres.txt",
    small_bfd_database_path="/mnt/small_bfd_database_path/bfd-first_non_consensus_sequences.fasta",
    uniclust30_database_path="/mnt/uniclust30_database_path/uniclust30_2018_08/uniclust30_2018_08",
    uniprot_database_path="/mnt/uniprot_database_path/uniprot.fasta",
    uniref90_database_path="/mnt/uniref90_database_path/uniref90.fasta",
    max_template_date=datetime.now().strftime("%Y-%m-%d"),
    db_preset="reduced_dbs",
    model_preset="monomer",
    benchmark=False,
    use_precomputed_msas=False,
    features_paths=None,
    run_features_only=False,
    logtostderr=True,
    cpu=4,
    memory=16,
    gpu=1,
    depends_on=None,
    stack_name=None,
    use_spot_instances=False,
):

    if stack_name is None:
        stack_name = list_alphafold_stacks()[0]["StackName"]
    batch_resources = get_batch_resources(stack_name)

    # Enable this option to be able to load the MSA results if instance
    # gets interrupted.
    if use_spot_instances:
        use_precomputed_msas = True

    container_overrides = {
        "command": [
            f"--fasta_paths={fasta_paths}",
            f"--uniref90_database_path={uniref90_database_path}",
            f"--mgnify_database_path={mgnify_database_path}",
            f"--data_dir={data_dir}",
            f"--template_mmcif_dir={template_mmcif_dir}",
            f"--obsolete_pdbs_path={obsolete_pdbs_path}",
            f"--output_dir={output_dir}",
            f"--max_template_date={max_template_date}",
            f"--db_preset={db_preset}",
            f"--model_preset={model_preset}",
            f"--s3_bucket={s3_bucket}",
        ],
        "resourceRequirements": [
            {"value": str(cpu), "type": "VCPU"},
            {"value": str(memory * 1000), "type": "MEMORY"},
        ],
    }

    if model_preset == "multimer":
        container_overrides["command"].append(
            f"--uniprot_database_path={uniprot_database_path}"
        )
        container_overrides["command"].append(
            f"--pdb_seqres_database_path={pdb_seqres_database_path}"
        )
    else:
        container_overrides["command"].append(
            f"--pdb70_database_path={pdb70_database_path}"
        )

    if db_preset == "reduced_dbs":
        container_overrides["command"].append(
            f"--small_bfd_database_path={small_bfd_database_path}"
        )
    else:
        container_overrides["command"].append(
            f"--uniclust30_database_path={uniclust30_database_path}"
        )
        container_overrides["command"].append(
            f"--bfd_database_path={bfd_database_path}"
        )

    if benchmark:
        container_overrides["command"].append("--benchmark")

    if use_precomputed_msas:
        container_overrides["command"].append("--use_precomputed_msas")

    if features_paths is not None:
        container_overrides["command"].append(f"--features_paths={features_paths}")

    if run_features_only:
        container_overrides["command"].append("--run_features_only")

    if logtostderr:
        container_overrides["command"].append("--logtostderr")

    if gpu > 0:
        job_definition = batch_resources["gpu_job_definition"]
        job_queue = batch_resources["gpu_job_queue"]
        container_overrides["resourceRequirements"].append(
            {"value": str(gpu), "type": "GPU"}
        )
    elif use_spot_instances and gpu == 0:
        job_definition = batch_resources["cpu_job_definition"]
        job_queue = batch_resources["cpu_spot_job_queue"]
    else:
        job_definition = batch_resources["cpu_job_definition"]
        job_queue = batch_resources["cpu_job_queue"]

    if depends_on is None:
        response = batch.submit_job(
            jobDefinition=job_definition,
            jobName=job_name,
            jobQueue=job_queue,
            containerOverrides=container_overrides,
        )
    else:
        response = batch.submit_job(
            jobDefinition=job_definition,
            jobName=job_name,
            jobQueue=job_queue,
            containerOverrides=container_overrides,
            dependsOn=[{"jobId": depends_on, "type": "SEQUENTIAL"}],
        )

    return response

