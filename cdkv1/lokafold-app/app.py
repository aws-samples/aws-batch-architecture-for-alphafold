import os
import sys
import logging
import boto3
from chalice import Chalice
from chalicelib import (
    validate_input,
    create_job_name,
    upload_fasta_to_s3,
    submit_batch_alphafold_job,
    get_batch_job_info
)
app = Chalice(app_name="lokafold-app")

boto_session = boto3.session.Session()
region = boto_session.region_name
batch = boto_session.client("batch", region_name=region)

S3_BUCKET = os.environ["FASTA_BUCKET"]

logging.basicConfig(
    format="%(asctime)s %(levelname)-s:%(name)s: %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

'''
{
    "job_name": "",
    "fasta_paths": "s3_key",
    "output_dir": "job_name",
    "db_preset": "DB_PRESET",
    "model_preset": "model_preset",
    "cpu": "prep_cpu",
    "memory": "prep_mem",
    "gpu": "prep_gpu",
    "run_features_only": true
}
'''

@app.route("/", methods=["POST", "GET"])
def index():
    request = app.current_request
    body = request.json_body
    if request.method == 'GET':
        # status_1 = get_batch_job_info(step_1_response["jobId"])
        logger.info(body)
        return {"Hello": "Warudo"}
    elif request.method == 'POST':
        input_sequences = list(body["sequences"].values())
        input_ids = list(body["sequences"].keys())
        db_preset = body["db_preset"]
        cpu = body["cpu"]
        memory = body["memory"]
        gpu = body["gpu"]
        run_features_only = body["run_features_only"]
        
        # Validate input for invalid aminoacid residues
        input_sequences, model_preset = validate_input(input_sequences)
        sequence_length = len(max(input_sequences))
        # Upload file to s3 bucket
        job_name = create_job_name()
        object_key = upload_fasta_to_s3(
            input_sequences,
            input_ids,
            S3_BUCKET,
            job_name,
            region=region
        )
        
        # step_1_response = submit_batch_alphafold_job(
        #     job_name=str(job_name),
        #     fasta_paths=object_key,
        #     output_dir=job_name,
        #     db_preset=db_preset,
        #     model_preset=model_preset,
        #     s3_bucket=S3_BUCKET,
        #     cpu=cpu,
        #     memory=memory,
        #     gpu=gpu,
        #     run_features_only=run_features_only,
        # )
        
        # step_2_response = submit_batch_alphafold_job(
        #     job_name=str(job_name),
        #     fasta_paths=object_key,
        #     output_dir=job_name,
        #     db_preset=db_preset,
        #     model_preset=model_preset,
        #     s3_bucket=S3_BUCKET,
        #     cpu=cpu,
        #     memory=memory,
        #     gpu=gpu,
        #     features_paths=os.path.join(job_name, job_name, "features.pkl"),
        #     depends_on=step_1_response["jobId"],
        # )
        
        response = {
            "feature_extraction_job_id": "jobid1",#step_1_response["jobId"],
            "prediction_job_id": "jobid2"#step_2_response["jobId"],
        }
        return response
