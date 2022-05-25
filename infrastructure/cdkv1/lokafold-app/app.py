import os
import sys
import logging
import boto3
from chalice import Chalice, Response
from chalice import BadRequestError
from chalicelib import (
    validate_input,
    create_job_name,
    upload_fasta_to_s3,
    submit_batch_alphafold_job,
    get_batch_job_info,
    submit_downloading_job
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

@app.route("/compute", methods=["POST", "GET"])
def compute():
    request = app.current_request
    body = request.json_body
    # TODO: add schema validation using api gateway cababilities
    if request.method == 'GET':
        job_id = request.query_params.get("job_id")
        try:
            body = get_batch_job_info(job_id)
        except Exception as e:
            raise BadRequestError(e)
        return Response(
            body=body,
            status_code=200
        )
    elif request.method == 'POST':
        input_sequences = list(body["sequences"].values())
        input_ids = list(body["sequences"].keys())
        db_preset = body["db_preset"]
        use_spot_instances = body["use_spot_instances"]
        
        # Validate input for invalid aminoacid residues
        try:
            input_sequences, model_preset = validate_input(input_sequences)
        except Exception as e:
            raise BadRequestError(e)
        
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
        try:
            job_name = create_job_name()
            object_key = upload_fasta_to_s3(
                input_sequences,
                input_ids,
                S3_BUCKET,
                job_name
            )
        except Exception as e:
            raise BadRequestError(e)

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
                use_spot_instances=use_spot_instances
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
        except Exception as e:
            raise BadRequestError(e)
        
        body = {
            "feature_extraction_job_response": step_1_response,
            "prediction_job_response": step_2_response,
        }
        return Response(
            body=body,
            status_code=200
        )
    else:
        return Response(
            body={
                "message": "Method is not implemented. Use either GET or POST"
            },
            status_code=405
        )

@app.route("/download", methods=["POST"])
def download():
    request = app.current_request
    body = request.json_body
    # TODO: add schema validation using api gateway cababilities
    if request.method == "POST":
        db_preset = body.get("db_preset", "reduced_dbs") # reduced_dbs
        use_spot_instances = body.get("use_spot_instances", True)
        
        try:
            job_name = create_job_name()
            response = submit_downloading_job(
                job_name=job_name,
                download_mode=db_preset,
                use_spot_instances=use_spot_instances
            )
        except Exception as e:
            raise BadRequestError(e)
        return Response(
            body=response,
            status_code=200,
        )
    else:
        return Response(
            body={
                "message": "Method is not implemented. Use POST"
            },
            status_code=405
        )

@app.route("/cancel", methods=["POST"])
def cancel():
    request = app.current_request
    body = request.json_body
    # TODO: add schema validation using api gateway cababilities
    if request.method == "POST":
        job_id = body.get("job_id")
        try:
            response = batch.describe_jobs(
                jobs=[job_id]
            )
        except Exception as e:
            raise BadRequestError(e)
        
        # Check if job exists
        if len(response["jobs"]) > 0:            
            if response["jobs"][0]["status"] in ["STARTING", "RUNNABLE", "RUNNING"]:
                response = batch.terminate_job(
                    jobId=job_id,
                    reason="Job cancelled via API."
                )
                status_code = response["ResponseMetadata"].get("HTTPStatusCode")
                if status_code == 200:
                    body = {
                        "status_code": status_code,
                        "message": f"Job {job_id} cancelled successfully."
                    }
                else:
                    body = {
                        "status_code": status_code,
                        "message": f"Job {job_id} couldn't be cancelled. Try again."
                    }
            else:
                body = {
                    "status_code": 200,
                    "message": f"Job id {job_id} is not STARTING, ready to run (RUNNABLE) or RUNNING and cannot be cancelled."
                }
        else:
            body = {
                "status_code": 200,
                "message": f"Job id {job_id} doesn't exist."
            }
        return Response(
            body=body,
            status_code=body["status_code"],
        )
    else:
        return Response(
            body={
                "message": "Method is not implemented. Use either POST"
            },
            status_code=405
        )