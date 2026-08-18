# Design It Twice

When exploring alternative interfaces for a chosen deepening candidate, use this parallel sub-agent pattern.

## Process

### 1. Frame the problem space
- Constraints any new interface would need to satisfy
- Dependencies it relies on and their categories (see [DEEPENING.md](DEEPENING.md))
- Illustrative code sketch to ground the constraints

### 2. Spawn sub-agents
Spawn 3+ sub-agents in parallel, each producing a **radically different** interface:
- Agent 1: "Minimize the interface — 1–3 entry points max. Maximise leverage."
- Agent 2: "Maximise flexibility — support many use cases and extensions."
- Agent 3: "Optimise for the most common caller — make the default case trivial."
- Agent 4 (if applicable): "Design around ports & adapters for cross-seam dependencies."

### 3. Present and compare
Present designs sequentially and compare by **depth** (leverage at the interface), **locality** (where change concentrates), and **seam placement**. Recommend the strongest design or hybrid.
