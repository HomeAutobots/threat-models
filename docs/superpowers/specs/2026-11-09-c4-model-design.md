# C4 model with Structurizr: design

Status: draft for the owner's approval, 2026-11-09. Replaces the hand-written DFD
(`systems/<slug>/dfd.md`) with a C4 model written in Structurizr's DSL. Supersedes the DFD parts of
`2026-11-08-web-app-design.md` (§5.4 element details, §6.5) and absorbs the "DFD pass" items held in
the follow-ups list.

A worked example that follows every rule below is in `2026-11-09-c4-model-example.dsl`, next to this
file. It describes a made-up shop. On 2026-11-09 it passed the pinned Structurizr's `validate`, and it
exported to JSON and to a static site.

## 1. Intent

The owner wants each system's architecture rebuilt on Simon Brown's C4 model, written with
Structurizr. In the owner's words, C4's organization and granularity "can give us richer insight
into threats and how they connect." Following the Structurizr method, every block has a name, a
technology, and a description, and every component, path, and block has an ID "so we can easily
pinpoint risks and paths."

Today's DFD is a Markdown file with one large Mermaid diagram, which the owner found hard to read.
The C4 model replaces it as the thing the agent drafts, the owner approves, and every risk points
at. The owner looks at the diagrams in Structurizr's own viewer.

C4 alone is not a threat model. C4 has no trust boundaries, and its arrows carry intent, not data.
The guide's rule still holds: "A threat model needs data flows and trust boundaries. Any view that
lacks either is an input." This design adds both inside the Structurizr model, using Structurizr's
own extension points (tags, properties, and styles), so the file stays a valid Structurizr workspace
that its viewer opens.

## 2. Goals, non-goals, anti-goals

Goals:
- Each system has one Structurizr workspace, `systems/<slug>/workspace.dsl`. It is the single
  source for the system's architecture and replaces `dfd.md`.
- The agent drafts and revises the workspace from `inputs/`. The owner approves it before threats
  are drafted. Every risk cites its IDs.
- Every element, path, and trust boundary has a stable ID, and the ID shows on the diagrams.
- Trust boundaries are modeled and drawn. tmreg computes which boundaries each path crosses; nobody
  types them.
- The owner sees the diagrams in Structurizr's own viewer. The web app serves Structurizr's static
  export of it, behind the web app's lock (§8).
- The web app:
  - shows every element, path, and boundary with its details and its risks;
  - shows what changed since the last approval, and approves the model;
  - follows a route across several paths and shows the risks along it. This is "how threats
    connect".
- Existing registers carry over. Live risks move to the new IDs through a mapping the owner
  approves, and history stays verifiable.

Non-goals:
- Drawing C4 diagrams in our web app. Structurizr's viewer draws them, and Mermaid leaves the web
  app.
- Editing the model in the browser, or in the viewer beyond the viewer's own layout changes.
- Structurizr's server, cloud, publishing, or AI features.
- Structurizr's MCP server (looked at on 2026-11-09, `docs.structurizr.com/ai/mcp`). Its tools
  validate, parse, inspect, and export DSL. It is left out for three reasons:
  - The hosted instance, `mcp.structurizr.com`, would send each system's architecture off the
    machine.
  - A local instance runs the same parser that executes `!script` and `!plugin`, and its docs don't
    say it turns them off. The agent, which reads untrusted `inputs/`, would send DSL to it before
    tmreg's check. It also listens over HTTP with no credential, which is the exposure §8 found in
    the live viewer.
  - It would add a tool channel beside the guard, outside the allow-list that four files keep in
    step.

  What it offers is covered without it. `c4 check` gives the agent a parse check plus this design's
  own rules. The real parser runs once per export, after tmreg's check, with no network, and the
  approve panel reports its verdict (§10).
- Structurizr's live `local` server, and dragging boxes to rearrange and save a layout. Diagrams use
  automatic layout (§8 says why).
- Code-level diagrams. Components found automatically from source code (`!components`).
- Showing risks inside the Structurizr viewer. That comes later (§16).

Anti-goals (a failure even if everything else works):
- A model file runs code, or fetches anything from the network, when tmreg, the web app, or the
  viewer reads it.
- A risk cites an ID that is not in the approved model.
- An ID is renumbered or reused, so an old risk points at the wrong thing.
- Boundary crossings drift away from the diagrams because someone typed them.
- tmreg needs Docker or Java to check, approve, or read a model.
- tmreg accepts a file that Structurizr rejects or reads differently.
- Anything other than the signed-in browser can read the diagrams, or change what they show.
- Another system's model, or the exported diagram sites, end up in git.
- Adoption rewrites or hides history.

## 3. Decisions

