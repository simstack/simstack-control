# simstack-control

Command line tools for a SimStack database. Connection settings come from `simstack.toml` in the project root, using the same `[parameters.db]` and `[parameters.general]` tables as simstack-mariana. `context.initialize()` reads that file, so run the commands from this repository (or another project that contains `simstack.toml`).

The database named in `simstack.toml` is the current user's database. `simstack_monitor` lists jobs from that database.

Node and model classes named in the node table and model table must be importable in the environment you use for `simstack_upload` and `simstack_submit`.

```bash
uv sync
```

`simstack.toml` is gitignored. Create it in the project root and set `connection_string` before contacting the database.

## simstack_inspect

```bash
simstack_inspect --list-nodes
simstack_inspect --list-models
simstack_inspect --dump-model ModelName
simstack_inspect --dump-model-recursive ModelName
simstack_inspect --model-data ModelName 0123456789abcdef01234567
simstack_inspect --node-id 0123456789abcdef01234567
```

`--list-nodes` accepts `--lists-nodes` as the same flag. `--dump-model` prints the `json_schema` stored on that model-table row. `--dump-model-recursive` also prints each nested model schema. `--model-data` prints the collection document with that id. `--node-id` prints the job's inputs, outputs, and `child_uuids`. File stacks are omitted.

## simstack_upload

```bash
simstack_upload --model ModelName model_data.json
```

`model_data.json` is a JSON object of model fields. The command prints the new document id.

## simstack_submit

```bash
simstack_submit --node-name node_name --resource resource inputs.json
simstack_submit --node-name node_name --resource resource --custom-name custom-name --category category_name inputs.json
simstack_submit --node-name node_name --resource resource --params params.json inputs.json
```

`inputs.json` is a JSON object whose keys are exactly the node's input names. The command writes a `NodeRegistry` row with status `submitted` and prints its id. `--custom-name`, `--category`, and `--params` are optional. The node's stored default parameters are kept, and `--resource` replaces the resource.

`params.json` is a `SlurmParameters` object for this master job. Set the fields you want to change, for example `nodes` and `tasks`. Omitted fields stay as the node stored them. Unknown fields are an error.

```json
{
  "nodes": 1,
  "tasks": 8,
  "cpus_per_task": 4,
  "mem": "16G",
  "time": "04:00:00"
}
```

## submit_orca_jinja (compatible_old branch)

This branch targets the **legacy** simstack-model environment pinned in
`pyproject.toml` (`simstack==v2.0.1.post1`, `molecular_qm_models@72f8dcb`,
`numpy==2.4.1`).  It submits the legacy ``orca_jinja`` node whose qm_input
schema is the legacy ``molecular_qm_models.qm_input.QMInput`` document — not
the new-world ``OrcaQMInput`` (which does not exist at the pinned revisions
and was removed together with the old ``examples/submit_orca.py``).

```bash
python examples/submit_orca_jinja.py \
    --parameters examples/orca_jinja.json \
    --resource justus-test-alt-core-version \
    examples/water.xyz
```

- `orca_jinja.json` is a short settings file without a molecule. Required
  keys are `basis-set`, `aux-basis`, `functional`, `dispersion`, `method`,
  `charge`, `multiplicity`, and `optimization`. Optional keys include
  `states`/`focus-states`, `frequencies`, `gradients`, solvent (with
  `solvent-model`), the electrical-property toggles, and `frozen-atoms`
  (0-based atom indices pinned during geometry optimization).
- `water.xyz` is the geometry. `orca_jinja_input.json` in the repository
  root is the exact document built for water — a ready-to-submit input file.
- Optional slurm overrides: `--params examples/justus-params.json`
  (partition `nano`, 16 tasks per node, 20G, 200 h — matching the jobs that
  already run on `justus-test-alt-core-version`).
- `--node-name` defaults to `orca_jinja`; other legacy variants such as
  `orca_jinja_no_restart_from_gbw` can be passed explicitly.
- `--version` defaults to `compatible_old`. The legacy nodes have no
  `_node_version`, so `submit_inputs` writes the explicit version into the
  `NodeRegistry` row. This makes agent jobs identifiable while the running
  production battery keeps `version: null`.

Requirements:

- The simstack-model checkout (with the legacy `applications/` tree) must be
  importable — the example adds the sibling directory `../simstack-model` to
  `sys.path` automatically, or set `SIMSTACK_MODEL_DIR`. The client does not
  install the runner-only `molecular_qm_util`/`pymatgen`/openbabel packages;
  `simstack_control.legacy_apps` provides import-time stand-ins so the node
  function can be introspected for submission.
- A local `simstack.toml` with the justus DB credential (copy
  `simstack-model/justus.toml` to `simstack.toml` in this repository).

## simstack_monitor

```bash
simstack_monitor
simstack_monitor --node-name node_name --status submitted
simstack_monitor --id 0123456789abcdef01234567
simstack_monitor --ids 0123456789abcdef01234567,0123456789abcdef01234568
```

Every invocation prints JSON with `uuid`, `name`, `custom_name`, `category`, and `status`. With no selectors it includes the jobs in this database. `--node-name` and `--status` narrow that list. `--id` keeps one uuid and `--ids` keeps a comma-separated list, in the order given. A uuid that does not match is an error. `--status` must be one of the SimStack task statuses (`submitted`, `running`, `slurm_queued`, `slurm_running`, `retrieved`, `timeout`, `failed`, `completed`, `recovered`, `terminating`).
