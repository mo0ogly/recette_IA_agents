/**
 * RunTree -- recursive collapsible treeview for the runs registry.
 *
 * Level 1: category  (skynet | campaigns | agents | discovery | recette-full)
 * Level 2: group     (one launch/batch, identified by eurodate + group_id)
 * Level 3: run       (individual run with kind + status badge)
 *
 * No external tree library (YAGNI, R20 no new hard deps).
 */

import { useState } from "react";
import type { RunTree, RunCategory, RunGroup, RunNode } from "../../api/client";

// Status badge CSS classes (semantic tokens, no hardcoded hex R31).
function statusClass(status: string): string {
  if (status === "sealed") return "run-badge run-badge-sealed";
  if (status === "running") return "run-badge run-badge-running";
  return "run-badge run-badge-open";
}

function RunNodeItem({
  run,
  selected,
  onSelect,
}: {
  run: RunNode;
  selected: boolean;
  onSelect: (id: string) => void;
}): JSX.Element {
  return (
    <li
      className={["run-tree-run", selected ? "run-tree-run-selected" : ""].join(" ").trim()}
      data-testid={`run-node-${run.id}`}
    >
      <button
        type="button"
        className="run-tree-run-btn"
        onClick={() => onSelect(run.id)}
        aria-current={selected ? "true" : undefined}
      >
        <span className="run-tree-run-id">{run.id}</span>
        <span className="run-tree-run-kind">{run.kind}</span>
        <span className="run-tree-run-date">{run.eurodate}</span>
        <span className={statusClass(run.status)}>{run.status}</span>
      </button>
    </li>
  );
}

function GroupItem({
  group,
  selectedId,
  onSelect,
}: {
  group: RunGroup;
  selectedId: string | null;
  onSelect: (id: string) => void;
}): JSX.Element {
  const [open, setOpen] = useState(true);

  return (
    <li className="run-tree-group" data-testid={`run-group-${group.group_id}`}>
      <button
        type="button"
        className="run-tree-group-btn"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="run-tree-group-toggle">{open ? "-" : "+"}</span>
        <span className="run-tree-group-label">{group.label}</span>
        <span className="run-tree-group-date">{group.eurodate}</span>
        <span className={statusClass(group.status)}>{group.status}</span>
      </button>
      {open && (
        <ul className="run-tree-runs">
          {group.runs.map((run) => (
            <RunNodeItem
              key={run.id}
              run={run}
              selected={selectedId === run.id}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function CategoryItem({
  cat,
  selectedId,
  onSelect,
}: {
  cat: RunCategory;
  selectedId: string | null;
  onSelect: (id: string) => void;
}): JSX.Element {
  const [open, setOpen] = useState(true);

  return (
    <li className="run-tree-category" data-testid={`run-category-${cat.category}`}>
      <button
        type="button"
        className="run-tree-category-btn"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="run-tree-category-toggle">{open ? "-" : "+"}</span>
        <span className="run-tree-category-name">{cat.category}</span>
      </button>
      {open && (
        <ul className="run-tree-groups">
          {cat.groups.map((group) => (
            <GroupItem
              key={group.group_id}
              group={group}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export default function RunTreeComponent({
  data,
  selectedId,
  onSelect,
}: {
  data: RunTree;
  selectedId: string | null;
  onSelect: (runId: string) => void;
}): JSX.Element {
  return (
    <nav className="run-tree" aria-label="Runs registry">
      <ul className="run-tree-categories">
        {data.categories.map((cat) => (
          <CategoryItem
            key={cat.category}
            cat={cat}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </nav>
  );
}
