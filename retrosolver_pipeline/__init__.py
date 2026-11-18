"""RetroSolver data pipeline (lane 2).

Python 3 standard library only. These modules MOVE and VALIDATE solver output.
They never create strategy content: every frequency and EV in a spot pack must
come from a real TexasSolver output file.
"""
PIPELINE_VERSION = "0.1.0"
SPOT_LIST_SCHEMA = "retrosolver.spot_list.v1"
BATCH_MANIFEST_SCHEMA = "retrosolver.batch_manifest.v1"
SPOT_PACK_SCHEMA = "retrosolver.spot_pack.v1"
