# Original Copyright 2021 DeepMind Technologies Limited
# Modifications Copyright 2022 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

### ---------------------------------------------
### Modified by Amazon Web Services (AWS) to update cuda version and add Alphafold
### parameter
ARG CUDA=11.7.0
ARG AF_VERSION=v2.2.0
ARG UBUNTU_VERSION=22.04
FROM nvcr.io/nvidia/cuda:${CUDA}-runtime-ubuntu${UBUNTU_VERSION}
# FROM directive resets ARGS, so we specify again (the value is retained if
# previously set).
ARG CUDA
ARG AF_VERSION
### ---------------------------------------------

# Use bash to support string substitution.
SHELL ["/bin/bash", "-c"]

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
      build-essential \
      cmake \
      cuda-command-line-tools-${CUDA/%.?/} \
      git \
      hmmer \
      kalign \
      tzdata \
      wget \
    && apt-get install -y --only-upgrade openssl \
    && rm -rf /var/lib/apt/lists/*

# Compile HHsuite from source.
RUN git clone --branch v3.3.0 https://github.com/soedinglab/hh-suite.git /tmp/hh-suite \
    && mkdir /tmp/hh-suite/build \
    && pushd /tmp/hh-suite/build \
    && cmake -DCMAKE_INSTALL_PREFIX=/opt/hhsuite .. \
    && make -j 4 && make install \
    && ln -s /opt/hhsuite/bin/* /usr/bin \
    && popd \
    && rm -rf /tmp/hh-suite

# Install mambaforge package manager.
RUN wget -q -P /tmp \
  https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-Linux-x86_64.sh \
  && bash /tmp/Mambaforge-Linux-x86_64.sh -b -p /opt/mamba \
  && rm /tmp/Mambaforge-Linux-x86_64.sh

# Install conda packages.
ENV PATH="/opt/mamba/bin:$PATH"
RUN mamba update -qy mamba \
    && mamba install -y -c conda-forge \
      openmm==7.5.1 \
      cudatoolkit==${CUDA/%.?/} \
      pdbfixer \
      pip \
      python==3.9 \
      awscli

RUN git clone --branch ${AF_VERSION} --depth 1 https://github.com/deepmind/alphafold.git /app/alphafold

COPY run_aws_alphafold.py /app/alphafold

### ---------------------------------------------     
RUN aws s3 cp s3://aws-batch-architecture-for-alphafold-public-artifacts/stereo_chemical_props/stereo_chemical_props.txt /app/alphafold/alphafold/common/

# Install pip packages.
RUN pip3 install --upgrade pip \
    && pip3 install -r /app/alphafold/requirements.txt \
    && pip3 install --upgrade jax jaxlib==0.3.10 -f \    
      https://storage.googleapis.com/jax-releases/jax_releases.html \
    && pip3 install boto3 protobuf==3.20.1 six==1.15.0 botocore==1.27.0 --force-reinstall
### ---------------------------------------------     
# Apply OpenMM patch.
WORKDIR /opt/mamba/lib/python3.9/site-packages
RUN patch -p0 < /app/alphafold/docker/openmm.patch

# Clean up
RUN rm -rf /app/alphafold/docker /app/alphafold/imgs /app/alphafold/notebooks /app/alphafold/scripts
### ---------------------------------------------     

# We need to run `ldconfig` first to ensure GPUs are visible, due to some quirk
# with Debian. See https://github.com/NVIDIA/nvidia-docker/issues/1399 for
# details.
# ENTRYPOINT does not support easily running multiple commands, so instead we
# write a shell script to wrap them up.
WORKDIR /app/alphafold
RUN echo $'#!/bin/bash\n\
ldconfig\n\
### ---------------------------------------------
### Modified by AWS to point to new script    
python /app/alphafold/run_aws_alphafold.py "$@"' > /app/run_aws_alphafold.sh \
  && chmod +x /app/run_aws_alphafold.sh
ENTRYPOINT ["/app/run_aws_alphafold.sh"]
### ---------------------------------------------
