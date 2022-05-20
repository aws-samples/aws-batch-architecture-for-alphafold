# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2022-05-20

### Fixed

### Changed

- Added additional download scripts to help address the instability of the public PDB mmcif mirror.
- Moved download jobs into private subnet for increased security.

## [1.0.1] - 2022-02-25

### Fixed

- Fix bug in download-Dockerfile that was causing download jobs to run longer than needed.
- Fix typo in section headers in AWS-AlphaFold notebook.

### Changed

- Add table of contents to AWS-AlphaFold notebook.

## [1.0] - 2022-02-24

### Changed

- Open Source Release

## [0.2] - 2022-02-23

### Changed

- Documentation updates
- Security and IP updates

## [0.1] - 2022-02-10

### Added

- Initial Release
- Submit 1- and 2-step protein-folding jobs to AWS Batch using a Jupyter Notebook.
