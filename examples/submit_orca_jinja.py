"""Submit the legacy ``orca_jinja`` node from a short parameters file and XYZ.

    python examples/submit_orca_jinja.py --parameters examples/orca_jinja.json \\
        --resource justus-test-alt-core-version examples/water.xyz

The parameters file uses the calculation settings of the legacy
``orca_jinja`` node (see ``examples/orca_jinja.json``) without a molecule.
Required keys are ``basis-set``, ``aux-basis``, ``functional``,
``dispersion``, ``method``, ``charge``, ``multiplicity``, and ``optimization``.
``states`` and ``focus-states`` are optional; ``focus-states`` is required
when ``states`` is greater than 0.  The XYZ file supplies the molecule.

This example targets the **compatible_old** branch of simstack-control: it
builds the legacy ``molecular_qm_models.qm_input.QMInput`` document (not the
new-world ``OrcaQMInput``) that the legacy simstack-model runner on justus
expects, and writes ``NodeRegistry.version = "compatible_old"`` so agent jobs
can be told apart from the production battery (which stores ``version: null``).
"""

import argparse
import asyncio
import sys
from pathlib import Path

from simstack_control.jsonutil import load_json_file
from simstack_control.legacy_apps import import_legacy_orca_node
from simstack_control.legacy_qm_input import build_orca_jinja_submit_input

DEFAULT_VERSION = "compatible_old"
DEFAULT_NODE_NAME = "orca_jinja"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="submit_orca_jinja",
        description=(
            "Build the legacy orca_jinja qm_input document from a short "
            "parameters file and an XYZ geometry, then submit the node."
        ),
    )
    parser.add_argument(
        "--parameters",
        required=True,
        help="Short ORCA settings JSON. Must not contain a molecule.",
    )
    parser.add_argument("--resource", required=True, help="Execution resource.")
    parser.add_argument(
        "--params",
        help="JSON object of SlurmParameters for this job, such as nodes and tasks.",
    )
    parser.add_argument(
        "--node-name",
        default=DEFAULT_NODE_NAME,
        help=f"Node name in the node table (default: {DEFAULT_NODE_NAME}).",
    )
    parser.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=(
            f"Version stored in the NodeRegistry row (default: {DEFAULT_VERSION}). "
            "The legacy nodes have no _node_version, so the version is set "
            "manually; leave as-is for agent jobs."
        ),
    )
    parser.add_argument("--custom-name", help="Optional display name.")
    parser.add_argument("--category", help="Optional category.")
    parser.add_argument("molecule", help="XYZ file for the molecule.")
    return parser


def ensure_applications_importable() -> None:
    """Make the legacy simstack-model ``applications`` tree importable.

    ``submit_cli.submit_inputs`` imports the node function
    ``applications.electronic_structure.orca.orca.orca_jinja`` from the
    simstack-model checkout.  ``legacy_apps.import_legacy_orca_node`` locates
    that checkout (env ``SIMSTACK_MODEL_DIR`` or the sibling directory) and
    registers a ``molecular_qm_util`` stand-in when the runner-only package
    (and its openbabel dependency) is not installed client-side.
    """
    import_legacy_orca_node()


async def _main() -> None:
    args = build_parser().parse_args()
    ensure_applications_importable()

    parameters = load_json_file(args.parameters)
    xyz_text = Path(args.molecule).read_text()
    document = build_orca_jinja_submit_input(parameters, xyz_text)

    slurm_parameters = None
    if args.params:
        slurm_parameters = load_json_file(args.params)

    from simstack_control.submit_cli import submit_inputs

    task_id = await submit_inputs(
        args.node_name,
        args.resource,
        document,
        custom_name=args.custom_name,
        category=args.category,
        slurm_parameters=slurm_parameters,
        version=args.version,
    )
    print(task_id)


def main() -> None:
    try:
        asyncio.run(_main())
    except (ValueError, LookupError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
