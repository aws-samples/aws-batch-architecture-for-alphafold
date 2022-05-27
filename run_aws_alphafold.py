# Original Copyright 2021 DeepMind Technologies Limited
# Modifications Copyright 2022 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Full AlphaFold protein structure prediction script."""
import json
import os
import pathlib
import pickle
import random
import shutil
import sys
import time
from typing import Dict, Union, Optional

from absl import app
from absl import flags
from absl import logging
from alphafold.common import protein
from alphafold.common import residue_constants
from alphafold.data import pipeline
from alphafold.data import pipeline_multimer
from alphafold.data import templates
from alphafold.data.tools import hhsearch
from alphafold.data.tools import hmmsearch
from alphafold.model import config
from alphafold.model import data
from alphafold.model import model
from alphafold.relax import relax
import numpy as np

### ---------------------------------------------
### Modified by Amazon Web Services (AWS) to add urlparse and boto3
from urllib.parse import urlparse
import boto3
s3 = boto3.client("s3")
### ---------------------------------------------
logging.set_verbosity(logging.INFO)

flags.DEFINE_list(
    'fasta_paths', None, 'Paths to FASTA files, each containing a prediction '
    'target that will be folded one after another. If a FASTA file contains '
    'multiple sequences, then it will be folded as a multimer. Paths should be '
    'separated by commas. All FASTA paths must have a unique basename as the '
    'basename is used to name the output directories for each prediction.')
flags.DEFINE_list(
    'is_prokaryote_list', None, 'Optional for multimer system, not used by the '
    'single chain system. This list should contain a boolean for each fasta '
    'specifying true where the target complex is from a prokaryote, and false '
    'where it is not, or where the origin is unknown. These values determine '
    'the pairing method for the MSA.')

flags.DEFINE_string('data_dir', None, 'Path to directory of supporting data.')
flags.DEFINE_string('output_dir', None, 'Path to a directory that will '
                    'store the results.')
flags.DEFINE_string('jackhmmer_binary_path', shutil.which('jackhmmer'),
                    'Path to the JackHMMER executable.')
flags.DEFINE_string('hhblits_binary_path', shutil.which('hhblits'),
                    'Path to the HHblits executable.')
flags.DEFINE_string('hhsearch_binary_path', shutil.which('hhsearch'),
                    'Path to the HHsearch executable.')
flags.DEFINE_string('hmmsearch_binary_path', shutil.which('hmmsearch'),
                    'Path to the hmmsearch executable.')
flags.DEFINE_string('hmmbuild_binary_path', shutil.which('hmmbuild'),
                    'Path to the hmmbuild executable.')
flags.DEFINE_string('kalign_binary_path', shutil.which('kalign'),
                    'Path to the Kalign executable.')
flags.DEFINE_string('uniref90_database_path', None, 'Path to the Uniref90 '
                    'database for use by JackHMMER.')
flags.DEFINE_string('mgnify_database_path', None, 'Path to the MGnify '
                    'database for use by JackHMMER.')
flags.DEFINE_string('bfd_database_path', None, 'Path to the BFD '
                    'database for use by HHblits.')
flags.DEFINE_string('small_bfd_database_path', None, 'Path to the small '
                    'version of BFD used with the "reduced_dbs" preset.')
flags.DEFINE_string('uniclust30_database_path', None, 'Path to the Uniclust30 '
                    'database for use by HHblits.')
flags.DEFINE_string('uniprot_database_path', None, 'Path to the Uniprot '
                    'database for use by JackHMMer.')
flags.DEFINE_string('pdb70_database_path', None, 'Path to the PDB70 '
                    'database for use by HHsearch.')
flags.DEFINE_string('pdb_seqres_database_path', None, 'Path to the PDB '
                    'seqres database for use by hmmsearch.')
flags.DEFINE_string('template_mmcif_dir', None, 'Path to a directory with '
                    'template mmCIF structures, each named <pdb_id>.cif')
