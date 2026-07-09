# Playbooks

Playbooks let you define a repeatable pivot chain in YAML instead of clicking through modules by hand or relying entirely on [Magic Chaining](magic_engine.md)'s automatic BFS. A playbook is a small DAG of steps, each running one module, where later steps can depend on what an earlier step discovered.

Playbooks share the same execution path as Magic Chaining -- the same API-key loading and the same [execution-safety gate](scope_and_safety.md) apply, so a playbook can't run an active/intrusive module any more freely than a human `run` can.

## Writing a playbook

```yaml
# playbooks/infra_sweep.yaml
name: Infrastructure Pivot & Threat Scan
trigger_type: domain-name
steps:
  - id: dns_sweep
    module: discovery/dns_enum
    inputs: { TARGET: "{{ trigger.value }}" }

  - id: shodan_ports
    module: intel/shodan_host
    depends_on: dns_sweep
    inputs: { TARGET: "{{ dns_sweep.node_value }}" }
    condition: "node.type == 'ipv4-addr' and not node.metadata.is_private"
```

- Steps with no `depends_on` run immediately, seeded from the trigger value you pass on the command line (`{{ trigger.value }}`).
- A step with `depends_on` runs **once for every node its dependency discovered**, optionally filtered by `condition`. In the example above, `shodan_ports` only runs against public IPv4 addresses `dns_sweep` found -- private ones are skipped.
- `{{ dns_sweep.node_value }}` is re-rendered for each qualifying node, so `shodan_ports` gets a different `TARGET` each time it runs.
- `inputs` can set any of the module's options, not just its target option -- every key is applied via the module's normal `set_option`.

!!! note "Template syntax is intentionally minimal"

    `{{ dotted.path }}` substitution is a small, dependency-free implementation -- not Jinja2. It only does dotted-path lookups against the trigger and prior step results; it can't run arbitrary expressions. `condition` strings are evaluated by a whitelisted mini-interpreter (comparisons, `and`/`or`/`not`, `in`) -- never Python's `eval()` -- since playbook YAML is user-authored and may eventually be shared between users.

## Running a playbook

```
keen[John Doe] > playbook playbooks/infra_sweep.yaml example.com
INFO     | Running playbook 'Infrastructure Pivot & Threat Scan' on: example.com
[playbook] step 'dns_sweep': running 'DNS Enum' on 'example.com'
[playbook] step 'shodan_ports': running 'Shodan Host' on '1.2.3.4'
SUCCESS  | Playbook completed: 2 step(s) ran, 3 node(s) discovered.
```

Every step's module run is tracked the same way a manual `run` is -- see [Job Tracking](jobs.md) for reviewing progress, logs, and cancelling a long-running playbook.

## Step dependency rules

- A step can only `depends_on` a step defined earlier in the same playbook; referencing an unknown step id fails immediately with a clear error rather than running partway through.
- A dependency cycle (`a` depends on `b`, `b` depends on `a`) is detected and the playbook stops there instead of hanging.
- Steps whose dependencies are already satisfied run concurrently, the same per-depth concurrency model Magic Chaining uses -- independent steps don't wait on each other.
- Only a step's **first** listed dependency's discovered nodes are iterated today; multi-dependency joins aren't supported yet.

## Automated chaining and active modules

Like Magic Chaining, a playbook step will not run an `active`/`intrusive` module automatically unless the `magic_allow_active_modules` preference is explicitly enabled -- see [Scope & Execution Safety](scope_and_safety.md#automated-chaining-and-active-modules).
