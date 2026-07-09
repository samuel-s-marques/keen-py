# Job Tracking

Every module run, Magic Chain, and playbook execution is recorded as a job in the active workspace's `job_history` table -- whether it was started from the CLI or the Web UI. This gives you one place to check what's running, review what already ran, and cancel something that's taking too long.

Jobs are workspace-scoped: switching workspaces switches which job history you're looking at.

## Usage

### Listing active jobs

`jobs list` shows only jobs that are currently `pending` or `running`.

```
keen[John Doe] > jobs list

                                     Active Jobs
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Job ID   ┃ Module                ┃ Target      ┃ Status  ┃ Progress ┃ Started             ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ 3f9a1b2c │ discovery/subdomain   │ example.com │ running │ 70%      │ 2026-07-09 10:22:01 │
└──────────┴───────────────────────┴─────────────┴─────────┴──────────┴─────────────────────┘
```

### Full history

`jobs history` shows every job regardless of status; optionally filter by a specific status (`pending`, `running`, `completed`, `failed`, `cancelled`).

```
keen[John Doe] > jobs history completed
```

### Viewing a job's logs

Every job keeps a rolling buffer of the log lines captured while it ran (capped at the most recent 500 lines), plus its error message if it failed. You can reference a job by its full ID or just the 8-character prefix shown in the table.

```
keen[John Doe] > jobs logs 3f9a1b2c
INFO     | discovery/subdomain: found subdomain 'mail.example.com'
INFO     | discovery/subdomain: found subdomain 'vpn.example.com'
```

### Cancelling a job

```
keen[John Doe] > jobs cancel 3f9a1b2c
INFO     | Job 3f9a1b2c8e1d4a6f9b2c0d5e8f1a3b7c marked cancelled.
```

If the job is still actively running in this process, cancelling it also interrupts the underlying task (not just marks it cancelled after the fact). Jobs started in a different process (e.g. a previous server run) can still be marked cancelled for record-keeping, even though there's nothing left in memory to interrupt.

## Web UI

The Web UI's task manager panel reads from the same `job_history` table via `GET /api/workspaces/{name}/jobs`. Running a module or a Magic Chain over WebSocket automatically creates and updates a job row as it progresses (including live `progress`, `node_added`, and `edge_added` events, not just log text), and the panel's **Cancel** button calls `POST /api/workspaces/{name}/jobs/{job_id}/cancel`.

## Notes for automation

- `GET /api/workspaces/{name}/jobs?status=running` -- list jobs, optionally filtered.
- `GET /api/workspaces/{name}/jobs/{job_id}` -- fetch one job's full record, including logs.
- `POST /api/workspaces/{name}/jobs/{job_id}/cancel` -- cancel a job.

See [Notifications](notifications.md) for getting alerted when a job completes or fails without watching it.