flags.DEFINE_string('max_template_date', None, 'Maximum template release date '
                    'to consider. Important if folding historical test sets.')
flags.DEFINE_string('obsolete_pdbs_path', None, 'Path to file containing a '
                    'mapping from obsolete PDB IDs to the PDB IDs of their '
                    'replacements.')
flags.DEFINE_enum('db_preset', 'full_dbs',
                  ['full_dbs', 'reduced_dbs'],
                  'Choose preset MSA database configuration - '
                  'smaller genetic database config (reduced_dbs) or '
                  'full genetic database config  (full_dbs)')
flags.DEFINE_enum('model_preset', 'monomer',
                  ['monomer', 'monomer_casp14', 'monomer_ptm', 'multimer'],
                  'Choose preset model configuration - the monomer model, '
                  'the monomer model with extra ensembling, monomer model with '
                  'pTM head, or multimer model')
flags.DEFINE_boolean('benchmark', False, 'Run multiple JAX model evaluations '
                     'to obtain a timing that excludes the compilation time, '
                     'which should be more indicative of the time required for '
                     'inferencing many proteins.')
flags.DEFINE_integer('random_seed', None, 'The random seed for the data '
                     'pipeline. By default, this is randomly generated. Note '
                     'that even if this is set, Alphafold may still not be '
                     'deterministic, because processes like GPU inference are '
                     'nondeterministic.')
flags.DEFINE_boolean('use_precomputed_msas', False, 'Whether to read MSAs that '
                     'have been written to disk instead of running the MSA '
                     'tools. The MSA files are looked up in the output '
                     'directory, so it must stay the same between multiple '
                     'runs that are to reuse the MSAs. WARNING: This will not '
                     'check if the sequence, database or configuration have '
                     'changed.')
flags.DEFINE_boolean('run_relax', True, 'Whether to run the final relaxation '
                     'step on the predicted models. Turning relax off might '
                     'result in predictions with distracting stereochemical '
                     'violations but might help in case you are having issues '
                     'with the relaxation stage.')
flags.DEFINE_boolean('use_gpu_relax', None, 'Whether to relax on GPU. '
                     'Relax on GPU can be much faster than CPU, so it is '
                     'recommended to enable if possible. GPUs must be available'
                     ' if this setting is enabled.')

### ---------------------------------------------
### Modified by AWS to add urlparse and boto3

flags.DEFINE_string(
    "s3_bucket",
    None,
    "Name of S3 bucket (without the s3://) used to store the fasta files and "
    " (optionally) features.pkl files, i.e. the shared s3 url for each member "
    " of FLAGS.fasta_paths.",
)
flags.DEFINE_list(
    "features_paths",
    None,
    "Optional paths to features.pkl files generated in "
    "previous runs. Note that if features_paths is not None, it must be the "
    "same length as fasta_paths.",
)
flags.DEFINE_boolean(
    "run_features_only",
    False,
    "Should the job stop after generating features?",
)
### ---------------------------------------------

FLAGS = flags.FLAGS

MAX_TEMPLATE_HITS = 20
RELAX_MAX_ITERATIONS = 0
RELAX_ENERGY_TOLERANCE = 2.39
RELAX_STIFFNESS = 10.0
RELAX_EXCLUDE_RESIDUES = []
RELAX_MAX_OUTER_ITERATIONS = 3


def _check_flag(flag_name: str,
                other_flag_name: str,
                should_be_set: bool):
  if should_be_set != bool(FLAGS[flag_name].value):
    verb = 'be' if should_be_set else 'not be'
    raise ValueError(f'{flag_name} must {verb} set when running with '
                     f'"--{other_flag_name}={FLAGS[other_flag_name].value}".')


