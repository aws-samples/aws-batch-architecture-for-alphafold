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

@app.route("/", methods=["POST", "GET"])
def index():
    request = app.current_request
    body = request.json_body
    if request.method == 'GET':
        job_id = request.query_params["job_id"]
        # job_id_2 = request.query_params["prediction_job_id"]
        status = get_batch_job_info(job_id)
        # status_2 = get_batch_job_info(job_id_2)
        response = {
            "job": status,
        }
        return response
    elif request.method == 'POST':
        input_sequences = list(body["sequences"].values())
        input_ids = list(body["sequences"].keys())
        db_preset = body["db_preset"]
        # cpu = body["cpu"]
        # memory = body["memory"]
        # gpu = body["gpu"]
        # run_features_only = body["run_features_only"]
        
        # Validate input for invalid aminoacid residues
        input_sequences, model_preset = validate_input(input_sequences)
        sequence_length = len(max(input_sequences))
        
        if db_preset == "reduced_dbs":
            prep_cpu = 4
            prep_mem = 16
            prep_gpu = 0

        else:
            prep_cpu = 16
            prep_mem = 32
            prep_gpu = 0

        if sequence_length < 700:
            predict_cpu = 4
            predict_mem = 16
            predict_gpu = 1
        else:
            predict_cpu = 16
            predict_mem = 64
            predict_gpu = 1
        

        # Upload file to s3 bucket
        job_name = create_job_name()
        object_key = upload_fasta_to_s3(
            input_sequences,
            input_ids,
            S3_BUCKET,
            job_name
        )
        # Submit jobs to batch
        try:
            step_1_response = submit_batch_alphafold_job(
                job_name=str(job_name),
                fasta_paths=object_key,
                output_dir=job_name,
                db_preset=db_preset,
                model_preset=model_preset,
                s3_bucket=S3_BUCKET,
                cpu=prep_cpu,
                memory=prep_mem,
                gpu=prep_gpu,
                run_features_only=True,
            )
            
            step_2_response = submit_batch_alphafold_job(
                job_name=str(job_name),
                fasta_paths=object_key,
                output_dir=job_name,
                db_preset=db_preset,
                model_preset=model_preset,
                s3_bucket=S3_BUCKET,
                cpu=predict_cpu,
                memory=predict_mem,
                gpu=predict_gpu,
                features_paths=os.path.join(job_name, job_name, "features.pkl"),
                depends_on=step_1_response["jobId"],
            )
        except Exception as err:
            raise f"Error submiting the jobs {err}"
        
        response = {
            "feature_extraction_job_response": step_1_response,
            "prediction_job_response": step_2_response,
        }
        return response
