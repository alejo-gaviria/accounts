# [Service Name] event-driven architecture

This is a **cloud-agnostic template** for documenting the event-driven flow between compute handlers (functions/lambdas), pub/sub topics, and queues in a service. It uses simulated, generic components and routes — no real implementation details — so an agent or engineer can use it as a reference for producing an equivalent document on **any** cloud provider (AWS, GCP, Azure, or a self-hosted broker).

For each handler and each API route, document: **what it processes**, **what business rules it applies**, **what it publishes**, and **where it persists data**.

**Last documented:** `<commit-hash>` — `<short commit message describing the doc update>`

When updating, scan modifications since that commit first: `git log <hash>..HEAD --oneline` or `git diff <hash>..HEAD -- src/` (replace `<hash>` with the commit above). After editing, update the hash with `git rev-parse HEAD` and a short message.

---

## Vocabulary map (pick your provider, use consistent terms)

This template uses three generic roles. Map them to whatever your actual stack uses, and stay consistent throughout the document:

| Generic term       | AWS               | GCP                          | Azure                              | Self-hosted           |
| ------------------- | ----------------- | ----------------------------- | ------------------------------------ | ---------------------- |
| **Function/Handler** | Lambda             | Cloud Function / Cloud Run     | Azure Function / Container App       | Any worker process      |
| **Topic** (pub/sub, fan-out) | SNS Topic    | Pub/Sub Topic                  | Event Grid Topic / Service Bus Topic | Kafka topic / RabbitMQ exchange |
| **Queue** (point-to-point) | SQS Queue     | Pub/Sub Subscription (pull)    | Service Bus Queue / Storage Queue    | Kafka consumer group / RabbitMQ queue |
| **Command bus**      | SQS FIFO queue     | Pub/Sub ordered topic          | Service Bus session-enabled queue    | Ordered queue with partition key |
| **Object storage**    | S3                 | Cloud Storage                  | Blob Storage                          | MinIO / any object store |
| **Batch job**         | AWS Batch          | Cloud Run Jobs / Batch          | Azure Batch / Container Apps Jobs    | Any async job runner    |
| **Scheduler/cron**    | EventBridge Scheduler | Cloud Scheduler             | Logic Apps / Azure Scheduler         | cron / Temporal        |

Do not mix vendor-specific names inside the diagram itself — use the generic term (Function, Topic, Queue) in labels, and only note the real provider mapping once, in a legend or in this table.

---

## Diagram

The example below is fully simulated (generic "Orders" domain) to show the expected shape: a handful of REST endpoints, a proxy/ingestion handler, a couple of projections that react to events and re-publish, a command handler, a scheduled job, and a worker consuming a queue. Replace with your real components, keep the four-line structure per node.