def predict_structure(
    fasta_path: str,
    fasta_name: str,
    output_dir_base: str,
    data_pipeline: Union[pipeline.DataPipeline, pipeline_multimer.DataPipeline],
    model_runners: Dict[str, model.RunModel],
    amber_relaxer: relax.AmberRelaxation,
    benchmark: bool,
    random_seed: int,
    is_prokaryote: Optional[bool] = None,
### ---------------------------------------------
### Modified by AWS to add support for 2-step jobs

    features_path: Optional[str] = None,
    run_features_only: Optional[bool] = False,
### ---------------------------------------------
):
    """Predicts structure using AlphaFold for the given sequence."""
    logging.info('Predicting %s', fasta_name)
    timings = {}
    output_dir = os.path.join(output_dir_base, fasta_name)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    msa_output_dir = os.path.join(output_dir, 'msas')
    if not os.path.exists(msa_output_dir):
        os.makedirs(msa_output_dir)

    # Get features.
    t_0 = time.time()
### ---------------------------------------------    
### Modified by AWS to add support for 2-step jobs

    # If we already have feature.pkl file, skip the MSA and template finding step
    if features_path is not None:
        logging.info(f"{features_path} found. Loading...")
        feature_dict = pickle.load(open(features_path, "rb"))
    else:
### ---------------------------------------------        
        if is_prokaryote is None:
            feature_dict = data_pipeline.process(
            input_fasta_path=fasta_path,
            msa_output_dir=msa_output_dir)
        else:
            feature_dict = data_pipeline.process(
                input_fasta_path=fasta_path,
                msa_output_dir=msa_output_dir,
                is_prokaryote=is_prokaryote)
        timings['features'] = time.time() - t_0

        # Write out features as a pickled dictionary.
        features_output_path = os.path.join(output_dir, 'features.pkl')
        with open(features_output_path, 'wb') as f:
            pickle.dump(feature_dict, f, protocol=4)

### ---------------------------------------------
### Modified by AWS to add support for 2-step jobs.
### See https://github.com/Zuricho/ParallelFold)

    if run_features_only:
        logging.info(
            f"Ending early since run_features_only set to {run_features_only}."
        )
        logging.info(f"Final timings for {fasta_name}: {timings}")
        timings_output_path = os.path.join(output_dir, "timings.json")
        with open(timings_output_path, "w") as f:
            f.write(json.dumps(timings, indent=4))
        return