| Decision | Choice | Who |
|---|---|---|
| Notation and tool | Rebuild on the C4 model with Structurizr; follow Simon Brown's method | Owner |
| Why | Richer insight into threats and how they connect | Owner |
| Every block | Has a name, a technology, and a description | Owner |
| IDs | Every component, path, and block has an ID, to pinpoint risks and paths | Owner |
| Paths | One-way, labeled arrows, as in Structurizr's method | Owner |
| Viewing diagrams | Structurizr's own viewer | Owner |
| Which form of the viewer | Structurizr's static export, served by the web app behind its lock. Testing showed the live `local` server lets any web page or local program rewrite what it shows, even with editing turned off (§8) | My call |
| Zoom levels | Context, container, and deployment always. Component only on a trigger (§5.2). Code never | My proposal; owner agreed |
| Who decides a zoom-in | The agent proposes it and names the trigger; the owner accepts it by approving the model | My call |
| Trust boundaries | Deployment nodes tagged `Trust boundary`, drawn as dashed red boxes; crossings computed (§5.6) | My proposal; owner agreed |
| Boundaries inside one container | A group of components inside that container (§5.6) | My proposal; owner agreed |
| Arrow direction | From the side that starts the exchange; data in both directions recorded on the path (§5.5) | My call; owner saw it |
| Model files run no code | tmreg refuses scripts, plugins, includes, and anything fetched from the web before any reader sees the file (§6) | My call; owner saw it |
| Structurizr install | The official Docker image, pinned by digest; Docker and Java were already installed | My call |
| ID scheme | Structurizr identifiers with fixed prefixes; names start with their ID (§5.3) | My call |
| Who reads the DSL | tmreg's own standard-library parser of a strict subset, tested against real Structurizr (§6, §13) | My call |
| Making the diagrams | "Open diagrams" checks the file, exports it with a one-off Docker run that has no network, and the web app serves the result (§8) | My call |
| Web app's job | Tables, risks, routes, changes, and approval; links into the viewer for pictures (§10) | My call |
| What an approval stores | The file's hash, its IDs, the parsed model, and the source text (§7.3) | My call |
| Existing registers | Adopted through `tm.was` mappings the owner approves, with one logged edit per live risk (§7.6) | My call |
| Pending AI re-reviews at adoption | Adoption waits until none are left (§7.6) | My call |
| What counts as a change | Any stored field, the parent, a path's ends, or a computed crossing or zone; not `tm.was` (§7.4) | My call |
| People and outside systems in several environments | One zone per environment, `tm.zone.<ENV id>` (§5.6) | My call |
| Reusing numbers | An ID that any earlier approval used is never given to a different item (§5.3) | My call |
| "Open risks" | Unresolved statuses, with drafts awaiting review counted separately (§7.5) | My call |
| STRIDE and the DFD checklist | Kept, through DFD roles computed from the C4 model (§5.8) | My call |
| Data classes | Declared in the workspace's properties (§5.7) | My call |
| The guide | Update only the pages that describe the tool. The C4 teaching page stays as it is (§14) | My call |

## 4. Constraints

- tmreg: Python 3.11 or later, standard library only. It reads the DSL with its own parser (§6),
  and it never needs Docker.
- The guard: Python 3.9 or later, standard library only, with no tmreg imports.
- The web app's dependencies live only under `webapp/`. Mermaid is removed.
- Every rule lives in `core.py`. The CLI and the web server are front ends, as in the web app
  spec §4.
- Structurizr is pinned to the image `structurizr/structurizr:2026.09.19`, digest
  `sha256:721136283c2f9cf1ba69037bc9de136c579d66fdcb2d771cb60546ec68def1a5`, pulled on
  2026-11-09. Changing the pin is a deliberate change that reruns the conformance tests (§13).
- Docker runs only one-off exports and tests, with no network. No Structurizr server keeps running.
- The web app listens on `127.0.0.1` only, and serves the diagrams behind its lock.
- Risk data never enters git. Fixtures and tests use the guide's reference system or made-up
  systems only.

## 5. The model

### 5.1 The file

- Each system has one file, `systems/<slug>/workspace.dsl`, in UTF-8. The real and trial registers
  share it, and each register keeps its own approvals, as with `dfd.md` today.
- The header:
  - `workspace "<system name>" "<description>"`;
  - `!identifiers flat`;
  - `configuration { scope softwaresystem }`;
  - workspace `properties` holding `tm.version` and the data classes (§5.7).
  - `tm.version` is a plain token. A new file starts at `1.0`, and any change bumps the minor
    number.
- Exactly one software system is in scope: the only system that has containers.

### 5.2 Levels: what gets drawn

| Level | When | View key |
|---|---|---|
| System context | Always | `context` |
| Container | Always | `containers` |
| Deployment | Always, one per environment | `deployment-<ENV id>` |
| Dynamic | Only for an exchange whose security depends on order, used sparingly (as Brown advises). Examples: a sign-in handshake (OAuth or OIDC), payment authorization and capture, a webhook | `<SEQ id>` |
| Component | Only for a container that meets a zoom trigger | `components-<C id>` |
| Code | Never | none |

A container is opened up into components when any of these is true:
1. It makes security decisions for others: sign-in, permissions, tenant separation, or issuing
   and checking tokens.
2. It holds or hands out secrets: credentials, payment tokens, or encryption keys.
3. It takes untrusted input that is hard to handle safely: uploads, rich documents, templates, or
   prompts to an AI model.
