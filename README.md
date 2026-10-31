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
```

`--list-nodes` accepts `--lists-nodes` as the same flag. `--dump-model` prints the `json_schema` stored on that model-table row. `--dump-model-recursive` also prints each nested model schema. `--model-data` prints the collection document with that id.

## simstack_upload

```bash
simstack_upload --model ModelName model_data.json
```

`model_data.json` is a JSON object of model fields. The command prints the new document id.

## simstack_submit

```bash
simstack_submit --node-name node_name --resource resource inputs.json
simstack_submit --node-name node_name --resource resource --custom-name custom-name --category category_name inputs.json
```

`inputs.json` is a JSON object whose keys are exactly the node's input names. The command writes a `NodeRegistry` row with status `submitted` and prints its id. `--custom-name` and `--category` are optional. The node's stored default parameters are kept, and `--resource` replaces the resource.

## simstack_monitor

```bash
simstack_monitor --list
simstack_monitor --list --node-name node_name --status submitted
```

`--list` prints JSON for the jobs in this database. `--node-name` and `--status` each narrow that list. `--status` must be one of the SimStack task statuses (`submitted`, `running`, `slurm_queued`, `slurm_running`, `retrieved`, `timeout`, `failed`, `completed`, `recovered`, `terminating`).