### ---------------------------------------------

    unrelaxed_pdbs = {}
    relaxed_pdbs = {}
    ranking_confidences = {}

    # Run the models.
    num_models = len(model_runners)
    for model_index, (model_name, model_runner) in enumerate(
        model_runners.items()):
        logging.info('Running model %s on %s', model_name, fasta_name)
        t_0 = time.time()
        model_random_seed = model_index + random_seed * num_models
        processed_feature_dict = model_runner.process_features(
            feature_dict, random_seed=model_random_seed)
        timings[f'process_features_{model_name}'] = time.time() - t_0

        t_0 = time.time()
        prediction_result = model_runner.predict(processed_feature_dict,
                                                 random_seed=model_random_seed)
        t_diff = time.time() - t_0
        timings[f'predict_and_compile_{model_name}'] = t_diff
        logging.info(
            'Total JAX model %s on %s predict time (includes compilation time, see --benchmark): %.1fs',
            model_name, fasta_name, t_diff)

        if benchmark:
            t_0 = time.time()
            model_runner.predict(processed_feature_dict, 
                                 random_seed=model_random_seed)
            t_diff = time.time() - t_0
            timings[f'predict_benchmark_{model_name}'] = t_diff
            logging.info(
                'Total JAX model %s on %s predict time (excludes compilation time): %.1fs',
                model_name, fasta_name, t_diff)

        plddt = prediction_result['plddt']
        ranking_confidences[model_name] = prediction_result['ranking_confidence']

        # Save the model outputs.
        result_output_path = os.path.join(output_dir, f'result_{model_name}.pkl')
        with open(result_output_path, 'wb') as f:
            pickle.dump(prediction_result, f, protocol=4)

        # Add the predicted LDDT in the b-factor column.
        # Note that higher predicted LDDT value means higher model confidence.
        plddt_b_factors = np.repeat(
            plddt[:, None], residue_constants.atom_type_num, axis=-1)
        unrelaxed_protein = protein.from_prediction(
            features=processed_feature_dict,
            result=prediction_result,
            b_factors=plddt_b_factors,
            remove_leading_feature_dimension=not model_runner.multimer_mode)

        unrelaxed_pdbs[model_name] = protein.to_pdb(unrelaxed_protein)
        unrelaxed_pdb_path = os.path.join(output_dir, f'unrelaxed_{model_name}.pdb')
        with open(unrelaxed_pdb_path, 'w') as f:
            f.write(unrelaxed_pdbs[model_name])

        if amber_relaxer:
            # Relax the prediction.
            t_0 = time.time()
            relaxed_pdb_str, _, _ = amber_relaxer.process(prot=unrelaxed_protein)
            timings[f'relax_{model_name}'] = time.time() - t_0

            relaxed_pdbs[model_name] = relaxed_pdb_str

            # Save the relaxed PDB.
            relaxed_output_path = os.path.join(
                output_dir, f'relaxed_{model_name}.pdb')
            with open(relaxed_output_path, 'w') as f:
                f.write(relaxed_pdb_str)

    # Rank by model confidence and write out relaxed PDBs in rank order.
    ranked_order = []
    for idx, (model_name, _) in enumerate(
        sorted(ranking_confidences.items(), key=lambda x: x[1], reverse=True)):
        ranked_order.append(model_name)
        ranked_output_path = os.path.join(output_dir, f'ranked_{idx}.pdb')
        with open(ranked_output_path, 'w') as f:
            if amber_relaxer:
                f.write(relaxed_pdbs[model_name])
            else:
                f.write(unrelaxed_pdbs[model_name])

    ranking_output_path = os.path.join(output_dir, 'ranking_debug.json')
    with open(ranking_output_path, 'w') as f:
        label = 'iptm+ptm' if 'iptm' in prediction_result else 'plddts'
        f.write(json.dumps(
                {label: ranking_confidences, 'order': ranked_order}, indent=4))

    logging.info('Final timings for %s: %s', fasta_name, timings)

    timings_output_path = os.path.join(output_dir, 'timings.json')

    ### ---------------------------------------------    
    ### Modified to add support for 2-step jobs
    ### Add back the features timing from the step 1 if timings.json presents
    ### https://github.com/aws-samples/aws-batch-architecture-for-alphafold/pull/3/files
    if os.path.exists(timings_output_path):
        with open(timings_output_path, 'r') as f:
            features_timing = json.load(f)
        timings['features'] = features_timing['features']
    ### --------------------------------------------- 

    with open(timings_output_path, 'w') as f:
        f.write(json.dumps(timings, indent=4))


def main(argv):
    if len(argv) > 1:
        raise app.UsageError('Too many command-line arguments.')

    for tool_name in (
      'jackhmmer', 'hhblits', 'hhsearch', 'hmmsearch', 'hmmbuild', 'kalign'):
        if not FLAGS[f'{tool_name}_binary_path'].value:
            raise ValueError(f'Could not find path to the "{tool_name}" binary. Make '
                            'sure it is installed on your system.')

    use_small_bfd = FLAGS.db_preset == 'reduced_dbs'
    _check_flag('small_bfd_database_path', 'db_preset',
                should_be_set=use_small_bfd)
    _check_flag('bfd_database_path', 'db_preset',
                should_be_set=not use_small_bfd)
    _check_flag('uniclust30_database_path', 'db_preset',
                should_be_set=not use_small_bfd)

    run_multimer_system = 'multimer' in FLAGS.model_preset
    _check_flag('pdb70_database_path', 'model_preset',
                should_be_set=not run_multimer_system)
    _check_flag('pdb_seqres_database_path', 'model_preset',
                should_be_set=run_multimer_system)
    _check_flag('uniprot_database_path', 'model_preset',
                should_be_set=run_multimer_system)

    if FLAGS.model_preset == 'monomer_casp14':
        num_ensemble = 8
    else:
        num_ensemble = 1

    # Check for duplicate FASTA file names.
    fasta_names = [pathlib.Path(p).stem for p in FLAGS.fasta_paths]
    if len(fasta_names) != len(set(fasta_names)):
        raise ValueError('All FASTA paths must have a unique basename.')

    # Check that is_prokaryote_list has same number of elements as fasta_paths,
    # and convert to bool.
    if FLAGS.is_prokaryote_list:
        if len(FLAGS.is_prokaryote_list) != len(FLAGS.fasta_paths):
            raise ValueError('--is_prokaryote_list must either be omitted or match '
                'length of --fasta_paths.')
        is_prokaryote_list = []
        for s in FLAGS.is_prokaryote_list:
            if s in ('true', 'false'):
                is_prokaryote_list.append(s == 'true')
            else:
                raise ValueError('--is_prokaryote_list must contain comma separated '
                    'true or false values.')
    else:  # Default is_prokaryote to False.
        is_prokaryote_list = [False] * len(fasta_names)
