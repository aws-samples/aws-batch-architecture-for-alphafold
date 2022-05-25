#!/bin/sh

if [ ! -d ${code_folder} ]; then
  mkdir ${code_folder};
fi
# clone repo
git clone ${code_repo} ${code_folder}
# zip it
cd ${code_folder}
zip -r ../lokafold-v2.2.0.zip . -x ".git/*"
