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

## submit_orca

```bash
python examples/submit_orca.py --parameters orca.json --resource jusuf molecule.xyz
```

`orca.json` is a short settings file. It has no molecule. Required keys are `basis-set`, `aux-basis`, `functional`, `dispersion`, `method`, `charge`, `multiplicity`, and `optimization`. Optional keys include `states`, `focus-states` (required when `states` is greater than 0), `frequencies`, solvent, and the other `OrcaQMInput` settings. The geometry comes from `molecule.xyz`.

The script builds the `qm_input` object that `simstack_submit --node-name orca` reads and submits that node. `orca_input.json` in the repository root is that object for water. `examples/orca.json` and `examples/water.xyz` are the short inputs that produce it. `examples/formaldehyde.xyz` is another geometry for the same settings.

## simstack_monitor

```bash
simstack_monitor
simstack_monitor --node-name node_name --status submitted
simstack_monitor --id 0123456789abcdef01234567
simstack_monitor --ids 0123456789abcdef01234567,0123456789abcdef01234568
```

Every invocation prints JSON with `uuid`, `name`, `custom_name`, `category`, and `status`. With no selectors it includes the jobs in this database. `--node-name` and `--status` narrow that list. `--id` keeps one uuid and `--ids` keeps a comma-separated list, in the order given. A uuid that does not match is an error. `--status` must be one of the SimStack task statuses (`submitted`, `running`, `slurm_queued`, `slurm_running`, `retrieved`, `timeout`, `failed`, `completed`, `recovered`, `terminating`).