```mermaid
flowchart TB
 subgraph GET_health["GET /health"]
    direction LR
        H1["Processes: HTTP GET"]
        H2["Applied rules: none"]
        H3["Publishes: none"]
        H4["Persists to: none"]
  end
 subgraph GET_resource_summary["GET /resources/summary/&lt;id&gt;"]
    direction LR
        RS1["Processes: HTTP GET resource_id"]
        RS2["Applied rules: read-model computed from current state"]
        RS3["Publishes: none"]
        RS4["Persists to: read-only summary tables"]
  end
 subgraph POST_resource_action["POST /resources/&lt;id&gt;/approve"]
    direction LR
        RA1["Processes: HTTP POST resource_id auth user"]
        RA2["Applied rules: resource must be in PENDING state; approve by user"]
        RA3["Publishes: resource.approved → Resource Topic"]
        RA4["Persists to: resources, resource_statistics"]
  end
 subgraph POST_config_upsert["PUT /configs/&lt;scope_id&gt;"]
    direction LR
        CFG1["Processes: HTTP PUT scope_id body auth user"]
        CFG2["Applied rules: create/update config; detect version change"]
        CFG3["Publishes: ConfigUpserted → Config Topic"]
        CFG4["Persists to: scoped_configs / configs"]
  end
 subgraph POST_reports_generate["POST /reports/generate"]
    direction LR
        RG1["Processes: HTTP POST report_type filters"]
        RG2["Applied rules: find matching records by criteria"]
        RG3["Publishes: Queue message report_id kind=<TYPE> → reports queue"]
        RG4["Persists to: none"]
  end

 subgraph Proxy["Ingestion proxy"]
    direction TB
        P1["Processes: source.created, source.updated, source.status_changed"]
        P2["Applied rules: ordering by event id; skip stale; upstream reference must exist"]
        P3["Publishes: forwards same event to downstream Topic A and Topic B"]
        P4["Persists to: ingestion_snapshot"]
  end
 subgraph ProjectionA["Events → Projection A"]
    direction LR
        A1["Processes: same upstream events"]
        A2["Applied rules: create/reconcile local record; apply domain-specific eligibility rules"]
        A3["Publishes: domain_a.initialized, domain_a.flag_set/unset → Domain A Topic"]
        A4["Persists to: domain_a_aggregates, domain_a_records"]
  end
 subgraph ProjectionB["Events → Projection B"]
    direction LR
        B1["Processes: same upstream events"]
        B2["Applied rules: eligibility check; recompute or drop contribution"]
        B3["Publishes: domain_b.item_appended, item_dropped, contribution_updated → Domain B Topic"]
        B4["Persists to: domain_b_ledgers"]
  end
 subgraph CmdHandler["Command handler"]
    direction LR
        CH1["Processes: COMPUTE or RECORD commands"]
        CH2["Applied rules: COMPUTE = run aggregation for scope; RECORD = register one unit per input"]
        CH3["Publishes: domain_b.computed/cancelled → Domain B Topic (on COMPUTE)"]
        CH4["Persists to: domain_b_runs, domain_b_run_items"]
  end
 subgraph ReportsWorker["Reports worker"]
    direction LR
        RW1["Processes: Queue message report_id kind"]
        RW2["Applied rules: generate report by kind; upload to storage"]
        RW3["Publishes: none"]
        RW4["Persists to: report output to object storage"]
  end
 subgraph Cron["Scheduled job"]
    direction RL
        Cr1["Processes: cron trigger with scope (e.g. region 13:00 UTC)"]
        Cr2["Applied rules: pick eligible scopes on recurrence"]
        Cr3["Publishes: COMPUTE commands → Command Bus (Queue)"]
        Cr4["Persists to: scheduler_runs, scheduler_scopes"]
  end

    POST_config_upsert --> ConfigTopic["Config Topic"]
    POST_resource_action --> ResourceTopic["Resource Topic"]
    POST_reports_generate --> ReportsQ["reports-queue"]
    ReportsQ --> ReportsWorker

    UpstreamEvents["Upstream Events Topic (external)"] --> ProxyQ["ingestion.fifo"]
    ProxyQ --> Proxy
    Proxy --> TopicA["Domain A Topic"] & TopicB["Domain B Topic (raw)"]
    TopicA --> ProjAQ["events→projection-a.fifo"]
    ProjAQ --> ProjectionA
    ProjectionA --> DomainATopic["Domain A Topic (derived)"]
    TopicB --> ProjBQ["events→projection-b.fifo"] & CmdProjQ["events→command-projection.fifo"]
    ProjBQ --> ProjectionB
    ProjectionB --> DomainBTopic["Domain B Topic"]
    CmdProjQ --> CmdHandler
    CmdHandler --> DomainBTopic
    ConfigTopic --> ConfigProjQ["config→projection.fifo"]
    ConfigProjQ --> ProjectionB
    Cron --> CmdHandler

     GET_health:::api
     GET_resource_summary:::api
     POST_resource_action:::api
     POST_config_upsert:::api
     POST_reports_generate:::api
     UpstreamEvents:::topic
     ProxyQ:::queue
     Proxy:::function
     TopicA:::topic
     TopicB:::topic
     ProjAQ:::queue
     ProjectionA:::function
     DomainATopic:::topic
     ProjBQ:::queue
     CmdProjQ:::queue
     ProjectionB:::function
     DomainBTopic:::topic
     CmdHandler:::function
     ConfigTopic:::topic
     ConfigProjQ:::queue
     ResourceTopic:::topic
     ReportsQ:::queue
     ReportsWorker:::function
     Cron:::function
    classDef topic fill:#e8eaf6,stroke:#3f51b5,color:#1a237e
    classDef queue fill:#e0f2f1,stroke:#00695c,color:#004d40
    classDef function fill:#fff3e0,stroke:#e65100,color:#bf360c
    classDef api fill:#fce4ec,stroke:#c2185b,color:#880e4f
```

---

## How to update this diagram

### When to update