### ---------------------------------------------
### Modified by AWS to add support for 2-step jobs.

    # Check that features_paths has the same number of elements as fasta_paths,
    # (if it is not None)
    if FLAGS.features_paths is not None:
        if len(FLAGS.features_paths) != len(FLAGS.fasta_paths):
            raise ValueError(
                "--features_paths must either be omitted or match "
                "length of --fasta_paths."
            )
### ---------------------------------------------

    if run_multimer_system:
        template_searcher = hmmsearch.Hmmsearch(
            binary_path=FLAGS.hmmsearch_binary_path,
            hmmbuild_binary_path=FLAGS.hmmbuild_binary_path,
            database_path=FLAGS.pdb_seqres_database_path)
        template_featurizer = templates.HmmsearchHitFeaturizer(
            mmcif_dir=FLAGS.template_mmcif_dir,
            max_template_date=FLAGS.max_template_date,
            max_hits=MAX_TEMPLATE_HITS,
            kalign_binary_path=FLAGS.kalign_binary_path,
            release_dates_path=None,
            obsolete_pdbs_path=FLAGS.obsolete_pdbs_path)
    else:
        template_searcher = hhsearch.HHSearch(
            binary_path=FLAGS.hhsearch_binary_path,
            databases=[FLAGS.pdb70_database_path])
        template_featurizer = templates.HhsearchHitFeaturizer(
            mmcif_dir=FLAGS.template_mmcif_dir,
            max_template_date=FLAGS.max_template_date,
            max_hits=MAX_TEMPLATE_HITS,
            kalign_binary_path=FLAGS.kalign_binary_path,
            release_dates_path=None,
            obsolete_pdbs_path=FLAGS.obsolete_pdbs_path)

    monomer_data_pipeline = pipeline.DataPipeline(
        jackhmmer_binary_path=FLAGS.jackhmmer_binary_path,
        hhblits_binary_path=FLAGS.hhblits_binary_path,
        uniref90_database_path=FLAGS.uniref90_database_path,
        mgnify_database_path=FLAGS.mgnify_database_path,
        bfd_database_path=FLAGS.bfd_database_path,
        uniclust30_database_path=FLAGS.uniclust30_database_path,
        small_bfd_database_path=FLAGS.small_bfd_database_path,
        template_searcher=template_searcher,
        template_featurizer=template_featurizer,
        use_small_bfd=use_small_bfd,
        use_precomputed_msas=FLAGS.use_precomputed_msas)

    if run_multimer_system:
        data_pipeline = pipeline_multimer.DataPipeline(
            monomer_data_pipeline=monomer_data_pipeline,
            jackhmmer_binary_path=FLAGS.jackhmmer_binary_path,
            uniprot_database_path=FLAGS.uniprot_database_path,
            use_precomputed_msas=FLAGS.use_precomputed_msas)
    else:
        data_pipeline = monomer_data_pipeline

    model_runners = {}
    model_names = config.MODEL_PRESETS[FLAGS.model_preset]
    for model_name in model_names:
        model_config = config.model_config(model_name)
        if run_multimer_system:
            model_config.model.num_ensemble_eval = num_ensemble
        else:
            model_config.data.eval.num_ensemble = num_ensemble
        model_params = data.get_model_haiku_params(
            model_name=model_name, data_dir=FLAGS.data_dir)
        model_runner = model.RunModel(model_config, model_params)
        model_runners[model_name] = model_runner

    logging.info('Have %d models: %s', len(model_runners),
                list(model_runners.keys()))

    if FLAGS.run_relax:
        amber_relaxer = relax.AmberRelaxation(
            max_iterations=RELAX_MAX_ITERATIONS,
            tolerance=RELAX_ENERGY_TOLERANCE,
            stiffness=RELAX_STIFFNESS,
            exclude_residues=RELAX_EXCLUDE_RESIDUES,
            max_outer_iterations=RELAX_MAX_OUTER_ITERATIONS,
            use_gpu=FLAGS.use_gpu_relax)
    else:
        amber_relaxer = None

    random_seed = FLAGS.random_seed
    if random_seed is None:
        random_seed = random.randrange(sys.maxsize // len(model_names))
    logging.info('Using random seed %d for the data pipeline', random_seed)

    # Predict structure for each of the sequences.
    for i, fasta_path in enumerate(FLAGS.fasta_paths):
        is_prokaryote = is_prokaryote_list[i] if run_multimer_system else None
        fasta_name = fasta_names[i]
### ---------------------------------------------
### Modified by AWS to add support for 2-step jobs and data storage in S3.

        # --------- Download files from S3 ---------------------------
        if FLAGS.s3_bucket is not None:
            s3_fasta_url = os.path.join(FLAGS.s3_bucket, fasta_path)
            logging.info(
                f"Downloading {fasta_path} from s3://{s3_fasta_url} to {fasta_path}"
            )
            try:
                if not os.path.exists(os.path.dirname(fasta_path)):
                    logging.info(f"Creating directory {os.path.dirname(fasta_path)}")
                    os.makedirs(os.path.dirname(fasta_path))
                s3.download_file(FLAGS.s3_bucket, fasta_path, fasta_path)
            except BaseException as err:
                logging.info(
                    f"Unable to download {fasta_path} from s3://{s3_fasta_url} to {fasta_path}"
                )
                print(err)
                continue

        if FLAGS.features_paths is not None:
            features_path = FLAGS.features_paths[i]
            s3_features_url = os.path.join(FLAGS.s3_bucket, features_path)
            logging.info(
                f"Downloading {features_path} from s3://{s3_features_url} to {features_path}"
            )
            try:
                if not os.path.exists(os.path.dirname(features_path)):
                    logging.info(f"Creating directory {os.path.dirname(features_path)}")
                    os.makedirs(os.path.dirname(features_path))
                s3.download_file(FLAGS.s3_bucket, features_path, features_path)

                ### 5/27/2022: Also download timings.json
                output_dir = os.path.join(FLAGS.output_dir, fasta_name)
                timings_output_path = os.path.join(output_dir, "timings.json")
                s3.download_file(FLAGS.s3_bucket, timings_output_path, timings_output_path)
                ########################################

            except BaseException as err:
                logging.info(
                    f"Unable to download {features_path} from s3://{s3_features_url} to {features_path}"
                )
                print(err)
                continue
        else:
            features_path = None
### ---------------------------------------------

        predict_structure(
            fasta_path=fasta_path,
            fasta_name=fasta_name,
            output_dir_base=FLAGS.output_dir,
            data_pipeline=data_pipeline,
            model_runners=model_runners,
            amber_relaxer=amber_relaxer,
            benchmark=FLAGS.benchmark,
            random_seed=random_seed,
            is_prokaryote=is_prokaryote,
### ---------------------------------------------            
### Modified by AWS to add support for 2-step jobs.
           
            features_path=features_path,
            run_features_only=FLAGS.run_features_only            
        )

    # ---- Upload results back to s3 -----------------------
    if FLAGS.s3_bucket is not None:
        logging.info(f"Uploading {FLAGS.output_dir} to {FLAGS.s3_bucket}")
        upload_data(FLAGS.output_dir, f"s3://{FLAGS.s3_bucket}/{FLAGS.output_dir}")
    # ----------------------------


def parse_s3_url(url):
    """Returns an (s3 bucket, key name/prefix) tuple from a url with an s3 scheme. (From SageMaker s3 utils)
    Args:
        url (str):
    Returns:
        tuple: A tuple containing:
            - str: S3 bucket name
            - str: S3 key
    """
    parsed_url = urlparse(url)
    if parsed_url.scheme != "s3":
        raise ValueError(
            "Expecting 's3' scheme, got: {} in {}.".format(parsed_url.scheme, url)
        )
    return parsed_url.netloc, parsed_url.path.lstrip("/")


def upload_data(path, desired_s3_uri, s3=boto3.client("s3"), extra_args=None):
    """Upload local file or directory to S3. (From SageMaker Session)
    If a single file is specified for upload, the resulting S3 object key is
    ``{key_prefix}/{filename}`` (filename does not include the local path, if any specified).
    If a directory is specified for upload, the API uploads all content, recursively,
    preserving relative structure of subdirectories. The resulting object key names are:
    ``{key_prefix}/{relative_subdirectory_path}/filename``.
    Args:
        path (str): Path (absolute or relative) of local file or directory to upload.
        desired_s3_uri (str): Name of the S3 Bucket to upload to, plus the object key.
        s3 (boto3 object): S3 client.
        extra_args (dict): Optional extra arguments that may be passed to the upload operation.
            Similar to ExtraArgs parameter in S3 upload_file function. Please refer to the
            ExtraArgs parameter documentation here:
            https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-uploading-files.html#the-extraargs-parameter
    Returns:
        str: The S3 URI of the uploaded file(s). If a file is specified in the path argument,
            the URI format is: ``s3://{bucket name}/{key_prefix}/{original_file_name}``.
            If a directory is specified in the path argument, the URI format is
            ``s3://{bucket name}/{key_prefix}``.
    """
    # Generate a tuple for each file that we want to upload of the form (local_path, s3_key).
    bucket, key_prefix = parse_s3_url(url=desired_s3_uri)

    files = []
    key_suffix = None
    if os.path.isdir(path):
        for dirpath, _, filenames in os.walk(path):
            for name in filenames:
                local_path = os.path.join(dirpath, name)
                s3_relative_prefix = (
                    ""
                    if path == dirpath
                    else os.path.relpath(dirpath, start=path) + "/"
                )
                s3_key = "{}/{}{}".format(key_prefix, s3_relative_prefix, name)
                files.append((local_path, s3_key))
    else:
        _, name = os.path.split(path)
        s3_key = "{}/{}".format(key_prefix, name)
        files.append((path, s3_key))
        key_suffix = name

    for local_path, s3_key in files:
        s3.upload_file(local_path, bucket, s3_key, ExtraArgs=extra_args)

    s3_uri = "s3://{}/{}".format(bucket, key_prefix)
    # If a specific file was used as input (instead of a directory), we return the full S3 key
    # of the uploaded object. This prevents unintentionally using other files under the same
    # prefix during training.
    if key_suffix:
        s3_uri = "{}/{}".format(s3_uri, key_suffix)
    return
### ---------------------------------------------

if __name__ == '__main__':
    flags.mark_flags_as_required([
            'fasta_paths',
            'output_dir',
            'data_dir',
            'uniref90_database_path',
            'mgnify_database_path',
            'template_mmcif_dir',
            'max_template_date',
            'obsolete_pdbs_path',
### ---------------------------------------------            
### Modified by AWS to resolve issue found in testing.
            
            #'use_gpu_relax',
### ---------------------------------------------            
        ])

    app.run(main)