4. It can take dangerous actions: refunds, admin changes, running code, or AI agent tools.
5. It mixes trust levels inside one deployable unit, such as a monolith that serves both customers
   and admins.
6. A threat can't be pinned down or fixed without knowing which part inside does what.
7. Past incidents or pen-test findings keep pointing at it.

How a zoom-in works:
- The container records why it was opened up in the property `tm.zoom`: the trigger numbers and a
  reason, for example "2, 4: holds payment tokens and issues refunds".
- The agent proposes each zoom-in in its check file. The owner accepts it by approving the model.
- A component view covers only that one container.
- A container that is opened up is analyzed through its components. Risks can still cite the
  container itself.

Code is never drawn. When the question is whether one control is built correctly, such as a crypto
routine, a parser, or a signature check, that belongs to a code review or a test. A risk's
controls or evidence can name it.

This follows Brown's guidance:
- System context and container diagrams are enough for most teams.
- Component diagrams are only worth drawing "if you feel they add value".
- Code diagrams are "not recommended for anything but the most important or complex components".

### 5.3 IDs

Every element, path, trust boundary, deployment environment, and dynamic view has an ID. The ID is
its Structurizr identifier (flat), so the same ID appears in the file, on the diagram, and in risks.

| Prefix | Kind | Structurizr construct |
|---|---|---|
| `A` | Person (actor) | `person` |
| `S` | Software system, in scope or outside it | `softwareSystem` |
| `C` | Container | `container` |
| `K` | Component | `component` |
| `R` | Path | relationship (`->`) |
| `TB` | Trust boundary | `deploymentNode` tagged `Trust boundary`, or a component `group` (§5.6) |
| `N` | Deployment node that is not a boundary | `deploymentNode` |
| `I` | Infrastructure node | `infrastructureNode` |
| `ENV` | Deployment environment | `deploymentEnvironment` |
| `SEQ` | Dynamic view (a sequence) | `dynamic` view key |

ID rules:
- The grammar is `^(A|S|C|K|R|TB|N|I|ENV|SEQ)[1-9][0-9]*$`, and it is case-sensitive.
- A new item takes the next number above the highest of its kind ever used. That covers the file,
  every earlier model approval in either register, and, for `TB`, the old DFD's boundaries. `c4 check`
  prints the next free number of each kind.
- An ID is never renumbered or reused. An ID that any earlier approval used is never given to a
  different item.
  - The one exception is an old DFD boundary whose new box claims it through `tm.was`. For example,
    the edge box can keep `TB1` (§11).
  - Removing an item is the owner's call, as today.

Structurizr cannot show an identifier on a diagram, so the names carry the ID:
- Every name starts with its ID and a space: "C3 Order API".
- Every path's description starts with its ID: "R4 Charges cards using".
- A dynamic view's title starts with its ID.
- tmreg checks that each prefix matches its identifier.

What has no ID of its own:
- Container and system instances on deployment diagrams. They show their container's or system's
  name, and so its ID.
- Structurizr's implied relationships, which it draws on the context view. Risks never cite them.

The web app shows where an item sits, for example `S1 › C3 › K2`.

### 5.4 Elements

| Kind | Required | tm properties |
|---|---|---|
| A person | name, description | `tm.zone.<ENV id>` for every environment (§5.6) |
| S software system | name, description. A system outside the scope is tagged `External` | `tm.zone.<ENV id>` for every environment in which it has no deployment instance |
| C container | name, description, technology | `tm.owner`. A data store is tagged `Data store` and lists `tm.data.stored` (§5.7). `tm.zoom` when it has components |
| K component | name, description, technology | Same as a container |
| N deployment node | name, description, technology | none |
| TB trust boundary | name, description, technology | `tm.enforced_by` |
| I infrastructure node | name, description, technology | none. Used for something that sits in a boundary but carries no path, such as a VPN gateway, firewall, or WAF. No paths in this version |
| ENV environment | name | none |

Every boundary box must hold at least one node, instance, or infrastructure node.
- The admin network that only a person sits in is an example. It holds the VPN gateway.
- The reason: Structurizr doesn't draw an empty deployment node.
- Structurizr's optional `inspect` report calls an infrastructure node without paths
  "disconnected". That is expected, and tmreg's own checks take the place of `inspect`.

Wording rules:
- Where inputs don't state a technology, an owner, what enforces a boundary, or how a hop is
  authenticated, the value is `unknown — ask <role>`, as today.
- `tm.assumed` marks an item that no input supports. It holds the reason, and it replaces writing
  `assumed` in a cell.

### 5.5 Paths

- **What a path is:** a Structurizr relationship, a one-way arrow labeled with its intent and its
  technology. Brown's rules apply: the label matches the arrow's direction, and a bare "Uses" is
  not a label.
- **Direction:** the arrow starts at the side that starts the exchange. Brown requires one
  convention throughout, and this is it.
  - The reply is recorded on the same path.
  - A reply that needs its own authorization, or goes somewhere else, is a path of its own.