- You add or remove a **Function/Handler**, **Queue**, or **Topic** in the event flow.
- You add, remove, or change a **REST API endpoint**: add a subgraph with the endpoint's method + path and the same four sections (Processes, Applied rules, Publishes, Persists to), and an arrow to the topic/queue/function it triggers (if any).
- A handler starts or stops **processing** new event types.
- **Business rules** change (new eligibility rules, state-machine transitions, computation rules, etc.).
- A handler starts or stops **publishing** event types, or targets a different topic/queue.
- **Persistence** changes: new tables/collections, or an existing handler writes to different storage.

### Where the information lives (generic — adjust paths to your repo)

| What to update                                        | Where to look in the codebase                                                                                                 |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Processes** (event types)                              | Handler entrypoints (e.g. `src/<module>/adapters/inbound/<queue-or-topic>/*_handler.*`) — docstrings, entry function, event-name/case handling.                    |
| **Applied rules**                                        | Domain layer (e.g. `src/<module>/domain/`) — aggregates, invariants, validation — and use cases (e.g. `application/use_cases/`).                                     |
| **Publishes** (event types and target)                   | Outbound dispatchers (e.g. `src/<module>/adapters/outbound/<topic-or-queue>/`), and domain event definitions (e.g. `domain/*_events.*`).                             |
| **Persists to** (tables/collections)                     | Repositories (e.g. `src/<module>/adapters/outbound/repositories/`) — write operations, table/collection names.                                                       |
| **Flow** (which topic/queue connects to which handler)   | Infra-as-code definitions: whatever declares topics, queues, subscriptions, and event sources for your provider (e.g. CDK/Terraform/Pulumi/ARM/Deployment Manager stacks). |

### How to edit the diagram

1. **Add or remove a component**
   - **New Function/Handler:** Add a `subgraph <Id>["Label"]` with `direction TB` or `direction LR`, then four inner nodes: Processes, Applied rules, Publishes, Persists to. Connect it in the flow (topic/queue → function → topic/queue). Add a line `NewNode:::function` and keep it in the same order as other `:::function` lines.
   - **New Topic or Queue:** Add a node (e.g. `NewTopic["Topic Name"]`), connect it in the flow, then add `NewTopic:::topic` or `NewQueue:::queue`.

2. **Change Processes / Applied rules / Publishes / Persists to**
   - Edit the corresponding node text inside the right `subgraph` (e.g. `P1["Processes: ..."]`). Keep text concise so the diagram stays readable. Never put real secrets, customer data, or internal identifiers in labels — use generic descriptions.

3. **Change the flow**
   - Edit the connection lines (e.g. `TopicA --> QueueB`, `QueueB --> HandlerC`, `HandlerC --> TopicD`). Use `A --> B & C` to connect one node to two targets. Use separate lines (`A --> B` and `A --> C`) if your renderer doesn't support `&`.

4. **Styling**
   - **Topic:** `classDef topic fill:#e8eaf6,...` — pub/sub topics (fan-out).
   - **Queue:** `classDef queue fill:#e0f2f1,...` — point-to-point queues.
   - **Function:** `classDef function fill:#fff3e0,...` — all compute handlers.
   - **API:** `classDef api fill:#fce4ec,...` — REST endpoint subgraphs.
   - Every node that appears in the flow must have a line assigning it a class (e.g. `UpstreamEvents:::topic`).

5. **Subgraph layout**
   - `direction TB` (top-to-bottom) for fewer/short labels.
   - `direction LR` (left-to-right) for longer labels.

6. **Rendering**
   - The diagram uses Mermaid. Render it in GitHub, GitLab, VS Code (Mermaid extension), or any Markdown viewer that supports Mermaid. If a link or label breaks, check quotes and special characters (`"`, `→`, `&`) and escape or simplify if needed.

### Checklist after changes

- [ ] Every Topic and Queue in the flow has a `:::topic` or `:::queue` line.
- [ ] Every Function/Handler subgraph has a `:::function` line.
- [ ] Every REST endpoint subgraph has a `:::api` line and an arrow to its target (topic/queue) when it publishes or enqueues.
- [ ] All four sections (Processes, Applied rules, Publishes, Persists to) are present for each handler and each REST endpoint, and match the actual code.
- [ ] Flow matches infra-as-code: subscriptions (topic → queue), event sources (queue → function), and publish targets (function or API → topic or queue).
- [ ] No real vendor-specific service names, real table names, real business rules, or real identifiers leaked into a "template" copy of this doc — only generic/simulated examples.