- **Required fields:**
  - description: the ID and the intent;
  - technology: the protocol and transport, including mutual TLS;
  - `tm.data.sent` and `tm.data.returned`: data classes from §5.7, or `none`;
  - `tm.auth`: authentication and authorization on this hop, including any change of identity.
- **Async:** the tag `Async` marks a message sent through a queue or an event, and the standard
  style draws it dashed.
- **What paths connect:** people, systems, containers, and components.
  - When a container is opened up, its paths are re-pointed to the specific components and keep
    their IDs.
  - Structurizr's implied relationships still draw those paths at the container level.
- **Deployment-level relationships** are not used in this version.

### 5.6 Trust boundaries

**Boundaries:**
- Structurizr has no trust-boundary type. A trust boundary here is a deployment node tagged
  `Trust boundary`: a box around what it protects, such as the internet, a cloud account, a subnet,
  a cluster, an admin network, or a third party.
- Nested nodes give nested zones.
- The standard style draws a boundary as a thick dashed red box.
- `tm.enforced_by` says what enforces the boundary.

**Zones:**
- A container's zones in an environment are the boundary nodes that enclose its instance, from
  outermost to innermost.
- A component takes its container's zones.
- A person has one zone per environment: `tm.zone.<ENV id>`, holding a TB ID from that environment,
  or `outside`. An administrator might be `tm.zone.ENV1` = `TB5` (the admin network) in
  production, and `tm.zone.ENV2` = `outside` in staging.
- An external system's zones come from its deployment instance in that environment. Where it has
  no instance, they come from `tm.zone.<ENV id>`.

**Crossings:**
- tmreg computes crossings for each environment. A path crosses every boundary that encloses one
  end and not the other.
- In the worked example:
  - `R2`, from the web front end in the customer's browser to the checkout handler, crosses `TB1`,
    `TB2`, and `TB3`.
  - `R6`, from the admin on the admin network to the admin handler, crosses `TB5`, `TB2`, `TB3`,
    and `TB6`.
- When a container has several instances, its paths cross the union of their boundaries.

Every container in scope must have at least one instance in every environment, so that every path
has known crossings. The check fails otherwise.

**Boundaries inside one container** (zoom trigger 5, such as tenant separation, or customer-facing
handlers next to admin-only ones):
- The boundary is a Structurizr `group` inside the container, named with a TB ID, such as
  "TB7 Admin handlers". It holds the components on its inside.
- The container's property `tm.enforced_by.TB7` says what enforces it.
- Structurizr draws the group as a dashed box on the component view.
- A path with one end inside the group and one outside crosses it.
- Groups are used only for this.

Flagging an unenforced boundary as a finding stays the agent's and the owner's job, as in the
guide's checklist.

### 5.7 Data classes

- The data classes are declared once, in workspace properties. Each one is
  `tm.dataclass.<Name>`, holding examples and regulatory hooks, for example
  `"Examples: name, address, email, phone. Regulatory: GDPR, CCPA."`
- Paths and data stores name classes from this list, and tmreg refuses an undeclared class.
- Where each class lives is computed, not written: from data stores (`tm.data.stored`) and paths
  (`tm.data.sent`, `tm.data.returned`).
- The `personal_data_classes` in `system.toml` must name declared classes.

### 5.8 DFD roles

The DFD becomes a view computed from the C4 model. That keeps three things working:
STRIDE-per-element, LINDDUN, and the guide's DFD checklist. tmreg gives each item a role, using the
guide's mapping from C4 to DFD:

| C4 item | DFD role |
|---|---|
| Person; a software system outside the scope | External entity |
| Container or component tagged `Data store` | Data store |
| Any other container or component | Process |
| Path | Data flow |
| Deployment node or group tagged as a boundary | Trust boundary |
| The system in scope, other deployment nodes, infrastructure nodes, environments, sequences | None |

### 5.9 Views and styles

- The required views have the fixed keys in §5.2.
  - Explicit keys keep the viewer's links stable. Structurizr warns that the keys it generates can
    change.
- Every view has a title that names its type and scope, as Brown asks, for example
  "Container diagram for S1 Ordering platform".
- Every element appears in at least one view.
- The reference workspace holds a standard styles block. Every workspace copies it:
  - `Trust boundary`: a thick dashed red border;
  - `Data store`: a cylinder;
  - `External`: grey;
  - `Group`: the same dashed red border, for boundaries inside a container;
  - `Async`: a dashed line.
- Structurizr draws each diagram's key itself.

## 6. The safe dialect

Structurizr's DSL can run code and fetch from the network:
- `!script` runs Groovy, Kotlin, Ruby, or JavaScript, and `!plugin` runs Java.
- `!include`, `extends`, icons, themes, and image views can fetch from the network.

Structurizr's viewer and validator run scripts, and no documented setting turns that off. The agent
writes this file, so tmreg accepts only a strict subset, and every reader goes through tmreg first.

**Allowed:** only the constructs in §5:
- `workspace`, `name`, `description`, `properties`, `!identifiers flat`, and `configuration` with
  `scope`;
- `model`, `person`, `softwareSystem`, `container`, `component`, and `group` (inside a container
  only);
- `deploymentEnvironment`, `deploymentNode`, `infrastructureNode`, `softwareSystemInstance`, and
  `containerInstance`;
- relationships (`->`) that have an identifier;
- `tags`, `description`, and `technology`;
- the views `systemContext`, `container`, `component`, `deployment`, and `dynamic`, with
  `include *`, `autoLayout`, and `title`. A dynamic view lists its paths by ID instead of an
  include. Using only `include *` guarantees that every element appears in a view;
- `styles`, with element and relationship styles that use no icon.

**Refused:**
- Any `!` directive other than `!identifiers flat`, anywhere in the file, including inside strings.
  This covers `!script`, `!plugin`, `!include`, `!docs`, `!adrs`, `!decisions`, `!components`,
  `!extend`, `!ref`, `!element`, `!elements`, `!relationship`, `!relationships`, `!const`,
  `!constant`, `!var`, and `!impliedRelationships`.
- These keywords, used as a statement: `extends`, `archetypes`, `url`, `icon`, `logo`, `theme`,
  `themes`, `image`, `perspectives`, `terminology`, `users`, `visibility`, `branding`, `filtered`,
  `custom`, and `animation`.

**Layout rules:**
- One statement per line.
- `{` ends a line, and `}` stands on a line by itself.
- Strings are double-quoted, stay on one line, and contain no `"` or `\`. This avoids depending on
  Structurizr's escape rules.
- No text blocks, line continuations, or comments of any kind. A comment would be text the reviewer
  never sees on a diagram.

**Text rules:**
- No control characters other than newline and tab.
- No bidirectional or invisible formatting characters. This is the same set the web app's
  `visible()` marks.
- The file is at most 512 KiB.

**Vocabulary:**
- Properties: only the `tm.*` names in §5.4–§5.7, plus `structurizr.inspection.*` workspace
  properties (used to turn off Structurizr's documentation and decisions inspections). An unknown
  `tm.` name is an error.
- Tags: only `Trust boundary`, `Data store`, `External`, and `Async`. Styles may also name
  Structurizr's built-in tags, such as `Person`, `Group`, `Element`, and `Relationship`.

**Who reads the file:** `c4 check`, `c4 approve`, the web app, and staging for the viewer all go
through this check. Structurizr only ever reads a copy of bytes that passed it (§8).

tmreg's parser is tested against the pinned Structurizr (§13).

## 7. tmreg changes

### 7.1 `c4.py` replaces `dfd.py`

`c4.py` parses the dialect into a model:
- each item by ID, with its kind, name, description, technology, tags, properties, parent, and DFD
  role;
- each path's two ends;
- the deployment tree;
- zones and crossings for each environment;
- the views;
- the version, and the sha256 of the raw bytes.

It is pure: it reads only the bytes it is given and imports nothing from core. Every error names
its line.

### 7.2 Commands

- `./tmreg c4 status <slug> [--trial]` prints none, current, or changed, like `dfd status`.
- `./tmreg c4 check <slug>` parses and checks the file. It takes no `--trial`. It prints:
  - the version and the sha256;
  - counts by kind;
  - the IDs added, removed, or changed since the latest approval;
  - the next free number of each kind (§5.3);
  - errors for any ID reused for a different item;
  - warnings: live risks that cite removed IDs, and adoption gaps (§7.6);
  - `ok` as its last line.
- `./tmreg c4 approve <slug> [--trial]`:
  - it is human-only and needs a note;
  - the approval is bound to the sha256 the reviewer saw, with `StaleRecord` on a mismatch, as
    today;
  - it refuses an unchanged file.
- `dfd status`, `dfd check`, and `dfd approve` are removed. `dfd` prints one line that points to
  `c4`.
- `run start` prints `model: MODEL-n (state)`.

### 7.3 Approvals and storage

- A new append-only table, `<slug>__model_approvals`, stores each approval:
  - the ID `MODEL-n`;
  - the version, the sha256, and the IDs by kind;
  - the parsed model as canonical JSON;
  - the source text;
  - who approved it, when, and the note.

  Its triggers, replay, and `verify` work like `__dfd_approvals`.
- Storing the parsed model and the source lets the web app show details as they were approved, and
  a line-by-line diff since the previous approval.
- Risks and runs record `model_approval_id`. It joins `SNAPSHOT_FIELDS`, as `dfd_approval_id` is
  today, so a rejected re-review restores it.
- Existing databases are upgraded only by adding tables and columns:
  - old rows and change-log entries stay as written;
  - `verify` accepts both eras;
  - `__dfd_approvals` stays, read-only.

### 7.4 Risks

- `elements` lists IDs from the latest model approval. Any kind except `ENV` can be cited, so a risk
  can point at a sequence (`SEQ`).
- Add, edit, and import validate `elements` as they do today, but against the model approval.
- The edit rule and decision D1 carry over: when the owner edits a risk and it keeps its approval,
  `model_approval_id` moves only when its elements change.
- An item counts as changed between two approvals when any of these differ:
  - a stored field: name, description, technology, tags, or a property other than `tm.was`;
  - its parent;
  - for a path, its two ends or its computed crossings;
  - for an element, its computed zones.

  Wording-only edits count, because the reviewer reads them. Moving a deployment node can therefore
  change many paths. That is intended, since it is the most security-relevant kind of change.
- This one meaning of "changed" drives four things: `c4 check`, the approve panel, the CLI's flag,
  and the risk record.
- "The model has moved on" also has one meaning everywhere: the risk was written against an older
  approval, and a later approval changed one of the items it cites. Today the CLI and the web app
  mean different things by the DFD version of this flag. The flag is information only, and it never
  changes a risk's state.
- Duplicate detection keeps using overlapping IDs.

### 7.5 Routes

`Registry.c4_routes(slug, from_id, to_id)` works on the latest approved model:
- It returns the simple chains of paths from one item to the other, up to 6 hops and 25 chains.
- It follows paths in either direction and marks the hops it takes against the arrow.
- For each hop, it gives the crossings and the open risks that cite that hop or its elements.

"Open risks", here and in the web app's counts, means:
- approved risks whose status is `open`, `planned`, or `in-progress`, counted together;
- drafts awaiting review (`pending`), counted separately;
- never `mitigated`, `accepted`, `wont-fix`, `retired`, or rejected risks.

The web app uses it (§10).

### 7.6 Adopting existing registers

A system that has a DFD approval but no model approval is adopted:
- **Mapping:** its first `workspace.dsl` marks what each old item became. The new item carries
  `tm.was`: the old DFD IDs, separated by commas.
  - One old ID can map to several new items, such as a process split into a container and its
    components.
- **Gaps:** `c4 check` lists every old ID that a live risk cites and no new item claims. Approval
  is refused while any remain.
- **Pending re-reviews:**
  - Adoption is refused while any AI edit of an approved risk still awaits review (a pending risk
    with `last_approved` set). `c4 check` and the refusal list them.
  - The reason: rejecting such a re-review restores its snapshot, which would bring old IDs back.
    The owner clears that queue first.
  - New AI drafts that are pending have no snapshot, so they are rewritten like any live risk.
- **Rewrite:** on the first `c4 approve`, in the same transaction as the approval:
  - each live risk's elements are rewritten from old IDs to new ones;
  - each rewrite is one human edit by the reviewer, with the note
    "Adopted the C4 model MODEL-1: P3→C3, F4→R4";
  - approved risks keep their approval, under the owner-edit rule;
  - retired risks are left as written.
- **Import:** `import-legacy` maps the catalog's citations through `tm.was` the same way.
- **History:** entries from before adoption keep their old IDs, and the web app shows them as
  written.

### 7.7 Reports and the skeleton

- The register's "Element(s)" column lists the new IDs. The detail view shows `model_approval_id`.
- Section 2 of the `threat-model.md` skeleton says the architecture is in `workspace.dsl`, that the
  web app opens the diagrams, and that `./tmreg c4 status` shows its approval.
- The run's check file is renamed `model-check.md`.

## 8. The viewer

**Why not the live viewer.** On 2026-11-09 I ran the pinned `structurizr local` against the sample
on `127.0.0.1`:
- It answered a request with a foreign `Host` header (the shape of a DNS-rebinding attack from a
  web page) and served the whole model, properties included.
- It accepted `PUT /api/workspace/1` from that foreign host, with no credential, and replaced what
  it showed with an empty workspace.
- It accepted writing an image file into its data folder.
- `STRUCTURIZR_EDITABLE=false` stopped none of this.

So any web page or local program could read the diagrams, or make them disagree with the file the
owner approves. A Structurizr server that keeps running is therefore out of this design.

**What replaces it:** Structurizr's static export of the same viewer.
- It is a self-contained site of 25 files and about 2.3 MB, with the same diagram renderer.
- It has no server and no save function.
- It references no outside URLs other than comments and XML namespaces.
- None of its scripts evaluate text as code.
- Its one inline script can be allowed by its hash.

**How it works:**
1. "Open diagrams" on the Architecture page is a locked POST. It reads `workspace.dsl` once, runs
   the full dialect check (§6) on those bytes, and writes those exact bytes to a new folder under
   `diagrams/` at the repo root, which git ignores.
2. The server then runs one export:

   ```
   docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges
     -v <folder>:/usr/local/structurizr <pinned image> export -workspace workspace.dsl -format static -output site
   ```

   The builder confirms the flags work, and adds a read-only root and a non-root user if the export
   still works with them. A file that fails the check is never exported, and the page shows its
   errors.
3. The site is kept by the sha256 of the bytes, so opening the same file again reuses it.
4. The server serves the site at `/diagrams/<reg>/<slug>/<sha256>/`:
   - GET only;
   - behind the same Host check as the API;
   - only with a valid session cookie. A plain navigation can't send the CSRF header, and the page
     only reads;
   - with `no-store`;
   - with the app's CSP, plus `'sha256-…'` for each inline script in that export's `index.html`.
     The server computes those hashes at export time.
5. The Architecture page links to each view of the current export.

**Without Docker:** the app starts and works anyway. "Open diagrams" says Docker isn't running and
how to start it.

**The agent:** the modeling agent can't reach the diagrams. It has no Docker, no curl, and no
browser tools (the guard and the MCP denies), and every `/diagrams` request needs the session
cookie.

## 9. The agent

**`/tm-model` step 2 becomes the model gate:**
- **Reading order:**
  - `inputs/`;
  - the guide's C4 page, DFD page, trust boundaries page, and data classification page;
  - section 2 of the template;
  - the DFD checklist;
  - the current `workspace.dsl`.

  It takes the shape from the reference workspace.
- **Draft or revise** following §5 and §6. The command restates those rules, as it restates the DFD
  grammar today.
- **Zoom-ins:** propose each one with its triggers, record them in `tm.zoom`, and list them in the
  check file.
- **Parse check:** `./tmreg c4 check <slug>`, fixing the file at most twice.
- **Self-check:** the guide's DFD checklist, applied to the DFD roles (§5.8), with the same five
  human-only items.
- **Check file:** `runs/<run-id>/model-check.md`. It holds:
  - the Sources table;
  - open questions and proposed changes;
  - zoom proposals;
  - when adopting, the `tm.was` mapping.
- **Stop:** the message asks the owner to review the model in the web app and approve it there.

**Steps 3–5:**
- Work one item at a time, by DFD role.
- Quote `workspace.dsl` lines, with their line numbers, as evidence.
- `elements` cites the new IDs, and evidence names the model version.

**The guard:**
- Writes are allowed to `systems/<slug>/workspace.dsl` and to run files. Writes to `dfd.md` are
  no longer allowed.
- Writes to `workspace.json` and to anything under `diagrams/` are never allowed.
- `TMREG_OPTIONS` gains `c4 status` (with `--trial`) and `c4 check`. `c4 approve` is human-only.
- The change gets the allow and block cases and the adversarial review that the constraints require.

**Settings:**
- `.claude/settings.json` swaps the `dfd` allow and deny rules for `c4`.
- `Edit(/systems/*/workspace.dsl)` replaces the `dfd.md` rule.
- `Bash(docker:*)` is denied explicitly, although the allow-list already blocks it.
- `tm-model.md`'s `allowed-tools` changes to match.

The agent never runs Structurizr.

## 10. Web app

**The "DFD" page becomes "Architecture"**, one per system and register:
- **Status:** the file against the latest approval (the state and version), and the list of
  approvals.
- **Diagrams:** "Open diagrams" exports the current file (§8), then links to each view: the context
  view, the container view, each component view, each deployment view, and each sequence.
- **Tables by kind:**
  - people and systems;
  - containers, with role, technology, owner, and zoom reason;
  - components, grouped by container;
  - paths: ID, from → to, description, technology, data sent and returned, authentication, and the
    boundaries crossed in each environment;
  - trust boundaries: what's inside, what enforces it, and the paths that cross it;
  - deployment and infrastructure nodes;
  - sequences, with their steps in order.
- **Risks per row:** each row shows its count of open risks. Selecting it shows its details, its
  risks, and the risks on its paths and components.
- **Routes:** pick a start and an end. The page shows the chains of paths between them, with the
  crossings and the risks on each hop (§7.5).
- **The approve panel:**
  - shows what changed since the latest approval: IDs added, removed, or changed (field by field),
    and a line diff of the DSL;
  - shows the check result;
  - shows whether Structurizr itself accepted these exact bytes. That is the result of the latest
    export for the same sha256 (§8):
    - "accepted";
    - "refused", with Structurizr's message;
    - "not checked yet: open the diagrams to check".

    This is information only, never a gate, so approving never needs Docker;
  - takes a note, and approves bound to the sha256 that was shown. A 409 reloads the page.
  - shows the restart hint when a refusal means the server lost its Terminal window.
- **Fixes carried over from the held DFD pass:**
  - one read gives the text, the parse, and the hash, all from the same bytes;
  - the note counter trims the way Python does;
  - an empty list shows nothing, instead of "none" beside an empty list.

**The risk record's element section** shows, for each cited ID:
- its kind, where it sits (`S1 › C3 › K2`), name, technology, description, and DFD role;
- for a path: from → to, the data, the authentication, and the crossings.
- The values come from the approval the risk was written against. When a later approval changed a
  cited item, the record shows both versions.
- Old IDs in history from before adoption show as written.

**Register:** the element filter takes the new IDs, and can optionally include an item's children.

**API:**
- New routes under `/api/<reg>/<slug>/c4/...`: the model, approve, export, and routes.
- The lock walker covers them.
- `/diagrams/...` is a new non-API route. It has its own lock tests: a foreign Host, no cookie, any
  method other than GET, and a path outside the export are all refused.
- The `/dfd` routes are removed.

The Mermaid dependency is removed.

## 11. The reference system

- `systems/ordering-platform/workspace.dsl` is built by hand from the guide's reference system,
  covering both its level-1 diagram and its extensions.
  - It is tracked in git, and it replaces `systems/ordering-platform/dfd.md`, which is removed.
  - Every one of the 56 old IDs is claimed through `tm.was`, so all 44 catalog rows import.
- The old boundaries were lines between zones. They become boxes that keep their numbers through
  `tm.was` (§5.3): `TB1` "Internet ↔ edge" becomes the box around the edge zone.
- `test_reference_system` checks three things: the file parses, all 56 old IDs are claimed, and
  every catalog citation maps.
- It is the shape the agent copies, as `dfd.md` is today, and it holds the standard styles.

## 12. Git policy

- `.gitignore` ignores:
  - `systems/*/workspace.dsl`, except the reference system's;
  - `systems/*/workspace.json`;
  - `diagrams/`.

  The `dfd.md` lines stay, because old local files are still risk data.
- `check_risk_paths.py` gains `REFERENCE_MODELS`. It refuses every other system's
  `workspace.dsl` or `workspace.json`, and anything under `diagrams/`.
- `test_risk_data_policy.py` changes to match.

## 13. Tests

**`c4.py`:**
- the grammar;
- each refused directive and keyword, including a directive inside a string;
- the text rules;
- IDs and their name prefixes;
- required fields;
- zones and crossings: nested boundaries, a group inside a container, people's zones, and several
  instances;
- DFD roles and data classes;
- the hash, and line numbers in errors.

**Core:**
- approve: a stale file, an unchanged file;
- adoption:
  - the mapping;
  - gaps refuse approval;
  - one edit per live risk;
  - approvals kept;
  - retired risks untouched;
  - `verify` still passes;
- risk validation, D1, "moved on", and routes.

**The worked example** is the first fixture. Its expected crossings in `ENV1`:

| Path | Crosses |
|---|---|
| `R1` | nothing |
| `R2` | `TB1`, `TB2`, `TB3` |
| `R3` | `TB3`, `TB4` |
| `R4` | nothing |
| `R5` | `TB2`, `TB3`, `TB7` |
| `R6` | `TB2`, `TB3`, `TB5`, `TB6` |
| `R7` | `TB3`, `TB4`, `TB6` |

Crossings are listed in ID order.

**Conformance:** skipped without Docker, and run by `make test-c4`. For every fixture tmreg accepts,
and for the reference workspace:
- the pinned Structurizr's `validate` passes;
- in its JSON export, the `structurizr.dsl.identifier` values of elements and relationships equal
  tmreg's IDs of those kinds.
  - Instances get generated identifiers, which are ignored.
  - Groups, environments, and views have no identifier there. They are compared by name prefix and
    by view key.
- its deployment-level copies of the relationships give the same pairs of instances that tmreg uses
  for crossings;
- its static export builds, and the inline-script hashes the server computes match its
  `index.html`.

A fixture that tmreg refuses is never given to Structurizr.

**Elsewhere:**
- the guard and settings tests;
- the risk-data policy;
- the web back end:
  - the lock walker;
  - the new routes;
  - the export runs only on checked bytes, with no network;
  - the `/diagrams` lock and its CSP;
  - 409s;
- the front end: the Architecture page, the approve panel, the record's element section, and
  routes.

## 14. Documents to update in the same change

**Tool:**
- `CLAUDE.md` and `README.md`, including "What the guard blocks";
- `tm-model.md` and the agent's `CLAUDE.md`;
- `webapp/DESIGN.md`, plus a note in the web app spec marking §5.4's element details and §6.5 as
  superseded;
- `project.example.toml`, if it mentions the DFD;
- the dev workspace's `CLAUDE.md` and `web-app-followups.md`, where the DFD pass items are now
  covered here.

**Guide** (my call, following the owner's earlier "Yes update those as well"):
- Change only the pages that describe the tool:
  - the playbook: "gate one" becomes the model approval. It is at 1,200 of its 1,200 words, so any
    change there must trim;
  - the tmreg design spec, which also records the Structurizr conventions;
  - the threat register page, where it mentions the DFD.
- The teaching pages stay as they are: the C4 page, the DFD page, the checklist, the STRIDE
  worksheet, the reference system, and the catalog.
  - The C4 page already suggests Structurizr "when you want the derived DFD to be generated and
    version-controlled alongside the architecture", which is what this does.
  - The other pages still apply, through DFD roles and `tm.was`.
  - Rewriting the guide's teaching needs the owner to ask for it.

## 15. Left to the builder

- The parser's internals, the exact string escapes (checked against Structurizr), and the error
  wording.
- How the `diagrams/` folders are laid out, and when old exports are cleaned up.
- Page layout, table column order, and tuning the route limits.
- The exact values in the standard styles.
- How the schema is upgraded, within §7.3's rule of only adding.

## 16. Later

- Risks shown in the viewer: a generated workspace that uses Structurizr's perspectives to show
  risk counts and severity on each element and path.
- A system landscape view across every system in the registry.
- Viewing the approved version beside the current file in the viewer.
- Saved manual layouts, if a safe way appears. For example, layouts kept by the web app and passed
  to the export.
- Signed approvals (web app spec, §11).
